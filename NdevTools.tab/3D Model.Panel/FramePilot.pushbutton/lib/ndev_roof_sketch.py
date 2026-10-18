# -*- coding: utf-8 -*-
"""Launch Revit's native beam-system tool with the existing FramePilot config.

Revit exposes the Beam System entry command as AutomaticBeamSystem. The user
chooses Sketch Beam System in its contextual ribbon. DocumentChanged captures
the new systems; an idle callback applies settings after the native transaction.
"""

import math
import clr

from System import Double, EventHandler
from Autodesk.Revit import DB
from Autodesk.Revit.UI import PostableCommand, RevitCommandId
from Autodesk.Revit.UI.Events import IdlingEventArgs

BUILD = '2026-10-18-sketch-settings-5'


class NativeBeamSystemSketch(object):
    def __init__(self, application, document, on_finished, write_comments):
        self.application = application
        self.document = document
        self.on_finished = on_finished
        self.write_comments = write_comments
        self._idle_subscribed = False
        self._document_subscribed = False
        self._cancel_requested = False
        self._event_error = None
        self._notification_sent = False
        self._idle_handler = EventHandler[IdlingEventArgs](self._on_idle)
        self._document_handler = EventHandler[DB.Events.DocumentChangedEventArgs](self._on_document_changed)
        self._existing = set()
        self._created = set()

    def start(self, elevation_text, comment_text, config=None, host_plane=None):
        doc = self.document
        elevation = clr.Reference[Double]()
        if not DB.UnitFormatUtils.TryParse(doc.GetUnits(), DB.SpecTypeId.Length,
                                           elevation_text, elevation):
            raise ValueError('Enter a valid Elevation from Level in project units '
                             'or feet and inches, for example -0\' 4".')
        self.elevation = float(elevation.Value)
        if math.isnan(self.elevation) or math.isinf(self.elevation):
            raise ValueError('Elevation from Level must be a finite length.')
        self.comment_text = comment_text
        self.config = config
        self.host_plane = host_plane
        command = RevitCommandId.LookupPostableCommandId(PostableCommand.AutomaticBeamSystem)
        if not self.application.CanPostCommand(command):
            raise ValueError('Open a model plan or 3D view and finish the current Revit command, '
                             'then try Sketch Beam System again.')
        self._existing = set(system.UniqueId for system in
                             DB.FilteredElementCollector(doc).OfClass(DB.BeamSystem))
        # Use exactly the same top/bottom host depth as FRAME when its current
        # host is known. Otherwise leave Revit's existing work plane untouched.
        # Never assign a Level or create a level-backed SketchPlane here.
        if host_plane is not None:
            transaction = DB.Transaction(doc, 'FramePilot: beam-system work plane')
            try:
                transaction.Start()
                from ndev_roof_flat import _workplane_depth
                depth = _workplane_depth(host_plane, config.workplane_face)
                origin = host_plane.point_at(0.0, 0.0, depth - host_plane.target_layer_depth)
                plane = DB.Plane.CreateByNormalAndOrigin(host_plane.normal, origin)
                doc.ActiveView.SketchPlane = DB.SketchPlane.Create(doc, plane)
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise RuntimeError('Revit could not set the selected Work Plane.')
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
            finally:
                transaction.Dispose()
        try:
            self.application.Application.DocumentChanged += self._document_handler
            self._document_subscribed = True
            self.application.Idling += self._idle_handler
            self._idle_subscribed = True
            self.application.PostCommand(command)
        except Exception:
            self.cancel()
            raise

    def request_cancel(self):
        """Safe from modeless WPF: defer Revit event removal until an API callback."""
        self._cancel_requested = True

    def cancel(self):
        """Detach only inside a Revit API callback; never propagate cleanup errors."""
        self._cancel_requested = True
        if self._document_subscribed:
            try:
                self.application.Application.DocumentChanged -= self._document_handler
                self._document_subscribed = False
            except Exception as error:
                self._event_error = unicode(error)
        # Keep one idle callback available to retry if document-listener
        # removal failed; a cancelled listener must never process additions.
        if self._idle_subscribed and not self._document_subscribed:
            try:
                self.application.Idling -= self._idle_handler
                self._idle_subscribed = False
            except Exception as error:
                self._event_error = unicode(error)

    def _notify(self, message):
        # Unhandled exceptions from .NET event delegates can terminate Revit.
        if self._notification_sent:
            return
        self._notification_sent = True
        try:
            self.on_finished(message)
        except Exception:
            pass

    def _on_document_changed(self, sender, args):
        # This is a read-only event. Only capture IDs here; never open a
        # transaction until Revit returns to an idle API context.
        if self._cancel_requested:
            return
        try:
            if not args.GetDocument().Equals(self.document):
                return
            for element_id in args.GetAddedElementIds():
                element = self.document.GetElement(element_id)
                if isinstance(element, DB.BeamSystem) and element.UniqueId not in self._existing:
                    self._created.add(element.UniqueId)
        except Exception as error:
            self._event_error = unicode(error)
            self.request_cancel()

    def _apply_elevation(self, system):
        # Change only the offset; preserve the work plane/level chosen in Revit.
        try:
            system.Elevation = self.elevation
        except Exception:
            parameter = system.get_Parameter(DB.BuiltInParameter.INSTANCE_ELEVATION_PARAM)
            if parameter is None or parameter.IsReadOnly or not parameter.Set(self.elevation):
                raise RuntimeError('Elevation from Level is not writable for this system.')
        if abs(float(system.Elevation) - self.elevation) > 1e-6:
            raise RuntimeError('Revit did not retain the requested Elevation from Level.')

    def _on_idle(self, sender, args):
        doc = self.document
        try:
            if self._cancel_requested:
                self.cancel()
                if self._event_error:
                    message = self._event_error
                    self._event_error = None
                    self._notify(u'Sketch tracking stopped: ' + message)
                return
            active = self.application.ActiveUIDocument
            if (not doc.IsValidObject or active is None
                    or not active.Document.Equals(doc)):
                self.cancel()
                self._notify(u'Sketch ended. Return to the original project to continue.')
                return
            # An idle tick can occur BEFORE the posted tool creates anything.
            # Stay armed until actual additions arrive. Another panel action or
            # closing FramePilot explicitly cancels this pending capture.
            if not self._created:
                return
            if doc.IsModifiable or doc.IsReadOnly:
                return
            systems = [doc.GetElement(uid) for uid in self._created]
            systems = [system for system in systems if isinstance(system, DB.BeamSystem)]
            if not systems:
                self._created.clear()
                return
            self.cancel()
            transaction = DB.Transaction(doc, 'FramePilot: sketched beam-system settings')
            elevation_errors = []
            justification_skipped = 0
            try:
                transaction.Start()
                if self.config is not None:
                    from ndev_roof_families import find_family_symbol, activate_symbol
                    symbol = find_family_symbol(doc, self.config.stud_family_name,
                                                self.config.stud_type_name,
                                                DB.BuiltInCategory.OST_StructuralFraming)
                    if symbol is None:
                        raise ValueError('The selected framing family/type is no longer loaded.')
                    activate_symbol(doc, symbol)
                    for system in systems:
                        system.BeamType = symbol
                        system.LayoutRule = DB.LayoutRuleFixedDistance(
                            self.config.stud_spacing_ft, DB.BeamSystemJustifyType.DirectionLine)
                for system in systems:
                    update = DB.SubTransaction(doc)
                    try:
                        update.Start()
                        self._apply_elevation(system)
                        if update.Commit() != DB.TransactionStatus.Committed:
                            raise RuntimeError('Revit did not commit Elevation from Level.')
                    except Exception as error:
                        if update.GetStatus() == DB.TransactionStatus.Started:
                            update.RollBack()
                        elevation_errors.append(unicode(error))
                    finally:
                        update.Dispose()
                doc.Regenerate()
                # Regeneration can replace generated beams after a level/elevation
                # change. Resolve the final members before writing instance Comments.
                elements = list(systems)
                if self.config is not None:
                    from ndev_roof_flat import _set_beam_z_justification
                for system in systems:
                    for element_id in system.GetBeamIds():
                        beam = doc.GetElement(element_id)
                        elements.append(beam)
                        if self.config is not None and beam is not None:
                            if not _set_beam_z_justification(beam, self.config.z_justification):
                                justification_skipped += 1
                commented, skipped = self.write_comments(elements, self.comment_text)
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise RuntimeError('Revit did not commit the beam-system settings.')
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
            finally:
                transaction.Dispose()
            message = (u'{0} beam system(s) created; custom comments written to {1} elements.').format(
                len(systems), commented)
            if elevation_errors:
                message += u' Elevation could not be applied: ' + u'; '.join(elevation_errors)
            else:
                message += u' Elevation offset applied.'
            if self.config is not None:
                message += u' FramePilot framing type and spacing applied.'
                if not justification_skipped:
                    message += u' Z Justification applied.'
                if self.host_plane is None:
                    message += (u' The existing Revit work plane was retained; Top/Bottom needs '
                                u'an existing single-face host context.')
                else:
                    message += u' {0} host workplane applied.'.format(self.config.workplane_face.title())
            if justification_skipped:
                message += u' Z Justification is locked on {0} beam(s).'.format(justification_skipped)
            if skipped:
                message += (u' {0} element(s) have missing, read-only, or unwritable Comments. '
                            u'Check Revit Properties.').format(skipped)
            self._notify(message)
        except Exception as error:
            self.cancel()
            self._notify(u'Sketch settings could not be applied: {0}. '
                         u'Check the created beam system in Revit Properties.'.format(error))
