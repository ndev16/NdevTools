# -*- coding: utf-8 -*-
"""Native move regression. Creates an unsaved document without opening the user's project."""
import imp
import json
import os
import shutil
import tempfile
import traceback
from pyrevit import DB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
engine = imp.load_source('ndev_main_sheet_moves_native_test', os.path.join(ROOT, 'sheet_moves.py'))
app = __revit__.Application
result = {'version': app.VersionNumber, 'passed': False, 'checks': []}
doc = None
events = []


def changed(sender, args):
    if doc is not None and args.GetDocument().Equals(doc) and str(args.Operation) == 'TransactionCommitted':
        events.extend(list(args.GetTransactionNames()))


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    result['checks'].append(name)


def closed(p, q):
    return abs(p.X-q.X) < 1e-5 and abs(p.Y-q.Y) < 1e-5


def copy_regression(source, target, items, viewport, draft, schedule_placement, notes):
    source_uids = [e.UniqueId for e in items]
    original = dict((e.UniqueId, engine.item_anchor(e)) for e in items)
    source_text = sorted(t.Text for t in DB.FilteredElementCollector(doc).OwnedByView(draft.Id).OfClass(DB.TextNote))
    assert source_text, 'Source drafting view needs a detail annotation.'
    group = DB.TransactionGroup(doc, 'Isolate copy regression')
    group.Start()
    try:
        for title, sheet, delta in (('cross-sheet', target, DB.XYZ(2, -3, 0)),
                                   ('zero-offset same-sheet', source, DB.XYZ.Zero)):
            events[:] = []
            copied = engine.copy_items(doc, source.UniqueId, sheet.UniqueId, source_uids, delta.X, delta.Y)
            check(title + ' copy adds new IDs and keeps original positions', set(copied) == set(source_uids) and
                  set(copied.values()).isdisjoint(source_uids) and len(set(copied.values())) == len(source_uids) and
                  all(closed(engine.item_anchor(doc.GetElement(u)), original[u]) and
                      closed(engine.item_anchor(doc.GetElement(copied[u])), original[u]+delta) for u in source_uids))
            check(title + ' copy has one Paste Copies undo step', events == ['Paste Copies'])
            new_vp = doc.GetElement(copied[viewport.UniqueId])
            duplicate = doc.GetElement(new_vp.ViewId)
            copied_notes = list(DB.FilteredElementCollector(doc).OwnedByView(duplicate.Id).OfClass(DB.TextNote))
            title_parameter = DB.BuiltInParameter.VIEW_DESCRIPTION
            result.setdefault('copy_view_details', {})[title] = {
                'new_view': duplicate.Id != draft.Id, 'texts': [e.Text for e in copied_notes],
                'duplicate_title': duplicate.get_Parameter(title_parameter).AsString(),
                'source_title': draft.get_Parameter(title_parameter).AsString() or draft.Name,
                'new_label': [new_vp.LabelOffset.X, new_vp.LabelOffset.Y, new_vp.LabelLineLength],
                'old_label': [viewport.LabelOffset.X, viewport.LabelOffset.Y, viewport.LabelLineLength],
                'same_type': new_vp.GetTypeId() == viewport.GetTypeId(), 'same_rotation': new_vp.Rotation == viewport.Rotation}
            check(title + ' drafting duplicate retains view detail, sheet title, type and rotation',
                  duplicate.Id != draft.Id and sorted(t.Text for t in copied_notes) == source_text and
                  duplicate.get_Parameter(title_parameter).AsString() == (draft.get_Parameter(title_parameter).AsString() or draft.Name)
                  and new_vp.Rotation == viewport.Rotation and new_vp.GetTypeId() == viewport.GetTypeId() and
                  closed(new_vp.LabelOffset, viewport.LabelOffset) and abs(new_vp.LabelLineLength-viewport.LabelLineLength)<1e-6)
            copied_schedule = doc.GetElement(copied[schedule_placement.UniqueId])
            check(title + ' duplicates independent schedule and preserves annotation text', copied_schedule.ScheduleId != schedule_placement.ScheduleId and
                  all(doc.GetElement(copied[e.UniqueId]).Text == e.Text for e in notes))
            plan_copy = doc.GetElement(doc.GetElement(copied[plan_placement.UniqueId]).ViewId)
            plan_notes = [n.Text for n in DB.FilteredElementCollector(doc).OwnedByView(plan_copy.Id).OfClass(DB.TextNote)]
            check(title + ' independent floor plan contains original detailing',
                  plan_copy.Id != plan.Id and plan_copy.GetPrimaryViewId() == DB.ElementId.InvalidElementId and
                  plan_note.Text in plan_notes)
        before = set(e.UniqueId for e in DB.FilteredElementCollector(doc).OfClass(DB.View))
        group_viewport = engine._transfer_viewport
        attempted = []
        def unsupported_after_duplicate(*args):
            placed, unused = group_viewport(*args)
            attempted.extend([placed.UniqueId, doc.GetElement(placed.ViewId).UniqueId])
            raise ValueError('Expected item-specific failure')
        engine._transfer_viewport = unsupported_after_duplicate
        try:
            skipped = []
            events[:] = []
            mixed = engine.copy_items(doc, source.UniqueId, target.UniqueId, [viewport.UniqueId, notes[0].UniqueId], 0, 0, skipped=skipped)
            check('mixed paste skips failed item and retains successful item in one Undo',
                  set(mixed) == set([notes[0].UniqueId]) and skipped == [(viewport.UniqueId, 'Expected item-specific failure')]
                  and events == ['Paste Copies'] and all(doc.GetElement(u) is None for u in attempted))
            events[:] = []
            skipped = []
            empty = engine.copy_items(doc, source.UniqueId, target.UniqueId, [viewport.UniqueId], 0, 0, skipped=skipped)
            check('all skipped returns empty mapping with reason and zero committed transactions',
                  empty == {} and len(skipped) == 1 and 'Paste Copies' not in events)
        finally:
            engine._transfer_viewport = group_viewport
        count = DB.FilteredElementCollector(doc).GetElementCount()
        original_transfer = engine._transfer_annotation
        def fail_after_new_view(*unused):
            current = set(e.UniqueId for e in DB.FilteredElementCollector(doc).OfClass(DB.View))
            assert len(current-before) == 1, 'Expected a newly duplicated view before the failure'
            raise RuntimeError('Injected copy failure')
        engine._transfer_annotation = fail_after_new_view
        try:
            try:
                engine.copy_items(doc, source.UniqueId, target.UniqueId, [viewport.UniqueId, notes[0].UniqueId], 0, 0)
                raise AssertionError('Injected copy failure committed')
            except RuntimeError as exc:
                assert 'Injected copy failure' in str(exc), str(exc)
        finally:
            engine._transfer_annotation = original_transfer
        check('bulk copy rollback removes the duplicated view and all new placements',
              before == set(e.UniqueId for e in DB.FilteredElementCollector(doc).OfClass(DB.View)) and
              DB.FilteredElementCollector(doc).GetElementCount() == count)
    finally:
        group.RollBack()
        group.Dispose()


