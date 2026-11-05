# -*- coding: utf-8 -*-
"""Atomic sheet-placement moves. Public coordinates are Revit sheet feet."""
import math
import os
from pyrevit import DB
from pyrevit.compat import get_elementid_value_func
from System.Collections.Generic import List

TOLERANCE = 1e-6
_id_value = get_elementid_value_func()
DETAIL_VIEWS = ('FloorPlan', 'EngineeringPlan', 'AreaPlan', 'CeilingPlan', 'Section', 'Elevation', 'Detail', 'DraftingView')
try:
    text_type = unicode
except NameError:
    text_type = str


def _sheet_id(element):
    return element.SheetId if isinstance(element, DB.Viewport) else element.OwnerViewId


def supported(doc, element):
    if element is None or not element.IsValidObject or not doc.Equals(element.Document):
        return False
    if element.Pinned or element.GroupId != DB.ElementId.InvalidElementId:
        return False
    if not isinstance(doc.GetElement(_sheet_id(element)), DB.ViewSheet):
        return False
    if isinstance(element, DB.Viewport):
        return isinstance(doc.GetElement(element.ViewId), DB.View)
    if isinstance(element, DB.ScheduleSheetInstance):
        view = doc.GetElement(element.ScheduleId)
        return (isinstance(view, DB.ViewSchedule) and not element.IsTitleblockRevisionSchedule and
                not view.IsInternalKeynoteSchedule and not view.IsTitleblockRevisionSchedule and
                not view.Definition.IsFilteredBySheet)
    if isinstance(element, (DB.TextNote, DB.FilledRegion)):
        return True
    if isinstance(element, DB.FamilyInstance):
        return (element.Category is not None and _id_value(element.Category.Id) in
                (int(DB.BuiltInCategory.OST_GenericAnnotation), int(DB.BuiltInCategory.OST_DetailComponents)) and
                element.SuperComponent is None and element.Host is None)
    return False


def item_anchor(element):
    if isinstance(element, DB.Viewport):
        return element.GetBoxCenter()
    if isinstance(element, DB.ScheduleSheetInstance):
        return element.Point
    if isinstance(element, DB.TextNote):
        return element.Coord
    location = element.Location
    if isinstance(location, DB.LocationPoint):
        return location.Point
    if isinstance(location, DB.LocationCurve):
        return location.Curve.Evaluate(0.5, True)
    box = element.get_BoundingBox(element.Document.GetElement(element.OwnerViewId))
    if box is None:
        raise ValueError('This item has no measurable position on its sheet.')
    return box.Transform.OfPoint((box.Min + box.Max).Multiply(0.5))


def _require_position(element, target):
    actual = item_anchor(element)
    if abs(actual.X-target.X) > TOLERANCE or abs(actual.Y-target.Y) > TOLERANCE:
        raise ValueError('Revit moved an item away from the requested sheet position.')


def _detail(element):
    return element.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)


def _parameter_value(parameter):
    return {'String': parameter.AsString, 'Integer': parameter.AsInteger,
            'Double': parameter.AsDouble, 'ElementId': parameter.AsElementId}[str(parameter.StorageType)]()


def _placement_data(element):
    params = []
    for p in element.Parameters:
        pid = _id_value(p.Id)
        if (p.IsReadOnly or not p.HasValue or str(p.StorageType) == 'None' or
                (pid < 0 and pid != int(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS))):
            continue
        params.append((p.Definition, _parameter_value(p)))
    from Autodesk.Revit.DB.ExtensibleStorage import Schema
    entities = [element.GetEntity(Schema.Lookup(guid)) for guid in element.GetEntitySchemaGuids()]
    return params, entities


def _restore_data(element, data):
    params, entities = data
    for definition, value in params:
        parameter = element.get_Parameter(definition)
        if parameter is None:
            raise ValueError('A placement parameter is missing on the destination.')
        if _parameter_value(parameter) != value:
            if parameter.IsReadOnly or not parameter.Set(value) or _parameter_value(parameter) != value:
                raise ValueError('Cannot preserve placement parameter ' + definition.Name + '.')
    for entity in entities:
        if not entity.IsValid():
            raise ValueError('This placement has inaccessible application data.')
        element.SetEntity(entity)


