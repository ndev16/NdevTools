# -*- coding: utf-8 -*-
"""Copy selected 2D detailing from an open section into another project view."""
import imp
import os

from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import DB, UI

transfer = imp.load_source('ndev_main_sheet_project_copy', os.path.join(os.path.dirname(__file__), 'project_copy.py'))
DESTINATIONS = (DB.ViewType.Section, DB.ViewType.Detail, DB.ViewType.DraftingView, DB.ViewType.Elevation,
                DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan, DB.ViewType.CeilingPlan)


def _supported(element):
    if isinstance(element, DB.FamilyInstance):
        return element.ViewSpecific and element.SuperComponent is None
    return isinstance(element, (DB.DetailCurve, DB.TextNote, DB.FilledRegion, DB.Dimension,
                                DB.IndependentTag, DB.Group, DB.ImageInstance))


def _references(element):
    if isinstance(element, DB.Dimension):
        return [r.ElementId for r in (element.References or [])]
    if isinstance(element, DB.IndependentTag):
        return [r.HostElementId for r in element.GetTaggedElementIds()]
    if isinstance(element, DB.FamilyInstance) and element.Host is not None and not isinstance(element.Host, DB.View):
        return [element.Host.Id]
    return []


def _reason(view, element, selected):
    if element.OwnerViewId != view.Id or not element.ViewSpecific or not _supported(element):
        return 'Only view-specific detail elements from the active section can be copied.'
    if element.GroupId != DB.ElementId.InvalidElementId:
        return 'Select the whole detail group to copy it.'
    if any(ref not in selected for ref in _references(element)):
        return 'This annotation needs its referenced elements. Select its detail references together, or recreate model references in the destination.'
    return ''


def copy(uidoc, clip):
    view, doc = uidoc.ActiveView, uidoc.Document
    ids = list(uidoc.Selection.GetElementIds())
    if not ids:
        try:
            refs = uidoc.Selection.PickObjects(UI.Selection.ObjectType.Element, 'Select section details to copy, then click Finish.')
            ids = [r.ElementId for r in refs]
        except OperationCanceledException:
            return None
    if not ids:
        return None
    selected = set(ids)
    rows, corners = [], []
    for eid in ids:
        element = doc.GetElement(eid)
        reason = _reason(view, element, selected)
        box = None if reason else element.get_BoundingBox(view)
        if not reason and box is None:
            reason = 'This detail has no measurable extent in the source view.'
        if box is not None:
            for x in (box.Min.X, box.Max.X):
                for y in (box.Min.Y, box.Max.Y):
                    for z in (box.Min.Z, box.Max.Z):
                        point = box.Transform.OfPoint(DB.XYZ(x, y, z)) - view.Origin
                        corners.append((point.DotProduct(view.RightDirection), point.DotProduct(view.UpDirection)))
        rows.append({'uid': element.UniqueId, 'label': clip.display_name(doc, element),
                     'version': str(element.VersionGuid), 'blocked': reason})
    if not corners:
        raise ValueError(rows[0]['blocked'])
    mid = [(min(c[i] for c in corners) + max(c[i] for c in corners)) * .5 for i in (0, 1)]
    center = view.Origin + view.RightDirection * mid[0] + view.UpDirection * mid[1]
    return clip.store_rows(doc, view, view.Name, rows, (center.X, center.Y, center.Z), 'copy', 'view-details')


def pick_point(uidoc, prompt):
    view = uidoc.ActiveView
    # Newly created sections often have no active work plane. Use the drawing
    # plane for the click and restore the user's work plane, including on Escape.
    if isinstance(view, DB.ViewDrafting):
        return uidoc.Selection.PickPoint(prompt)
    plane = view.SketchPlane
    if plane and abs(plane.GetPlane().Normal.DotProduct(view.ViewDirection)) > .999999:
        return uidoc.Selection.PickPoint(prompt)
    doc = uidoc.Document
    group = DB.TransactionGroup(doc, 'Pick section detail location')
    try:
        group.Start()
        with DB.Transaction(doc, 'Set temporary drawing plane') as tx:
            tx.Start()
            plane = DB.Plane.CreateByNormalAndOrigin(view.ViewDirection, view.Origin)
            view.SketchPlane = DB.SketchPlane.Create(doc, plane)
            if tx.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Revit could not set the work plane for the paste point.')
        return uidoc.Selection.PickPoint(prompt)
    finally:
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        group.Dispose()