def sample_kind(view):
    if str(view.ViewType) == 'ThreeD':
        return '3D perspective' if view.IsPerspective else '3D orthographic'
    return str(view.ViewType)


def sample_cases(sample_name, kinds, year='2026'):
    path = os.path.join(os.environ['ProgramW6432'] if 'ProgramW6432' in os.environ else os.environ['ProgramFiles'],
                        'Autodesk', 'Revit ' + year, 'Samples', sample_name + '.rvt')
    inventory = {'path': path, 'available': os.path.isfile(path)}
    result.setdefault('samples', []).append(inventory)
    if not os.path.isfile(path):
        return []
    directory = tempfile.mkdtemp(prefix='MoveSheetDetailsSample_')
    copy_path = os.path.join(directory, os.path.basename(path))
    shutil.copyfile(path, copy_path)
    sample = None
    transaction = None
    findings = []
    try:
        options = DB.OpenOptions()
        options.DetachFromCentralOption = DB.DetachFromCentralOption.DetachAndPreserveWorksets
        try:
            sample = app.OpenDocumentFile(DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(copy_path), options)
        finally:
            options.Dispose()
        transaction = DB.Transaction(sample, 'Prepare sample fixture')
        transaction.Start()
        source_sheet, target_sheet = [DB.ViewSheet.Create(sample, DB.ElementId.InvalidElementId) for _ in range(2)]
        if transaction.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Sample sheets could not be created.')
        transaction.Dispose()
        transaction = None
        all_views = [v for v in DB.FilteredElementCollector(sample).OfClass(DB.View) if not v.IsTemplate]
        inventory['view_types'] = sorted(set(str(v.ViewType) for v in all_views))
        views = [v for v in all_views if sample_kind(v) in kinds]
        placed = list(DB.FilteredElementCollector(sample).OfClass(DB.Viewport))
        for kind in kinds:
            element = next((e for e in placed if e.IsValidObject and engine.supported(sample, e) and
                            sample_kind(sample.GetElement(e.ViewId)) == kind), None)
            if element is None:
                view = next((v for v in views if sample_kind(v) == kind and DB.Viewport.CanAddViewToSheet(sample, source_sheet.Id, v.Id)), None)
                if view is None:
                    continue
                transaction = DB.Transaction(sample, 'Put sample view on source sheet')
                transaction.Start()
                element = DB.Viewport.Create(sample, source_sheet.Id, view.Id, DB.XYZ.Zero)
                if transaction.Commit() != DB.TransactionStatus.Committed or element is None:
                    raise ValueError('Cannot initialize sample ' + kind)
                transaction.Dispose()
                transaction = None
            old = element.UniqueId
            origin = sample.GetElement(element.SheetId)
            view_id = element.ViewId
            source_view = sample.GetElement(view_id)
            if kind in ('Legend', 'ColumnSchedule'):
                modes = ('share', 'detail', 'duplicate', 'skip', 'invalid')
            elif kind.startswith('3D'):
                modes = ('duplicate',)
            else:
                modes = ('detail',)
            for mode in modes:
                group = DB.TransactionGroup(sample, 'Isolate view copy policy')
                group.Start()
                try:
                    explicit = kind in ('Legend', 'ColumnSchedule')
                    choices = {source_view.UniqueId: mode} if explicit else {}
                    skipped, calls = [], []
                    duplicate_func = engine._duplicate_view
                    def record_duplicate(document, chosen, option):
                        calls.append(str(option))
                        return duplicate_func(document, chosen, option)
                    engine._duplicate_view = record_duplicate
                    try:
                        mapping = engine.copy_items(sample, origin.UniqueId, target_sheet.UniqueId, [old], 0, 0, choices, skipped)
                    finally:
                        engine._duplicate_view = duplicate_func
                    option = DB.ViewDuplicateOption.WithDetailing if mode=='detail' else DB.ViewDuplicateOption.Duplicate
                    can = (DB.Viewport.CanAddViewToSheet(sample, target_sheet.Id, view_id) if mode=='share' else
                           mode in ('detail', 'duplicate') and source_view.CanViewBeDuplicated(option))
                    result.setdefault('mode_outcomes', []).append([kind, mode, 'created' if mapping else skipped[0][1], calls])
                    if old in mapping:
                        created_viewport = sample.GetElement(mapping[old])
                        assert not skipped and sample.GetElement(old).ViewId == view_id
                        check('{} / {} uses its authorized native option'.format(kind, mode), (created_viewport.ViewId == view_id and not calls)
                              if mode == 'share' else (created_viewport.ViewId != view_id and calls == [str(option)]))
                    else:
                        check('{} / {} skips with reason and no source changes'.format(kind, mode), skipped and
                              skipped[0][0] == old and skipped[0][1] and sample.GetElement(old).ViewId == view_id)
                        if can:
                            result.setdefault('declines_after_positive_api_capability', []).append([kind, mode, source_view.Name, skipped[0][1]])
                finally:
                    group.RollBack()
                    group.Dispose()
            if kind in ('Legend','ColumnSchedule','Detail'):
                mapping = engine.move(sample, origin.UniqueId, target_sheet.UniqueId, [old], -2.4, 3.2)
                new = sample.GetElement(mapping[old])
                check('sample ' + kind + ' placement preserved view identity', new.ViewId == view_id and new.SheetId == target_sheet.Id)
            findings.append(kind)
        return findings
    finally:
        if transaction and transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        if sample:
            sample.Close(False)
        if os.path.exists(copy_path):
            os.remove(copy_path)
        if not os.listdir(directory):
            os.rmdir(directory)