def _safe_delete(doc, element):
    allowed = {element.Id}
    if isinstance(element, DB.FilledRegion):
        # Filled-region boundaries belong to its private sketch. Keep independent
        # sheet lines, tags, dimensions and all other dependent elements intact.
        for eid in element.GetDependentElements(None):
            child = doc.GetElement(eid)
            if isinstance(child, DB.Sketch):
                allowed.add(eid)
                allowed.update(child.GetAllElements())
    removed = set(doc.Delete(element.Id))
    if not removed.issubset(allowed):
        raise ValueError('Moving this item would delete an additional dependent element.')


def _duplicate_view(doc, view, option):
    if not view.CanViewBeDuplicated(option):
        raise ValueError(u'Revit does not allow {} for "{}".'.format(option, view.Name))
    duplicate_id = view.Duplicate(option)
    if duplicate_id == DB.ElementId.InvalidElementId or duplicate_id == view.Id:
        raise ValueError(u'Revit returned no independent copy of "{}" for {}.'.format(view.Name, option))
    doc.Regenerate()
    duplicate = doc.GetElement(duplicate_id)
    if not isinstance(duplicate, DB.View):
        raise ValueError(u'Revit could not resolve the new view for "{}".'.format(view.Name))
    if duplicate.GetPrimaryViewId() != DB.ElementId.InvalidElementId:
        duplicate.ConvertToIndependent()
    source_type = view.GetTypeId()
    if duplicate.GetTypeId() != source_type and duplicate.IsValidType(source_type):
        replacement = duplicate.ChangeTypeId(source_type)
        if replacement != DB.ElementId.InvalidElementId:
            duplicate = doc.GetElement(replacement)
    if duplicate.ViewType != view.ViewType or duplicate.GetTypeId() != source_type:
        raise ValueError(u'Revit could not retain the view family type of "{}" on its independent copy.'.format(view.Name))
    if duplicate.GetPrimaryViewId() != DB.ElementId.InvalidElementId:
        raise ValueError('Revit did not create an independent view.')
    # A blank title defaults to the view name. Preserve the printed title even
    # though the duplicate receives its own distinct name in the Project Browser.
    parameter_id = DB.BuiltInParameter.VIEW_DESCRIPTION
    old_title = view.get_Parameter(parameter_id)
    if old_title is not None:
        title = old_title.AsString() or view.Name
        new_title = duplicate.get_Parameter(parameter_id)
        if new_title is None or ((new_title.AsString() or duplicate.Name) != title and
                                 (new_title.IsReadOnly or not new_title.Set(title))):
            raise ValueError(u'Cannot preserve the sheet title of "{}".'.format(view.Name))
    doc.Regenerate()
    return duplicate.Id


def _copy_view_id(doc, view, target, choices):
    kind = str(view.ViewType)
    if kind in DETAIL_VIEWS:
        mode = 'detail'
    elif kind == 'ThreeD':
        mode = 'duplicate'
    elif kind in ('Legend', 'ColumnSchedule'):
        mode = choices.get(view.UniqueId)
        if mode == 'skip':
            raise ValueError('Skipped by request.')
        if mode not in ('share', 'detail', 'duplicate'):
            raise ValueError(u'Choose Share, Duplicate with detailing, Duplicate, or Skip for "{}".'.format(view.Name))
    else:
        raise ValueError('Copy is unavailable for view type {}.'.format(kind))
    if mode == 'share':
        if not DB.Viewport.CanAddViewToSheet(doc, target.Id, view.Id):
            raise ValueError(u'Revit cannot place the original "{}" on this destination sheet.'.format(view.Name))
        return view.Id
    option = DB.ViewDuplicateOption.WithDetailing if mode == 'detail' else DB.ViewDuplicateOption.Duplicate
    return _duplicate_view(doc, view, option)