def _copy_set(source, target, elements, shift, options, moves):
    doc = target.Document
    with DB.Transaction(doc, 'Paste section details') as tx:
        tx.Start()
        try:
            failures = moves._Failures()
            settings = tx.GetFailureHandlingOptions()
            settings.SetFailuresPreprocessor(failures).SetClearAfterRollback(True)
            tx.SetFailureHandlingOptions(settings)
            details = [e for e in elements if not isinstance(e, DB.ImageInstance)]
            copied = []
            if details:
                copied.extend(DB.ElementTransformUtils.CopyElements(source, transfer._ids(details), target,
                                                                   DB.Transform.Identity, options))
            for image in elements:
                if isinstance(image, DB.ImageInstance):
                    image_ids = transfer.copy_image_ids(source, target, image, options)
                    for eid in image_ids:
                        new = doc.GetElement(eid)
                        if isinstance(new, DB.ImageInstance) and new.OwnerViewId == target.Id and new.Pinned != image.Pinned:
                            new.Pinned = image.Pinned
                    copied.extend(image_ids)
            roots = [doc.GetElement(eid) for eid in copied]
            roots = [e for e in roots if e.OwnerViewId == target.Id and e.GroupId == DB.ElementId.InvalidElementId
                     and e.ViewSpecific and _supported(e)]
            # CopyElements also returns types and sketch dependencies. Only
            # count the same top-level detail classes the user actually copied.
            if transfer._signature(roots) != transfer._signature(elements):
                raise ValueError('Revit could not reproduce the selected details in the destination view.')
            if not shift.IsZeroLength():
                pinned = [e for e in roots if e.Pinned]
                for e in pinned:
                    e.Pinned = False
                DB.ElementTransformUtils.MoveElements(doc, transfer._ids(roots), shift)
                for e in pinned:
                    e.Pinned = True
            if tx.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Revit could not place these details. ' + ' '.join(failures.messages))
            return [e.UniqueId for e in roots]
        finally:
            if tx.GetStatus() == DB.TransactionStatus.Started:
                tx.RollBack()


def _connected_sets(elements):
    by_id = dict((e.Id, e) for e in elements)
    neighbours = dict((eid, set()) for eid in by_id)
    for e in elements:
        for other in _references(e):
            if other in by_id:
                neighbours[e.Id].add(other)
                neighbours[other].add(e.Id)
    remaining = set(by_id)
    while remaining:
        stack = [remaining.pop()]
        connected = []
        while stack:
            eid = stack.pop()
            connected.append(by_id[eid])
            found = neighbours[eid] & remaining
            remaining.difference_update(found)
            stack.extend(found)
        yield connected


def _try_copy(source, target, elements, shift, options, moves):
    try:
        return _copy_set(source, target, elements, shift, options, moves), None
    except Exception as error:
        if not moves._expected_copy_failure(getattr(error, 'clsException', error)):
            raise
        return [], unicode(error)


def paste(uidoc, entry, clip, moves, prompt, skipped):
    doc, target = uidoc.Document, uidoc.ActiveView
    if target.ViewType not in DESTINATIONS or target.IsTemplate:
        raise ValueError('Open the destination section or another 2D detail view before pasting section details.')
    source_doc = entry['document']
    source = source_doc.GetElement(entry['source'])
    if source is None:
        raise ValueError('The source section was deleted. Copy the details again.')
    try:
        point = pick_point(uidoc, prompt)
    except OperationCanceledException:
        return None
    if point is None:
        return None
    current = clip.for_paste(doc)
    if current is None or current['token'] != entry['token']:
        raise ValueError('The clipboard changed. Paste again using the new selection.')
    elements = []
    for row in entry['rows']:
        e = source_doc.GetElement(row['uid'])
        reason = row['blocked']
        if not reason and (e is None or e.OwnerViewId != source.Id or str(e.VersionGuid) != row['version']):
            reason = 'The source detail changed or was deleted. Copy it again.'
        if reason:
            skipped.append((row['uid'], reason))
        else:
            elements.append(e)
    selected = set(e.Id for e in elements)
    valid = []
    for e in elements:
        reason = _reason(source, e, selected)
        if reason:
            skipped.append((e.UniqueId, reason))
        else:
            valid.append(e)
    if not valid:
        return []
    aligned = DB.ElementTransformUtils.GetTransformFromViewToView(source, target).OfPoint(DB.XYZ(*entry['center']))
    delta = point - aligned
    shift = delta - target.ViewDirection * delta.DotProduct(target.ViewDirection)
    with DB.CopyPasteOptions() as options, DB.TransactionGroup(doc, 'Paste section details') as group:
        options.SetDuplicateTypeNamesHandler(transfer.DestinationTypes())
        group.Start()
        try:
            placed, failure = _try_copy(source, target, valid, shift, options, moves)
            if failure:
                # Keep referenced details together when isolating a failed item.
                for batch in _connected_sets(valid):
                    reason = failure
                    if len(batch) < len(valid):
                        copied, reason = _try_copy(source, target, batch, shift, options, moves)
                        placed.extend(copied)
                    if reason:
                        skipped.extend((e.UniqueId, reason) for e in batch)
            if placed and group.Assimilate() != DB.TransactionStatus.Committed:
                raise ValueError('Revit could not commit the pasted section details.')
        finally:
            if group.GetStatus() == DB.TransactionStatus.Started:
                group.RollBack()
    return placed
