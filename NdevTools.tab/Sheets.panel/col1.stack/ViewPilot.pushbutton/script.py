# -*- coding: utf-8 -*-
"""NdevTools ViewPilot - pyRevit host / HTML UI bridge.

Compatible syntax: IronPython 2.7. Intended for Revit 2022-2027; validate
against the specific build and project before production deployment.

All files/UI are local. No API calls, telemetry, CDN, or remote scripts.
User-initiated Help buttons open the public GitHub pages in a browser.
"""
from __future__ import print_function

import os
import sys
import json
import base64
import codecs
import traceback
import re

import clr
clr.AddReference('System')
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')

from System.Windows.Forms import (Form, WebBrowser, DockStyle, FormStartPosition,
                                  FormWindowState, WebBrowserReadyState, MessageBox, Button, Label, FlowLayoutPanel, FlowDirection)
from System.Drawing import Size, Point
from System import Array, Object, Int64
from System.Diagnostics import Process, ProcessStartInfo

from pyrevit import revit, DB, script

DOC = revit.doc
APP_VERSION = str(DOC.Application.VersionNumber) if DOC else 'unknown'
ROOT = os.path.dirname(__file__)
UI_DIR = os.path.join(ROOT, 'ui')
DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                        'NdevTools', 'ViewPilot')
PRESET_FILE = os.path.join(DATA_DIR, 'presets.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
HELP_URL = 'https://github.com/ndev16/NdevTools'
ISSUES_URL = HELP_URL + '/issues/new'
# Add the creator's LinkedIn URL here when provided. Never guess a profile.
LINKEDIN_URL = 'https://www.linkedin.com/in/nataraj016/'
SUPPORTED = ('2022', '2023', '2024', '2025', '2026', '2027')


def element_id_value(eid):
    try:
        return int(eid.Value)
    except Exception:
        return int(eid.IntegerValue)


def int_id(el):
    return element_id_value(el.Id)


def new_element_id(n):
    """Revit 2024+ may use Int64 ids; Revit 2022/23 accept Int32 ids."""
    try:
        return DB.ElementId(Int64(n))
    except (TypeError, OverflowError, ValueError):
        return DB.ElementId(int(n))


def safe_text(value):
    try:
        return unicode(value)
    except NameError:
        return str(value)
    except Exception:
        return ''


def view_type_name(view):
    try:
        return safe_text(view.ViewType.ToString())
    except Exception:
        return 'Other'


def category_for(view):
    vt = view_type_name(view)
    if vt in ('FloorPlan', 'EngineeringPlan'):
        try:
            if safe_text(view.Discipline).lower().find('structural') >= 0:
                return 'Structural Plans'
        except Exception:
            pass
        if vt == 'EngineeringPlan':
            return 'Structural Plans'
        return 'Floor Plans'
    if vt == 'CeilingPlan':
        return 'Ceiling Plans'
    if vt == 'AreaPlan':
        return 'Area Plans'
    if vt == 'Section':
        # Revit does not always expose detail versus building-section subtype
        try:
            p = view.get_Parameter(DB.BuiltInParameter.VIEW_FAMILY)
            if p and 'Detail' in safe_text(p.AsValueString()):
                return 'Detail Views'
        except Exception:
            pass
        return 'Sections'
    if vt == 'Detail':
        return 'Detail Views'
    if vt == 'Elevation':
        return 'Elevations'
    if vt == 'DraftingView':
        return 'Drafting Views'
    if vt == 'Legend':
        return 'Legends'
    if vt == 'ThreeD':
        return '3D Views'
    if vt in ('Schedule', 'ColumnSchedule', 'PanelSchedule', 'CostReport'):
        return 'Schedules'
    return 'Other Views'


EXCLUDED_TYPES = set(('DrawingSheet', 'ProjectBrowser', 'SystemBrowser',
                      'Internal', 'Undefined', 'Report', 'LoadsReport'))
DUP_OPTIONS = [('duplicate', DB.ViewDuplicateOption.Duplicate),
               ('detailing', DB.ViewDuplicateOption.WithDetailing),
               ('dependent', DB.ViewDuplicateOption.AsDependent)]


def valid_view(view):
    try:
        if view.IsTemplate or view_type_name(view) in EXCLUDED_TYPES:
            return False
        if not view.Name:
            return False
        return True
    except Exception:
        return False


def is_dependent_view(view):
    try:
        return view.GetPrimaryViewId() != DB.ElementId.InvalidElementId
    except Exception:
        return False


def get_param(view, param_id):
    try:
        return view.get_Parameter(param_id)
    except Exception:
        return None


def detect_view_scale_units():
    """Read host project's displayed length units (Revit 2022+), for labels only.

    View.Scale stores an integer drawing ratio in BOTH unit systems.
    Therefore imperial labels must map e.g. 1/4 inch = 1 foot to 1:48.
    """
    try:
        units = DOC.GetUnits()
        fmt = units.GetFormatOptions(DB.SpecTypeId.Length)
        display = safe_text(fmt.GetUnitTypeId()).lower()
        if any(word in display for word in ('feet', 'foot', 'inch')):
            return 'imperial'
        if any(word in display for word in ('millimeter', 'centimeter', 'meter')):
            return 'metric'
    except Exception:
        pass
    try:
        value = safe_text(DOC.DisplayUnitSystem).lower()
        if 'imperial' in value:
            return 'imperial'
        if 'metric' in value:
            return 'metric'
    except Exception:
        pass
    return 'metric'  # safe ratio labels, not an assumed conversion


def collect_template_metadata(v):
    """Bound expected unsupported-property exceptions to one template."""
    try:
        controls_scale = False
        try:
            # GetTemplateParameterIds gives parameters governed by this template;
            # NonControlledTemplateParameterIds excludes unchecked template parameters.
            scale_pid = new_element_id(int(DB.BuiltInParameter.VIEW_SCALE))
            all_ids = set(element_id_value(e) for e in v.GetTemplateParameterIds())
            excluded = set(element_id_value(e) for e in v.GetNonControlledTemplateParameterIds())
            controls_scale = (element_id_value(scale_pid) in all_ids and
                              element_id_value(scale_pid) not in excluded)
        except Exception:
            # Conservative fallback: don't incorrectly claim a template locks Scale.
            controls_scale = False
        try:
            tscale = int(v.Scale)
        except Exception:
            tscale = 0
        return {'id': str(int_id(v)), 'name': safe_text(v.Name),
                'type': view_type_name(v), 'scale': tscale,
                'controls_scale': controls_scale}
    except Exception:
        return None


def compatible_template_id(view, candidate):
    """Use the supported compatibility check without an exception-driven scan."""
    try:
        if view.IsValidViewTemplate(candidate.Id):
            return str(int_id(candidate))
    except Exception:
        pass
    return None


def collect_view_metadata(view, template_views, sheets_by_view):
    """Read one view in its own Python frame, including unsupported properties."""
    if not valid_view(view):
        return None
    vt = view_type_name(view)
    dup = []
    for key, enum_value in DUP_OPTIONS:
        try:
            if view.CanViewBeDuplicated(enum_value):
                dup.append(key)
        except Exception:
            pass
    scope = get_param(view, DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
    scope_value = 'none'
    can_scope = bool(scope)
    can_edit_scope = bool(scope and not scope.IsReadOnly)
    try:
        if scope and scope.AsElementId() != DB.ElementId.InvalidElementId:
            scope_value = str(element_id_value(scope.AsElementId()))
    except Exception:
        pass
    template_id = 'none'
    try:
        if view.ViewTemplateId != DB.ElementId.InvalidElementId:
            template_id = str(element_id_value(view.ViewTemplateId))
    except Exception:
        pass
    try:
        scale = int(view.Scale)
    except Exception:
        scale = 0
    try:
        crop = bool(view.CropBoxActive)
    except Exception:
        crop = None
    # Revit exposes IsValidViewTemplate, not GetValidViewTemplateIds.
    # Keep exception handling in a separate call for each candidate so
    # IronPython's interpreted exception continuations cannot grow with
    # the number of views/templates in the project.
    valid_template_ids = []
    for candidate in template_views:
        candidate_id = compatible_template_id(view, candidate)
        if candidate_id is not None:
            valid_template_ids.append(candidate_id)
    if template_id != 'none' and template_id not in valid_template_ids:
        # Preserve the existing assignment even when a view type cannot
        # enumerate it (this does not authorize assigning it elsewhere).
        valid_template_ids.append(template_id)
    return {'id': str(int_id(view)), 'name': safe_text(view.Name),
            'type': vt, 'category': category_for(view),
            'methods': dup, 'sheet': sheets_by_view.get(int_id(view), ''),
            'scope': scope_value, 'can_scope': can_scope,
            'can_edit_scope': can_edit_scope,
            'valid_templates': valid_template_ids,
            'template': template_id, 'scale': scale,
            'crop': crop, 'dependent': is_dependent_view(view)}


def collect_model():
    """Return UI-safe metadata. Read-only; does not start a transaction."""
    all_views = list(DB.FilteredElementCollector(DOC).OfClass(DB.View).ToElements())
    sheets_by_view = {}
    for vp in DB.FilteredElementCollector(DOC).OfClass(DB.Viewport).ToElements():
        try:
            sh = DOC.GetElement(vp.SheetId)
            if sh:
                sheets_by_view[int(element_id_value(vp.ViewId))] = safe_text(sh.SheetNumber)
        except Exception:
            pass
    for si in DB.FilteredElementCollector(DOC).OfClass(DB.ScheduleSheetInstance).ToElements():
        try:
            sh = DOC.GetElement(si.OwnerViewId)
            if sh:
                sheets_by_view[int(element_id_value(si.ScheduleId))] = safe_text(sh.SheetNumber)
        except Exception:
            pass

    scope_boxes = []
    try:
        for el in DB.FilteredElementCollector(DOC).OfCategory(
                DB.BuiltInCategory.OST_VolumeOfInterest).WhereElementIsNotElementType():
            scope_boxes.append({'id': str(int_id(el)), 'name': safe_text(el.Name)})
    except Exception:
        pass
    scope_boxes.sort(key=lambda x: x['name'].lower())

    template_views = [v for v in all_views if v.IsTemplate]
    templates = []
    for template in template_views:
        metadata = collect_template_metadata(template)
        if metadata is not None:
            templates.append(metadata)
    templates.sort(key=lambda x: x['name'].lower())

    views = []
    for view in all_views:
        metadata = collect_view_metadata(view, template_views, sheets_by_view)
        if metadata is not None:
            views.append(metadata)
    views.sort(key=lambda x: (x['category'], x['name'].lower()))
    return {'project': safe_text(DOC.Title), 'version': APP_VERSION,
            'unitSystem': detect_view_scale_units(),
            'views': views, 'scopeBoxes': scope_boxes, 'templates': templates,
            'presets': read_json(PRESET_FILE, {}),
            'settings': read_json(SETTINGS_FILE, {'humor': True})}


def read_json(filename, fallback):
    try:
        with codecs.open(filename, 'r', 'utf-8') as f:
            return json.load(f)
    except Exception:
        return fallback


def save_json(filename, value):
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR)
    with codecs.open(filename, 'w', 'utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def safe_name(name):
    val = safe_text(name).strip()
    if not val or len(val) > 250:
        raise ValueError('View names must be 1-250 characters.')
    # Let the Revit API enforce any other project/view-specific constraints.
    return val


def scope_box(view, choice, warnings):
    if not choice or choice == 'default':
        return
    p = get_param(view, DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
    if not p or p.IsReadOnly:
        warnings.append('Scope box not editable on: ' + safe_text(view.Name))
        return
    try:
        p.Set(DB.ElementId.InvalidElementId if choice == 'none' else new_element_id(choice))
    except Exception as exc:
        warnings.append('Cannot assign scope box to {0}: {1}'.format(view.Name, exc))


def template_setting(view, choice, warnings):
    if not choice or choice == 'default':
        return
    try:
        target = DB.ElementId.InvalidElementId if choice == 'none' else new_element_id(choice)
        if choice != 'none' and not view.IsValidViewTemplate(target):
            warnings.append('Template incompatible with ' + safe_text(view.Name))
            return
        view.ViewTemplateId = target
    except Exception as exc:
        warnings.append('Cannot set template on {0}: {1}'.format(view.Name, exc))


def scale_setting(view, choice, warnings):
    if not choice or choice == 'default':
        return
    try:
        view.Scale = int(choice)
    except Exception as exc:
        warnings.append('Cannot set scale on {0}: {1}'.format(view.Name, exc))


def crop_setting(view, choice, warnings):
    if not choice or choice == 'default':
        return
    try:
        view.CropBoxActive = choice == 'on'
    except Exception as exc:
        warnings.append('Cannot set crop on {0}: {1}'.format(view.Name, exc))


def apply_settings(view, opts, warnings, is_original=False):
    if not isinstance(opts, dict):
        return
    # Apply the template before direct view properties. Template control may
    # lock crop/scale/scope, in which case warnings are reported.
    if not is_original:
        template_setting(view, opts.get('template', 'default'), warnings)
        scale_setting(view, opts.get('scale', 'default'), warnings)
    scope_box(view, opts.get('scope', 'default'), warnings)


def get_view_from_string(raw_id):
    try:
        el = DOC.GetElement(new_element_id(raw_id))
        return el if isinstance(el, DB.View) else None
    except Exception:
        return None


def validate_job(job):
    """Preflight names and requested methods, including swaps of source names."""
    rows = job.get('items', [])
    if not isinstance(rows, list) or not rows:
        raise ValueError('Select at least one view to process.')
    current = [v for v in DB.FilteredElementCollector(DOC).OfClass(DB.View).ToElements()
               if valid_view(v)]
    all_names = dict((safe_text(v.Name).casefold() if hasattr(safe_text(v.Name), 'casefold')
                      else safe_text(v.Name).lower(), int_id(v)) for v in current)
    changing_ids = set()
    for row in rows:
        view = get_view_from_string(row.get('id'))
        if view is None or not valid_view(view):
            raise ValueError('A selected view no longer exists. Click Refresh.')
        newname = safe_name(row.get('new_name', view.Name))
        if newname.lower() != safe_text(view.Name).lower():
            changing_ids.add(int_id(view))
        for copy in row.get('copies', []):
            method = copy.get('method', '')
            enum = dict(DUP_OPTIONS).get(method)
            if enum is None or not view.CanViewBeDuplicated(enum):
                raise ValueError('Duplication method "{0}" is invalid for {1}.'.format(
                    method, view.Name))
            if method != 'dependent':
                selected_template = safe_text(copy.get('template', 'default'))
                if selected_template not in ('default', 'none'):
                    template_view = get_view_from_string(selected_template)
                    if (template_view is None or not template_view.IsTemplate or
                            not view.IsValidViewTemplate(template_view.Id)):
                        raise ValueError('View template is incompatible with ' + safe_text(view.Name))
                if copy.get('scale', 'default') == 'ask':
                    raise ValueError('Select a view scale for copy of ' + safe_text(view.Name))

    retained = set(n for n, ident in all_names.items() if ident not in changing_ids)
    targets = set()
    for row in rows:
        view = get_view_from_string(row['id'])
        desired = safe_name(row.get('new_name', view.Name))
        if int_id(view) in changing_ids:
            key = desired.lower()
            if key in retained or key in targets:
                raise ValueError('View name conflict: ' + desired)
            targets.add(key)
        for cp in row.get('copies', []):
            name = safe_name(cp.get('name', ''))
            key = name.lower()
            if key in retained or key in targets:
                raise ValueError('View name conflict: ' + name)
            targets.add(key)
    return rows


def apply_job(payload):
    """One undo-friendly transaction. Nothing commits when validation fails."""
    rows = validate_job(payload)
    trans = DB.Transaction(DOC, 'NdevTools ViewPilot - Batch Rename and Duplicate')
    created = []
    renamed = []
    warnings = []
    trans.Start()
    try:
        # Temporary renaming allows name swaps (Plan A <-> Plan B).
        renames = []
        for row in rows:
            view = get_view_from_string(row['id'])
            if safe_text(view.Name) != safe_text(row.get('new_name', view.Name)):
                renames.append((view, safe_name(row['new_name'])))
        for idx, (view, desired) in enumerate(renames):
            view.Name = '__NDEV_VIEWPILOT_TMP_{0}_{1}'.format(int_id(view), idx)
        for view, desired in renames:
            view.Name = desired
            renamed.append(desired)

        for row in rows:
            source = get_view_from_string(row['id'])
            # Common scope/template/scale settings belong only to newly created
            # views. Never touch existing originals unless explicitly renamed.
            for cp in row.get('copies', []):
                method = dict(DUP_OPTIONS)[cp['method']]
                new_id = source.Duplicate(method)
                v = DOC.GetElement(new_id)
                if v is None:
                    raise RuntimeError('Revit failed to return duplicated view for ' + source.Name)
                v.Name = safe_name(cp['name'])
                if cp.get('method') == 'dependent':
                    # Revit dependent views share their parent template and scale.
                    apply_settings(v, {'scope': cp.get('scope', 'default')}, warnings)
                else:
                    apply_settings(v, cp, warnings)
                created.append(safe_text(v.Name))
        trans.Commit()
    except Exception:
        if trans.GetStatus() == DB.TransactionStatus.Started:
            trans.RollBack()
        raise
    return {'created': created, 'renamed': renamed, 'warnings': warnings}


def batch_assign(payload, mode):
    """Preflight all assignments, then atomically commit one undoable batch.

    Each change carries 'before' to detect a stale UI/project assignment.
    """
    changes = payload.get('changes', [])
    if not isinstance(changes, list) or not changes:
        raise ValueError('No changed assignments. Select views before applying.')
    if len(changes) > 10000:
        raise ValueError('Too many views in one operation.')
    if mode not in ('scope', 'template'):
        raise ValueError('Unknown batch assignment mode.')
    planned, seen = [], set()
    valid_scopes = set(int_id(el) for el in DB.FilteredElementCollector(DOC).OfCategory(
        DB.BuiltInCategory.OST_VolumeOfInterest).WhereElementIsNotElementType())
    for c in changes:
        ident = str(c.get('id', ''))
        if ident in seen:
            raise ValueError('Repeated view in assignment batch: ' + ident)
        seen.add(ident)
        view = get_view_from_string(ident)
        if view is None or not valid_view(view):
            raise ValueError('One view no longer exists. Please Refresh.')
        dest = str(c.get('to', 'none'))
        before = str(c.get('before', 'none'))
        if mode == 'scope':
            if category_for(view) not in ('Floor Plans', 'Structural Plans', 'Area Plans'):
                raise ValueError('Scope workflow supports floor, structural, and area plans only: ' + view.Name)
            p = get_param(view, DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
            if not p or p.IsReadOnly:
                raise ValueError('Scope box cannot be edited on ' + view.Name)
            actual = ('none' if p.AsElementId() == DB.ElementId.InvalidElementId
                      else str(element_id_value(p.AsElementId())))
            if dest != 'none' and int(dest) not in valid_scopes:
                raise ValueError('Scope box no longer exists for ' + view.Name)
        else:
            actual = ('none' if view.ViewTemplateId == DB.ElementId.InvalidElementId
                      else str(element_id_value(view.ViewTemplateId)))
            if dest != 'none':
                target = get_view_from_string(dest)
                if target is None or not target.IsTemplate or not view.IsValidViewTemplate(target.Id):
                    raise ValueError('View template is incompatible with ' + view.Name)
        if actual != before:
            raise ValueError('Assignment changed since opening ViewPilot: ' + view.Name + '. Refresh.')
        planned.append((view, dest))
    trans = DB.Transaction(DOC, 'NdevTools ViewPilot - Assign ' +
                           ('Scope Boxes' if mode == 'scope' else 'View Templates'))
    trans.Start()
    try:
        for view, target in planned:
            eid = DB.ElementId.InvalidElementId if target == 'none' else new_element_id(target)
            if mode == 'scope':
                view.get_Parameter(DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP).Set(eid)
            else:
                view.ViewTemplateId = eid
        trans.Commit()
    except Exception:
        if trans.GetStatus() == DB.TransactionStatus.Started:
            trans.RollBack()
        raise
    return {'count': len(planned), 'mode': mode}



def manage_entity(payload):
    """User-triggered, undoable management of existing scope boxes and templates.

    Scope-box copy/move uses ElementTransformUtils and reports Revit restrictions;
    template duplication attempts supported API operations and rolls back on
    failures, rather than fabricating a successful duplicate.
    """
    mode = safe_text(payload.get('mode', ''))
    operation = safe_text(payload.get('operation', ''))
    if mode not in ('scope', 'template') or operation not in ('rename', 'edit', 'duplicate'):
        raise ValueError('Unsupported Scope Box or View Template operation.')
    eid = new_element_id(payload.get('id'))
    item = DOC.GetElement(eid)
    if item is None:
        raise ValueError('The selected element no longer exists. Please Refresh.')
    if mode == 'template' and (not isinstance(item, DB.View) or not item.IsTemplate):
        raise ValueError('Selected item is not a View Template.')
    if mode == 'scope':
        scope_ids = set(int_id(x) for x in DB.FilteredElementCollector(DOC)
                        .OfCategory(DB.BuiltInCategory.OST_VolumeOfInterest)
                        .WhereElementIsNotElementType())
        if int_id(item) not in scope_ids:
            raise ValueError('Selected item is not a Scope Box.')
    name = safe_text(payload.get('name', '')).strip()
    if operation in ('rename', 'duplicate'):
        name = safe_name(name)
        pool = collect_model()['scopeBoxes' if mode == 'scope' else 'templates']
        if any(x['name'].lower() == name.lower() and
               (operation == 'duplicate' or x['id'] != safe_text(payload.get('id')))
               for x in pool):
            raise ValueError('Name already in use: ' + name)
    trans = DB.Transaction(DOC, 'NdevTools ViewPilot - ' + operation.title() + ' ' +
                           ('Scope Box' if mode == 'scope' else 'View Template'))
    trans.Start()
    try:
        if operation == 'rename':
            item.Name = name
            message = 'Renamed to ' + name
        elif operation == 'edit':
            if mode == 'template':
                new_scale = int(payload.get('scale', 0))
                if new_scale < 1 or new_scale > 100000:
                    raise ValueError('Scale ratio must be between 1 and 100000.')
                item.Scale = new_scale
                message = 'Updated View Template scale to 1:' + str(new_scale)
            else:
                values = payload.get('offset')
                if (not isinstance(values, list) or len(values) != 3 or
                    any(abs(float(x)) > 100000.0 for x in values)):
                    raise ValueError('Supply three safe movement offsets in feet.')
                movement = DB.XYZ(float(values[0]), float(values[1]), float(values[2]))
                DB.ElementTransformUtils.MoveElement(DOC, eid, movement)
                message = 'Moved Scope Box by X/Y/Z offsets (feet). Resizing remains available in Revit.'
        else:
            if mode == 'scope':
                # One foot shift prevents the new scope box from hiding precisely
                # over its source; Revit can reject copying certain elements.
                copied = list(DB.ElementTransformUtils.CopyElement(DOC, eid,
                                                                   DB.XYZ(1.0, 0.0, 0.0)))
                produced = [DOC.GetElement(x) for x in copied]
                scope_category = item.Category.Id if item.Category else None
                copies = [x for x in produced if x is not None and x.Category is not None
                          and scope_category is not None and x.Category.Id == scope_category]
                if not copies:
                    raise ValueError('Revit did not produce a usable Scope Box copy.')
                copies[0].Name = name
            else:
                # Some Revit view-template types cannot be duplicated by the API.
                # Check CanViewBeDuplicated, and only then try a native copy fallback.
                copy_id = None
                try:
                    if item.CanViewBeDuplicated(DB.ViewDuplicateOption.Duplicate):
                        copy_id = item.Duplicate(DB.ViewDuplicateOption.Duplicate)
                except Exception:
                    pass
                copied_view = DOC.GetElement(copy_id) if copy_id is not None else None
                if copied_view is None or not copied_view.IsTemplate:
                    try:
                        copied_ids = list(DB.ElementTransformUtils.CopyElement(DOC, eid,
                                                                               DB.XYZ.Zero))
                        matched = [DOC.GetElement(x) for x in copied_ids]
                        matching = [x for x in matched if isinstance(x, DB.View) and x.IsTemplate]
                        copied_view = matching[0] if matching else None
                    except Exception as exc:
                        raise ValueError('Revit API does not permit duplicating this template: ' + safe_text(exc))
                if copied_view is None or not copied_view.IsTemplate:
                    raise ValueError('Revit cannot duplicate this template type. No changes were committed.')
                copied_view.Name = name
            message = 'Created duplicate: ' + name
        trans.Commit()
    except Exception:
        if trans.GetStatus() == DB.TransactionStatus.Started:
            trans.RollBack()
        raise
    return {'message': message, 'mode': mode, 'operation': operation}


def open_external_url(url):
    """UseShellExecute fixes URL launching on modern .NET / Windows systems."""
    psi = ProcessStartInfo(url)
    psi.UseShellExecute = True
    Process.Start(psi)


class HelpWindow(Form):
    """Native separate, offline Help dialog; links open only on user click."""
    def __init__(self):
        Form.__init__(self)
        self.Text = 'NdevTools ViewPilot | Help — Created by Nataraj Devaraj'
        self.StartPosition = FormStartPosition.CenterParent
        self.MinimumSize = Size(640, 520)
        self.Size = Size(800, 640)
        self.helpweb = WebBrowser()
        self.helpweb.Dock = DockStyle.Fill
        self.helpweb.ScriptErrorsSuppressed = True
        self.helpweb.IsWebBrowserContextMenuEnabled = True
        self.helpweb.AllowNavigation = False
        self.Controls.Add(self.helpweb)
        self.helpweb.DocumentText = '''<!doctype html><html><head><meta http-equiv="X-UA-Compatible" content="IE=edge" />
        <style>body{font:15px 'Segoe UI',Arial;background:#061a2c;color:#e5f5ff;
        padding:20px;line-height:1.65}h2,h3{color:#10d5ec}code{color:#67ddf9}
        .box{border:1px solid #195c78;padding:12px;margin:12px 0;border-radius:6px}
        </style></head><body><h2>ViewPilot Help</h2><h3>Created by Nataraj Devaraj</h3>
        <div class="box"><h3>Rename &amp; Duplicate</h3>
        Check views, edit names, choose a Revit-supported duplicate method, set copy counts and per-copy settings, then click Apply Changes. Check the conflict preview before committing.</div>
        <div class="box"><h3>Scope Boxes</h3>
        Choose a project scope box, click Select Views, check compatible floor, structural or area plans, then Add Selected Views. Review assignments before Apply Scope Changes. Remove frees a view to assign elsewhere.</div>
        <div class="box"><h3>View Templates</h3>
        Choose a project template and add compatible views using checkboxes. Apply Template Changes writes the previewed assignments in one Revit transaction.</div>
        <div class="box"><h3>Cleanup Tools</h3>
        Run Health Check to review missing view templates, mixed scales, scope assignments and unplaced dependent views. This scan is read-only.</div>
        <div class="box"><h3>Settings &amp; Saved Setups</h3>
        BIM Humor is enabled by default. Funny messages appear only while new views are being created. Saved Setups store UI defaults locally on this computer.</div>
        <div class="box"><h3>Duplicate method guide</h3>
        <b>Duplicate:</b> independent view. <b>With Detailing:</b> includes supported annotations. <b>As Dependent:</b> shares properties with its original view, where Revit supports it.</div>
        <div class="box"><h3>&#9733; Support NdevTools</h3>
        Enjoying ViewPilot? Please consider giving the NdevTools project a star on GitHub!
        Have suggestions, feedback, or feature requests? Feel free to share them on GitHub or connect on LinkedIn.<br>
        <b>Created by Nataraj Devaraj</b><br><b>github.com/ndev16/NdevTools</b><br><b>linkedin.com/in/nataraj016/</b></div>
        <p>ViewPilot runs offline. GitHub opens only when you explicitly select its button below.</p>
        </body></html>'''
        self.footer = FlowLayoutPanel()
        self.footer.Dock = DockStyle.Bottom
        self.footer.Height = 56
        self.footer.FlowDirection = FlowDirection.LeftToRight
        self.Controls.Add(self.footer)
        self.star = Button()
        self.star.Text = 'Star NdevTools on GitHub'
        self.star.Width = 205
        self.star.Height = 35
        self.star.Click += lambda sender, args: open_external_url(HELP_URL)
        self.footer.Controls.Add(self.star)
        self.report = Button()
        self.report.Text = 'Report an Issue'
        self.report.Width = 150
        self.report.Height = 35
        self.report.Click += lambda sender, args: open_external_url(ISSUES_URL)
        self.footer.Controls.Add(self.report)
        if LINKEDIN_URL:
            self.linkedin = Button()
            self.linkedin.Text = 'Connect on LinkedIn'
            self.linkedin.Width = 178
            self.linkedin.Height = 35
            self.linkedin.Click += lambda sender, args: open_external_url(LINKEDIN_URL)
            self.footer.Controls.Add(self.linkedin)
        self.closebtn = Button()
        self.closebtn.Text = 'Close'
        self.closebtn.Width = 100
        self.closebtn.Height = 35
        self.closebtn.Click += lambda sender, args: self.Close()
        self.footer.Controls.Add(self.closebtn)


def run_healthcheck():
    """Read-only checks; informational diagnostics are not automatic fixes."""
    data = collect_model()
    views = data['views']
    untemplated = []
    noscope = []
    dependents_unplaced = []
    scales = {}
    for v in views:
        if v['category'] not in ('Legends', 'Schedules', 'Drafting Views') and v['template'] == 'none':
            untemplated.append(v['name'])
        if v['can_scope'] and v['scope'] == 'none':
            noscope.append(v['name'])
        if v['dependent'] and not v['sheet']:
            dependents_unplaced.append(v['name'])
        if v['scale'] > 0 and v['category'] not in ('Legends', 'Schedules'):
            scales.setdefault(v['category'], []).append((v['name'], v['scale']))
    inconsistent = [safe_text(cat) + ' — ' + safe_text(name) + ' (1:' + str(scale) + ')'
                    for cat, values in scales.items()
                    if len(set(pair[1] for pair in values)) > 1
                    for name, scale in values]
    suspicious_names = [v['name'] for v in views if re.search(r'(?i)(?:\bcopy\b|\bunnamed\b)', v['name'])]
    return {'checks': [
        {'title': 'Potential Temporary / Copy Names', 'level': 'info',
         'detail': 'Views containing Copy or Unnamed may need review.',
         'count': len(suspicious_names), 'examples': suspicious_names},
        {'title': 'Missing View Templates', 'level': 'warning',
         'detail': 'Unassigned templates are not necessarily errors.',
         'count': len(untemplated), 'examples': untemplated},
        {'title': 'Mixed Scales by View Type', 'level': 'info',
         'detail': 'Mixed scales may be intentional. Review by discipline.',
         'count': len(inconsistent), 'examples': inconsistent},
        {'title': 'Unplaced Dependent Views', 'level': 'info',
         'detail': 'Dependent views not placed on any sheet.',
         'count': len(dependents_unplaced), 'examples': dependents_unplaced},
        {'title': 'Views Without Scope Box', 'level': 'info',
         'detail': 'Only includes views with a scope box parameter.',
         'count': len(noscope), 'examples': noscope},
    ]}


class ViewPilotWindow(Form):
    def __init__(self):
        Form.__init__(self)
        self.Text = 'NdevTools | ViewPilot'
        self.StartPosition = FormStartPosition.CenterScreen
        self.MinimumSize = Size(1080, 660)
        self.Size = Size(1520, 870)
        self.WindowState = FormWindowState.Maximized
        self.web = WebBrowser()
        self.web.Dock = DockStyle.Fill
        self.web.ScriptErrorsSuppressed = True
        self.web.IsWebBrowserContextMenuEnabled = True
        self.web.AllowWebBrowserDrop = False
        self.web.WebBrowserShortcutsEnabled = True
        self.Controls.Add(self.web)
        self.web.Navigating += self.on_navigating
        self.web.DocumentCompleted += self.on_loaded
        self.FormClosing += self.on_closing
        self.loaded = False
        self._inject_ui()

    def on_closing(self, sender, args):
        # Stop local UI timers before the embedded document is disposed.
        self.call_js('disposeViewPilot', {})

    def _inject_ui(self):
        with codecs.open(os.path.join(UI_DIR, 'index.html'), 'r', 'utf-8') as f:
            html = f.read()
        with codecs.open(os.path.join(UI_DIR, 'style.css'), 'r', 'utf-8') as f:
            css = f.read()
        with codecs.open(os.path.join(UI_DIR, 'app.js'), 'r', 'utf-8') as f:
            js = f.read()
        with open(os.path.join(UI_DIR, 'assets', 'ndevtools-logo.png'), 'rb') as f:
            logo_b64 = base64.b64encode(f.read())
        if not isinstance(logo_b64, str):
            logo_b64 = logo_b64.decode('ascii')
        html = html.replace('/* INLINE_STYLE */', css)
        html = html.replace('/* INLINE_SCRIPT */', 'window.__inRevitHost = true;\n' + js)
        html = html.replace('INLINE_LOGO_DATA', logo_b64)
        self.web.DocumentText = html

    def call_js(self, method, data):
        if self.web.Document is None:
            return
        try:
            self.web.Document.InvokeScript(method, Array[Object]([json.dumps(data, ensure_ascii=True)]))
        except Exception as exc:
            print('ViewPilot UI call failed: {0}: {1}'.format(method, exc))

    def on_loaded(self, sender, args):
        # DocumentCompleted may also run for subframes. Load once.
        if self.loaded:
            return
        if self.web.Document is None:
            return
        try:
            if self.web.Document.GetElementById('viewRows') is None:
                return
        except Exception:
            return
        self.loaded = True
        try:
            self.call_js('setHostData', collect_model())
        except Exception as exc:
            MessageBox.Show(str(exc), 'ViewPilot: Project Read Failed')

    def on_navigating(self, sender, args):
        url = safe_text(args.Url) if args.Url else ''
        if 'ndevpilot.invalid/bridge' not in url:
            return
        args.Cancel = True
        if self.web.Document is None:
            return
        raw = ''
        try:
            el = self.web.Document.GetElementById('bridge_payload')
            raw = safe_text(el.InnerText) if el else ''
            message = json.loads(raw)
            action = message.get('action', '')
            payload = message.get('payload', {})
            self.route_action(action, payload)
        except Exception as exc:
            self.call_js('hostError', {'message': safe_text(exc)})
            print('ViewPilot bridge failure:\n' + traceback.format_exc())

    def route_action(self, action, payload):
        if action == 'refresh':
            self.call_js('setHostData', collect_model())
        elif action == 'health':
            self.call_js('showHealthResults', run_healthcheck())
        elif action in ('assign_scope', 'assign_template'):
            try:
                result = batch_assign(payload, 'scope' if action == 'assign_scope' else 'template')
                self.call_js('showAssignmentResults', result)
                self.call_js('setHostData', collect_model())
            except Exception as exc:
                self.call_js('hostError', {'message': safe_text(exc)})
                print('ViewPilot assignment failure:\n' + traceback.format_exc())
        elif action == 'manage_entity':
            try:
                result = manage_entity(payload)
                self.call_js('v5ManageResults', result)
                self.call_js('setHostData', collect_model())
            except Exception as exc:
                self.call_js('hostError', {'message': safe_text(exc)})
                print('ViewPilot management failure:\n' + traceback.format_exc())
        elif action == 'help':
            HelpWindow().ShowDialog(self)
        elif action == 'apply':
            try:
                result = apply_job(payload)
                result['success'] = True
                self.call_js('showApplyResults', result)
                self.call_js('setHostData', collect_model())
            except Exception as exc:
                self.call_js('hostError', {'message': safe_text(exc)})
                print('ViewPilot apply failure:\n' + traceback.format_exc())
        elif action == 'save_preset':
            name = safe_text(payload.get('name', '')).strip()
            if not name or len(name) > 80:
                raise ValueError('Preset name must contain 1-80 characters.')
            presets = read_json(PRESET_FILE, {})
            presets[name] = payload.get('settings', {})
            save_json(PRESET_FILE, presets)
            self.call_js('setPresets', presets)
        elif action == 'delete_preset':
            presets = read_json(PRESET_FILE, {})
            presets.pop(safe_text(payload.get('name', '')), None)
            save_json(PRESET_FILE, presets)
            self.call_js('setPresets', presets)
        elif action == 'save_settings':
            settings = {'humor': bool(payload.get('humor', True))}
            save_json(SETTINGS_FILE, settings)
        elif action == 'github':
            open_external_url(HELP_URL)
        elif action == 'issues':
            open_external_url(ISSUES_URL)
        elif action == 'minimize':
            self.WindowState = FormWindowState.Minimized
        elif action == 'close':
            self.Close()


if __name__ == '__main__':
    if APP_VERSION not in SUPPORTED:
        MessageBox.Show('Targeted for Revit 2022-2027; current version: ' + APP_VERSION,
                        'NdevTools ViewPilot')
    elif DOC is None or DOC.IsFamilyDocument:
        MessageBox.Show('ViewPilot requires an active Revit project document.',
                        'NdevTools ViewPilot')
    else:
        dialog = ViewPilotWindow()
        dialog.ShowDialog()