def _transfer_viewport(doc, old, target, point, choices=None):
    view_id, type_id = old.ViewId, old.GetTypeId()
    rotation, label_offset, label_length = old.Rotation, old.LabelOffset, old.LabelLineLength
    positioning = old.ViewportPositioning
    # Before Revit 2026 the swap positioning setting exists without a ViewAnchor.
    anchor = getattr(old, 'ViewAnchor', None)
    number = _detail(old).AsString()
    data = _placement_data(old)
    if choices is not None:
        view_id = _copy_view_id(doc, doc.GetElement(view_id), target, choices)
    else:
        _safe_delete(doc, old)
        doc.Regenerate()
    if not DB.Viewport.CanAddViewToSheet(doc, target.Id, view_id):
        raise ValueError('This view cannot be placed on the destination sheet.')
    placed = DB.Viewport.Create(doc, target.Id, view_id, point)
    if placed is None:
        raise ValueError('Revit could not create the destination viewport.')
    if placed.GetTypeId() != type_id:
        changed = placed.ChangeTypeId(type_id)
        if changed != DB.ElementId.InvalidElementId:
            placed = doc.GetElement(changed)
    if placed.Rotation != rotation:
        placed.Rotation = rotation
    if placed.ViewportPositioning != positioning:
        placed.ViewportPositioning = positioning
    if anchor is not None and placed.ViewAnchor != anchor:
        placed.SetViewAnchorAndPosition(anchor, placed.GetPositionAtViewAnchor(anchor))
    placed.LabelOffset = label_offset
    placed.LabelLineLength = label_length
    _restore_data(placed, data)
    doc.Regenerate()
    placed.SetBoxCenter(point)
    if (placed.ViewId != view_id or placed.GetTypeId() != type_id or placed.Rotation != rotation or
            placed.ViewportPositioning != positioning or (anchor is not None and placed.ViewAnchor != anchor) or
            placed.LabelOffset.DistanceTo(label_offset) > TOLERANCE or
            abs(placed.LabelLineLength - label_length) > TOLERANCE):
        raise ValueError('Revit could not preserve the viewport settings.')
    return placed, number


def _transfer_schedule(doc, old, target, point):
    view_id, segment, rotation = old.ScheduleId, old.SegmentIndex, old.Rotation
    type_id = old.GetTypeId()
    data = _placement_data(old)
    _safe_delete(doc, old)
    doc.Regenerate()
    view = doc.GetElement(view_id)
    if view is None:
        raise ValueError('Revit would remove the underlying schedule.')
    if view.GetSegmentCount() > 1 and segment >= 0:
        placed = DB.ScheduleSheetInstance.Create(doc, target.Id, view_id, point, segment)
    else:
        placed = DB.ScheduleSheetInstance.Create(doc, target.Id, view_id, point)
    if placed.Rotation != rotation:
        placed.Rotation = rotation
    placed.Point = point
    _restore_data(placed, data)
    if (placed.ScheduleId != view_id or placed.GetTypeId() != type_id or placed.Rotation != rotation or
            (view.GetSegmentCount() > 1 and placed.SegmentIndex != segment)):
        raise ValueError('Revit could not preserve the schedule placement.')
    return placed


def _transfer_annotation(doc, old, source, target, point, keep_source=False):
    ids = List[DB.ElementId]()
    ids.Add(old.Id)
    options = DB.CopyPasteOptions()
    try:
        copied = DB.ElementTransformUtils.CopyElements(source, ids, target, DB.Transform.Identity, options)
    finally:
        options.Dispose()
    matches = [doc.GetElement(eid) for eid in copied]
    matches = [e for e in matches if e is not None and e.GetType() == old.GetType() and
               e.OwnerViewId == target.Id and e.GetTypeId() == old.GetTypeId()]
    if len(matches) != 1:
        raise ValueError('Revit could not identify the copied sheet annotation.')
    placed = matches[0]
    doc.Regenerate()
    if isinstance(old, DB.TextNote):
        if (placed.Text != old.Text or placed.LeaderCount != old.LeaderCount or
                not placed.BaseDirection.IsAlmostEqualTo(old.BaseDirection) or not placed.UpDirection.IsAlmostEqualTo(old.UpDirection)):
            raise ValueError('The copied text note differs from the original.')
    elif isinstance(old, DB.FamilyInstance):
        before_axes, after_axes = old.GetTransform(), placed.GetTransform()
        if (not before_axes.BasisX.IsAlmostEqualTo(after_axes.BasisX) or
                not before_axes.BasisY.IsAlmostEqualTo(after_axes.BasisY)):
            raise ValueError('The copied annotation has a different orientation.')
    before = item_anchor(placed)
    DB.ElementTransformUtils.MoveElement(doc, placed.Id, DB.XYZ(point.X-before.X, point.Y-before.Y, 0))
    if not keep_source:
        _safe_delete(doc, old)
    return placed