try:
    doc = app.NewProjectDocument(r'C:\ProgramData\Autodesk\RVT 2026\Templates\Default_I_ENU.rte')
    app.DocumentChanged += changed
    setup = DB.Transaction(doc, 'Fixture')
    setup.Start()
    sheets = [DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId) for i in range(2)]
    source, target = sheets
    family = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType) if t.ViewFamily == DB.ViewFamily.Drafting)
    draft = DB.ViewDrafting.Create(doc, family.Id)
    text_type = DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType).FirstElementId()
    DB.TextNote.Create(doc, draft.Id, DB.XYZ.Zero, 'Contents of the drafting view', text_type)
    floor_type = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType) if t.ViewFamily == DB.ViewFamily.FloorPlan)
    level = DB.FilteredElementCollector(doc).OfClass(DB.Level).FirstElement()
    plan = DB.ViewPlan.Create(doc, floor_type.Id, level.Id)
    plan_note = DB.TextNote.Create(doc, plan.Id, DB.XYZ(0, 0, level.ProjectElevation), 'Floor plan copy proof', text_type)
    section_type = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType) if t.ViewFamily==DB.ViewFamily.Section)
    box = DB.BoundingBoxXYZ()
    orientation = DB.Transform.Identity
    orientation.BasisX, orientation.BasisY, orientation.BasisZ = DB.XYZ.BasisX, DB.XYZ.BasisZ, -DB.XYZ.BasisY
    box.Transform = orientation
    box.Min, box.Max = DB.XYZ(-5, -5, 0), DB.XYZ(5, 5, 10)
    DB.ViewSection.CreateSection(doc, section_type.Id, box)
    detail_type = next((t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType) if t.ViewFamily==DB.ViewFamily.Detail), None)
    if detail_type:
        DB.ViewSection.CreateDetail(doc, detail_type.Id, box)
    if setup.Commit() != DB.TransactionStatus.Committed:
        raise ValueError('Fixture sheet/view creation failed.')
    setup.Dispose()
    setup = DB.Transaction(doc, 'Fixture placements')
    setup.Start()
    assert DB.Viewport.CanAddViewToSheet(doc, source.Id, draft.Id), 'Fixture drafting view is not placeable.'
    viewport = DB.Viewport.Create(doc, source.Id, draft.Id, DB.XYZ(0.3, 0.4, 0))
    assert viewport is not None, 'Revit could not render the new drafting viewport.'
    plan_placement = DB.Viewport.Create(doc, source.Id, plan.Id, DB.XYZ(0.9, 0.6, 0))
    viewport.Rotation = DB.ViewportRotation.Clockwise
    viewport.LabelOffset = DB.XYZ(0.18, 0.12, 0)
    viewport.LabelLineLength = 0.56
    number = viewport.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
    number.Set('27')
    notes = [DB.TextNote.Create(doc, source.Id, DB.XYZ(0.1, 0.2, 0), text, text_type) for text in ('one', 'two')]
    bound = DB.Line.CreateBound(DB.XYZ.Zero, DB.XYZ(0.8, 0.2, 0))
    line = doc.Create.NewDetailCurve(source, bound)
    symbols = list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(DB.BuiltInCategory.OST_GenericAnnotation))
    annotation = None
    for symbol in symbols:
        tx = DB.SubTransaction(doc)
        tx.Start()
        try:
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            instance = doc.Create.NewFamilyInstance(DB.XYZ(0.2, 0.3, 0), symbol, source)
            if not engine.supported(doc, instance):
                raise ValueError('Use a free-standing annotation.')
            tx.Commit()
            annotation = instance
            break
        except Exception:
            tx.RollBack()
        finally:
            tx.Dispose()
    schedule = DB.ViewSchedule.CreateSchedule(doc, DB.ElementId(DB.BuiltInCategory.OST_Doors))
    schedule.Definition.AddField(schedule.Definition.GetSchedulableFields()[0])
    placement = DB.ScheduleSheetInstance.Create(doc, source.Id, schedule.Id, DB.XYZ(0.5, 0.5, 0))
    optional = []
    eligible = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.View) if not v.IsTemplate and
                str(v.ViewType) in ('Legend', 'ColumnSchedule', 'Section', 'Detail')]
    for v in eligible:
        if str(v.ViewType) not in [role for role, e in optional] and DB.Viewport.CanAddViewToSheet(doc, source.Id, v.Id):
            optional.append((str(v.ViewType), DB.Viewport.Create(doc, source.Id, v.Id, DB.XYZ(-0.5, -0.2, 0))))
    if setup.Commit() != DB.TransactionStatus.Committed:
        raise ValueError('Fixture failed.')
    setup.Dispose()
    result['optional_viewport_types'] = [kind for kind, unused in optional]
    result['annotation_family'] = annotation is not None
    items = notes + [viewport, plan_placement, placement] + ([annotation] if annotation else []) + [e for role, e in optional]
    uids = [e.UniqueId for e in items]
    vp_uid, sc_uid = viewport.UniqueId, placement.UniqueId
    view_uid, sched_uid = draft.UniqueId, schedule.UniqueId
    original_type = viewport.GetTypeId()
    check('sheet detail lines excluded and fixture items supported', not engine.supported(doc, line) and all(engine.supported(doc, e) for e in items))
    copy_regression(source, target, items, viewport, draft, placement, notes)
    events[:] = []
    before = dict((e.UniqueId, engine.item_anchor(e)) for e in items)
    delta = DB.XYZ(-4.5, 6.1, 0)
    mapping = engine.move(doc, source.UniqueId, source.UniqueId, uids, delta.X, delta.Y)
    check('same sheet keeps all IDs and relative positions, allows overlap and off-border positions',
          mapping == dict((u, u) for u in uids) and all(closed(engine.item_anchor(e), before[e.UniqueId]+delta) for e in items))
    check('one undo transaction for same-sheet move', events == ['Move Views'])
    result['same_sheet_undo_names'] = list(events)
    before = dict((e.UniqueId, engine.item_anchor(e)) for e in items)
    try:
        engine.move(doc, source.UniqueId, target.UniqueId, [vp_uid, line.UniqueId], 0, 0)
        raise AssertionError('Unsupported selection moved.')
    except ValueError:
        pass
    check('bad mixed selection leaves valid source untouched', doc.GetElement(vp_uid).SheetId == source.Id)
    original_transfer = engine._transfer_annotation
    def fail(*args):
        raise ValueError('Inject after viewport removed and re-created')
    engine._transfer_annotation = fail
    try:
        try:
            engine.move(doc, source.UniqueId, target.UniqueId, [vp_uid, notes[0].UniqueId], 0, 0)
            raise AssertionError('Injected failure committed.')
        except ValueError as exc:
            assert 'Inject after' in str(exc), str(exc)
    finally:
        engine._transfer_annotation = original_transfer
    check('partial transfer rolled back including viewport ID', doc.GetElement(vp_uid).SheetId == source.Id and not list(target.GetAllViewports()))
    events[:] = []
    delta = DB.XYZ(3.0, -0.4, 0)
    mapping = engine.move(doc, source.UniqueId, target.UniqueId, uids, delta.X, delta.Y, transaction_name='Paste Views')
    check('one undo transaction for bulk cross-sheet transfer', events == ['Paste Views'])
    result['cross_sheet_undo_names'] = list(events)
    check('all sources replaced once at translated positions',
          all(doc.GetElement(u) is None and closed(engine.item_anchor(doc.GetElement(mapping[u])), before[u]+delta) for u in uids))
    new_vp, new_sc = doc.GetElement(mapping[vp_uid]), doc.GetElement(mapping[sc_uid])
    check('underlying view and schedule identities preserved', doc.GetElement(new_vp.ViewId).UniqueId == view_uid and doc.GetElement(new_sc.ScheduleId).UniqueId == sched_uid)
    check('viewport type, rotation, detail number, title offset and line length preserved',
          new_vp.GetTypeId() == original_type and new_vp.Rotation == DB.ViewportRotation.Clockwise and
          closed(new_vp.LabelOffset, DB.XYZ(0.18, 0.12, 0)) and abs(new_vp.LabelLineLength-0.56) < 1e-6 and
          new_vp.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).AsString() == '27')
    check('standalone detail line survived untouched', line.IsValidObject and line.OwnerViewId == source.Id)
    try:
        engine.move(doc, source.UniqueId, target.UniqueId, uids, 0, 0)
        raise AssertionError('Repeat cut accepted.')
    except ValueError:
        pass
    check('stale repeat paste rejected', all(doc.GetElement(u) is not None for u in mapping.values()))
    additional = DB.Transaction(doc, 'Prepare split schedule and detail-number conflict')
    additional.Start()
    for i in range(10):
        DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
    sheet_list = DB.ViewSchedule.CreateSheetList(doc)
    field = next(f for f in sheet_list.Definition.GetSchedulableFields() if f.ParameterId.Value == int(DB.BuiltInParameter.SHEET_NUMBER))
    sheet_list.Definition.AddField(field)
    doc.Regenerate()
    sheet_list.Split(2)
    segment = DB.ScheduleSheetInstance.Create(doc, source.Id, sheet_list.Id, DB.XYZ(1, 1, 0), 1)
    collision = DB.ViewDrafting.Create(doc, family.Id)
    DB.TextNote.Create(doc, collision.Id, DB.XYZ.Zero, 'Detail number conflict', text_type)
    additional.Commit()
    additional.Dispose()
    additional = DB.Transaction(doc, 'Place repeated detail number')
    additional.Start()
    source_vp = DB.Viewport.Create(doc, source.Id, collision.Id, DB.XYZ.Zero)
    source_vp.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).Set('27')
    additional.Commit()
    additional.Dispose()
    segment_uid, collision_uid = segment.UniqueId, source_vp.UniqueId
    copies = DB.TransactionGroup(doc, 'Isolate split schedule copy')
    copies.Start()
    try:
        segment_map = engine.copy_items(doc, source.UniqueId, target.UniqueId, [segment_uid], 0, 0)
        segment_copy = doc.GetElement(segment_map[segment_uid])
        check('split schedule copy duplicates definition, retains segment and leaves source intact', segment_copy.ScheduleId != sheet_list.Id and
              segment_copy.SegmentIndex == segment.SegmentIndex == 1 and segment_copy.Id != segment.Id)
    finally:
        copies.RollBack()
        copies.Dispose()
    moved = engine.move(doc, source.UniqueId, target.UniqueId, [collision_uid, segment_uid], 0.3, -0.1)
    segment_after = doc.GetElement(moved[segment_uid])
    check('split schedule retains the same segment and underlying schedule', segment_after.SegmentIndex == 1 and segment_after.ScheduleId == sheet_list.Id)
    number_after = doc.GetElement(moved[collision_uid]).get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).AsString()
    check('existing detail number retained on occupied destination', number_after and number_after != '27' and
          new_vp.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).AsString() == '27')
    sample_kinds = ('Legend', 'ColumnSchedule', 'Detail', 'FloorPlan', 'AreaPlan', 'EngineeringPlan', 'CeilingPlan', 'Elevation',
                    '3D orthographic', '3D perspective')
    found = sample_cases('Snowdon Towers Sample Structural', sample_kinds)
    if set(sample_kinds)-set(found):
        found.extend(sample_cases('Snowdon Towers Sample Architectural', [kind for kind in sample_kinds if kind not in found]))
    if 'ColumnSchedule' not in found:
        found.extend(sample_cases('rst_advanced_sample_project', ['ColumnSchedule'], year='2023'))
    result['sample_viewport_types'] = found
    result['passed'] = True
except Exception:
    result['error'] = traceback.format_exc()
finally:
    if doc:
        app.DocumentChanged -= changed
        for active in (globals().get('setup'), globals().get('additional')):
            if active is not None and active.IsValidObject and active.GetStatus() == DB.TransactionStatus.Started:
                active.RollBack()
        doc.Close(False)
    folder = os.path.join(ROOT, 'diagnostics')
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(os.path.join(folder, 'native-moves-' + app.VersionNumber + '.json'), 'w') as stream:
        json.dump(result, stream, indent=2)