def _assign_numbers(doc, target, requests):
    if not requests:
        return
    moving = set(v.Id for v, number in requests)
    taken = set(_detail(doc.GetElement(i)).AsString() for i in target.GetAllViewports() if i not in moving)
    to_set = [(v, number) for v, number in requests if number and number not in taken]
    # Release automatically assigned numbers first so simultaneous swaps work.
    import uuid
    changes = [(v, number) for v, number in to_set if _detail(v).AsString() != number]
    reserved = set(number for v, number in to_set)
    for v, number in requests:
        if (v, number) not in to_set and _detail(v).AsString() in reserved:
            free = 1
            used = set(_detail(doc.GetElement(i)).AsString() for i in target.GetAllViewports()) | reserved
            while str(free) in used:
                free += 1
            if not _detail(v).Set(str(free)):
                raise ValueError('Cannot allocate a unique viewport detail number.')
    for v, number in changes:
        if not _detail(v).Set('NDEV-' + uuid.uuid4().hex):
            raise ValueError('Cannot prepare destination viewport detail numbers.')
    for v, number in changes:
        if not _detail(v).Set(number):
            raise ValueError('Cannot preserve the original viewport detail number.')


class _Failures(DB.IFailuresPreprocessor):
    def __init__(self):
        self.messages = []

    def PreprocessFailures(self, accessor):
        for failure in accessor.GetFailureMessages():
            if failure.GetSeverity() == DB.FailureSeverity.Warning:
                # Warnings are returned by Revit without forcing a modal response.
                continue
            self.messages.append(failure.GetDescriptionText())
        return DB.FailureProcessingResult.ProceedWithRollBack if self.messages else DB.FailureProcessingResult.Continue


def move(doc, source_uid, target_uid, item_uids, dx, dy, transaction_name='Move Views'):
    return _transfer(doc, source_uid, target_uid, item_uids, dx, dy, transaction_name, None, None)


def copy_items(doc, source_uid, target_uid, item_uids, dx, dy, choices=None, skipped=None):
    return _transfer(doc, source_uid, target_uid, item_uids, dx, dy, 'Paste Copies', choices or {}, skipped)


def _copy_schedule(doc, old, target, point, cache):
    import imp
    import sys
    name = '_ndev_main_move_views_schedule_copy'
    helper = sys.modules.get(name)
    if helper is None:
        helper = imp.load_source(name, os.path.join(os.path.dirname(__file__), 'sheet_schedule_copy.py'))
    placed = helper.copy_schedule(doc, old, target, point, cache)
    _restore_data(placed, _placement_data(old))
    return placed


def _place(doc, source, target, old, point, choices, cache):
    copying = choices is not None
    overrides = source.GetElementOverrides(old.Id) if source.AreGraphicsOverridesAllowed() else None
    try:
        number = None
        if isinstance(old, DB.Viewport):
            placed, number = _transfer_viewport(doc, old, target, point, choices)
        elif isinstance(old, DB.ScheduleSheetInstance):
            placed = _copy_schedule(doc, old, target, point, cache) if copying else _transfer_schedule(doc, old, target, point)
        else:
            placed = _transfer_annotation(doc, old, source, target, point, copying)
        if overrides is not None:
            target.SetElementOverrides(placed.Id, overrides)
        return placed, number
    finally:
        if overrides is not None:
            overrides.Dispose()


def _expected_copy_failure(error):
    if isinstance(error, ValueError):
        return True
    return hasattr(error, 'GetType') and error.GetType().FullName in (
        'Autodesk.Revit.Exceptions.ArgumentException', 'Autodesk.Revit.Exceptions.ArgumentOutOfRangeException',
        'Autodesk.Revit.Exceptions.InvalidOperationException')


def _copy_one(doc, source, target, old, point, delta, choices, cache, omissions):
    uid = old.UniqueId
    attempt = DB.SubTransaction(doc)
    item_cache = dict(cache)
    try:
        attempt.Start()
        placed, number = _place(doc, source, target, old, point, choices, item_cache)
        doc.Regenerate()
        if not old.IsValidObject or old.Id == placed.Id or _sheet_id(old) != source.Id or _sheet_id(placed) != target.Id:
            raise RuntimeError('Copy did not preserve the source or created a placement on the wrong sheet.')
        _require_position(old, point-delta)
        _require_position(placed, point)
        if attempt.Commit() != DB.TransactionStatus.Committed:
            raise RuntimeError('Revit could not finish copying a sheet item.')
        cache.update(item_cache)
        return placed, number
    except Exception as error:
        if attempt.GetStatus() == DB.TransactionStatus.Started:
            attempt.RollBack()
        if not _expected_copy_failure(error):
            raise
        omissions.append((uid, getattr(error, 'Message', None) or text_type(error)))
        return None, None
    finally:
        attempt.Dispose()


def _transfer(doc, source_uid, target_uid, item_uids, dx, dy, transaction_name, choices, skipped):
    if doc is None or doc.IsReadOnly or doc.IsFamilyDocument or doc.IsModifiable:
        raise ValueError('Open a writable project with no active transaction.')
    dx, dy = float(dx), float(dy)
    if any(math.isnan(v) or math.isinf(v) for v in (dx, dy)):
        raise ValueError('Enter finite sheet offsets.')
    source, target = doc.GetElement(source_uid), doc.GetElement(target_uid)
    if any(not isinstance(s, DB.ViewSheet) or s.IsPlaceholder for s in (source, target)):
        raise ValueError('Choose two available drawing sheets.')
    uids = list(item_uids)
    if not uids or len(set(uids)) != len(uids):
        raise ValueError('Select one or more distinct sheet items.')
    delta = DB.XYZ(dx, dy, 0)
    copying = choices is not None
    plans, omissions = [], []
    for uid in uids:
        try:
            element = doc.GetElement(uid)
            if element is None or not element.IsValidObject:
                raise ValueError('The selected placement no longer exists.')
            if _sheet_id(element) != source.Id:
                raise ValueError('The selected placement belongs to another sheet.')
            if element.Pinned or element.GroupId != DB.ElementId.InvalidElementId:
                raise ValueError('The selected placement is pinned or belongs to a model group.')
            if not supported(doc, element):
                raise ValueError('Unsupported sheet item: {}.'.format(element.GetType().Name))
            plans.append((uid, element, item_anchor(element) + delta))
        except Exception as error:
            if not copying or not _expected_copy_failure(error):
                raise
            omissions.append((uid, getattr(error, 'Message', None) or text_type(error)))
    if not plans:
        if skipped is not None:
            skipped.extend(omissions)
        return {}
    move_in_place = source.Id == target.Id and not copying
    if move_in_place and dx == 0 and dy == 0:
        return dict((uid, uid) for uid in uids)
    tx = DB.Transaction(doc, transaction_name)
    failures = _Failures()
    result, numbers, cache = {}, [], {}
    try:
        tx.Start()
        options = tx.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(failures)
        options.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(options)
        if move_in_place:
            ids = List[DB.ElementId]()
            for uid, element, point in plans:
                ids.Add(element.Id)
            DB.ElementTransformUtils.MoveElements(doc, ids, delta)
        for uid, old, point in plans:
            if move_in_place:
                placed, number = old, None
            elif copying:
                placed, number = _copy_one(doc, source, target, old, point, delta, choices, cache, omissions)
                if placed is None:
                    continue
            else:
                placed, number = _place(doc, source, target, old, point, None, cache)
            if number is not None:
                numbers.append((placed, number))
            result[uid] = placed.UniqueId
        if not result:
            tx.RollBack()
            if skipped is not None:
                skipped.extend(omissions)
            return {}
        _assign_numbers(doc, target, numbers)
        doc.Regenerate()
        for uid, old, point in plans:
            if uid not in result:
                continue
            placed = doc.GetElement(result[uid])
            if _sheet_id(placed) != target.Id or (not move_in_place and not copying and doc.GetElement(uid) is not None):
                raise ValueError('Sheet ownership verification failed.')
            _require_position(placed, point)
            if copying:
                original = doc.GetElement(uid)
                if original is None or _sheet_id(original) != source.Id or original.Id == placed.Id:
                    raise ValueError('Source preservation verification failed.')
                _require_position(original, point - delta)
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Revit rolled back the sheet operation. ' + ' '.join(failures.messages))
        if skipped is not None:
            skipped.extend(omissions)
        return result
    except Exception:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        raise
    finally:
        tx.Dispose()
