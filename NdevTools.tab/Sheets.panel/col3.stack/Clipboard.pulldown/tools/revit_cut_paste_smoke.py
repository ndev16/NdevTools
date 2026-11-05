# -*- coding: utf-8 -*-
"""Clipboard integration checks on disposable documents. No active project access."""
import imp
import clr
import json
import os
import shutil
import tempfile
import time
import traceback
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import DB, UI
from System import IntPtr
from System.Runtime.CompilerServices import RuntimeHelpers


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
command = imp.load_source('ndev_main_cut_test_command', os.path.join(ROOT, 'script.py'))
clip, moves, preview = command.load_modules()
checks = []
reports = []
tested_modes = {}
native_mode_dialog = command.choose_mode


def capture_report(result, skipped, data):
    labels = dict((r['uid'], r['label']) for r in data['rows'])
    reports.append((len(result), [(labels[uid], reason) for uid, reason in skipped]))


def check(name, passed):
    if not passed:
        raise AssertionError(name)
    checks.append(name)


def expect_error(message, invoke):
    try:
        invoke()
    except ValueError as error:
        if message.lower() in unicode(error).lower():
            return
        raise
    raise AssertionError('Expected error: ' + message)


def test_dialog(dialog, action):
    # Journal playback sends Exit on entering a nested modal loop. Show the same
    # WPF content synchronously and drive its real handlers before returning to Revit.
    dialog.window.Show()
    try:
        dialog.window.UpdateLayout()
        check('WPF displayed / ' + action, dialog.window.IsVisible)
        expected = 2 if action == 'copy' else 1
        check('Partial preselection and correct action / ' + action, dialog.Placements.SelectedItems.Count == expected
              and dialog.ChooseButton.Content == action.title() + ' selected')
        dialog.select_all(None, None)
        check('Select all with explicit skip eligibility / ' + action, dialog.Placements.SelectedItems.Count == expected + 1)
        dialog.choose(None, None)
    finally:
        if dialog.window.IsVisible:
            dialog.window.Close()
    check('Selected IDs returned / ' + action, len(dialog.chosen) == expected + 1)
    return dialog.chosen


class TestSelection(object):
    def __init__(self):
        self.ids = []
        self.point = None
        self.prompt = None

    def GetElementIds(self):
        return self.ids

    def SetElementIds(self, ids):
        self.ids = list(ids)

    def PickPoint(self, prompt):
        self.prompt = prompt
        if self.point is None:
            raise RuntimeHelpers.GetUninitializedObject(clr.GetClrType(OperationCanceledException))
        return self.point


class Context(object):
    pass


def special_views(app, directory):
    tested = []
    for sample in ['rst_advanced_sample_project.rvt', 'rac_basic_sample_project.rvt']:
        path = os.path.join(directory, sample)
        shutil.copyfile(os.path.join(os.environ['ProgramFiles'], 'Autodesk', 'Revit 2023', 'Samples', sample), path)
        doc = app.OpenDocumentFile(path)
        try:
            views = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
                     if not v.IsTemplate and str(v.ViewType) in ('Legend', 'ColumnSchedule')]
            tx = DB.Transaction(doc, 'Temporary sheets for clipboard choices')
            tx.Start()
            source = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
            target = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
            note = DB.TextNote.Create(doc, source.Id, DB.XYZ(1, 1, 0), 'Mixed special copy note',
                                      doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType))
            items = {}
            for kind in ('Legend', 'ColumnSchedule'):
                if kind in tested:
                    continue
                view = next((v for v in views if str(v.ViewType) == kind and DB.Viewport.CanAddViewToSheet(doc, source.Id, v.Id)), None)
                if view:
                    items[kind] = DB.Viewport.Create(doc, source.Id, view.Id, DB.XYZ(len(items)*1.1, .4, 0))
            tx.Commit()
            tx.Dispose()
            ctx = Context()
            ctx.MainWindowHandle = IntPtr.Zero
            ctx.ActiveUIDocument, ctx.Document = ctx, doc
            ctx.Selection = TestSelection()
            for kind, holder in items.items():
                uid = holder.UniqueId
                view = doc.GetElement(holder.ViewId)
                ctx.ActiveView, ctx.Selection.ids = source, [holder.Id]
                entry = command.main(ctx, 'copy')
                ctx.ActiveView = target
                prompts = []
                def cancel(prompt, label):
                    prompts.append(prompt)
                    return None
                command.choose_mode = cancel
                ctx.Selection.prompt = None
                prior_views = set(x.Id for x in DB.FilteredElementCollector(doc).OfClass(DB.View))
                prior_ports = set(x.Id for x in DB.FilteredElementCollector(doc).OfClass(DB.Viewport))
                events = []
                def changed(sender, args):
                    if args.GetDocument().Equals(doc):
                        events.append((str(args.Operation), list(args.GetTransactionNames())))
                app.DocumentChanged += changed
                started = time.time()
                try:
                    check(kind + ' cancel mode retains clipboard before point pick',
                          command.main(ctx, 'paste') is None and ctx.Selection.prompt is None and clip.current(doc)['token'] == entry['token'])
                finally:
                    app.DocumentChanged -= changed
                elapsed = time.time() - started
                check(kind + ' probes leave no new views, placements or undo transactions',
                      all(e[0] == 'TransactionRolledBack' for e in events)
                      and prior_views == set(x.Id for x in DB.FilteredElementCollector(doc).OfClass(DB.View))
                      and prior_ports == set(x.Id for x in DB.FilteredElementCollector(doc).OfClass(DB.Viewport)))
                expected = ['skip']
                if DB.Viewport.CanAddViewToSheet(doc, target.Id, view.Id):
                    expected.append('share')
                for key, option in [('detail', DB.ViewDuplicateOption.WithDetailing), ('duplicate', DB.ViewDuplicateOption.Duplicate)]:
                    if view.CanViewBeDuplicated(option):
                        expected.append(key)
                check(kind + ' choices match native target capability and view UID',
                      len(prompts) == 1 and prompts[0]['uid'] == view.UniqueId and set(prompts[0]['options']).issubset(expected)
                      and 'share' in prompts[0]['options'] and 'detail' in prompts[0]['options'])
                prompt = prompts[0]
                tested_modes[kind] = {'name':view.Name, 'flags':expected, 'offered':prompt['options'],
                                      'seconds':round(elapsed,3), 'probe_events': events}
                if kind == 'Legend' and view.Name == 'Symbol Legend':
                    check('Empty independent plain legend omitted even when Revit advertises Duplicate',
                          'duplicate' in expected and 'duplicate' not in prompt['options'])
                for idx, mode in enumerate(prompt['options'], 1):
                    def choose_link(dialog):
                        assert view.Name in dialog.MainInstruction
                        assert preview.sheet_label(target) in dialog.MainContent
                        return getattr(UI.TaskDialogResult, 'CommandLink{}'.format(idx))
                    assert native_mode_dialog(prompt, preview.sheet_label(target), choose_link) == mode
                check(kind + ' actual native TaskDialog commands map to the advertised options',
                      native_mode_dialog(prompt, preview.sheet_label(target), lambda dialog: UI.TaskDialogResult.Cancel) is None)
                command.choose_mode = lambda prompt, label: 'skip'
                check(kind + ' user skip reports zero before point pick',
                      command.main(ctx, 'paste') == {} and ctx.Selection.prompt is None and reports[-1][0] == 0
                      and view.Name in reports[-1][1][0][0] and 'paste choice' in reports[-1][1][0][1])
                for mode in [m for m in ('share','detail','duplicate') if m in prompt['options']]:
                    command.choose_mode = lambda prompt, label: mode
                    ctx.Selection.point = DB.XYZ(.8, .7, 0)
                    result = command.main(ctx, 'paste')
                    if uid not in result:
                        raise AssertionError(u'{} {} could not be placed: {}'.format(kind, mode, reports[-1]))
                    check(kind + ' actual ' + mode + ' placement',
                          uid in result and (doc.GetElement(result[uid]).ViewId == view.Id) == (mode == 'share'))
                tested.append(kind)
            if len(items) > 1:
                ctx.ActiveView, ctx.Selection.ids = source, [p.Id for p in items.values()]
                command.main(ctx, 'copy')
                seen = []
                def decide(prompt, label):
                    seen.append(prompt['uid'])
                    return 'skip'
                command.choose_mode = decide
                ctx.ActiveView = target
                check('Multiple special views receive independent prompts', command.main(ctx, 'paste') == {}
                      and len(set(seen)) == len(items) and len(reports[-1][1]) == len(items))
                ctx.ActiveView, ctx.Selection.ids = source, [p.Id for p in items.values()] + [note.Id]
                command.main(ctx, 'copy')
                command.choose_mode = lambda prompt, label: 'skip' if prompt['kind'] == 'Legend' else 'detail'
                ctx.ActiveView, ctx.Selection.point = target, DB.XYZ(.3, 1.2, 0)
                placed = command.main(ctx, 'paste')
                check('One special view skipped, other chosen mode and note are pasted',
                      set(placed) == set([note.UniqueId, items['ColumnSchedule'].UniqueId]) and reports[-1][0] == 2
                      and len(reports[-1][1]) == 1)
        finally:
            doc.Close(False)
            clip._entries()
        if len(tested) == 2:
            break
    check('Actual legend and graphical column schedule families exercised', set(tested) == set(['Legend','ColumnSchedule']))


def run(app, directory):
    doc = app.NewProjectDocument(DB.UnitSystem.Imperial)
    other = None
    try:
        tx = DB.Transaction(doc, 'Set up disposable clipboard test')
        tx.Start()
        src = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
        dst = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
        spare = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
        src.SheetNumber, dst.SheetNumber = 'QA101', 'QA102'
        view_type = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                         if t.ViewFamily == DB.ViewFamily.Drafting)
        view = DB.ViewDrafting.Create(doc, view_type.Id)
        doc.Create.NewDetailCurve(view, DB.Line.CreateBound(DB.XYZ.Zero, DB.XYZ(8, 5, 0)))
        vp = DB.Viewport.Create(doc, src.Id, view.Id, DB.XYZ(.4, 1.3, 0))
        note_type = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
        note = DB.TextNote.Create(doc, src.Id, DB.XYZ(2, .4, 0), 'Clipboard placement', note_type)
        pinned = DB.TextNote.Create(doc, src.Id, DB.XYZ(2, .8, 0), 'Pinned', note_type)
        pinned.Pinned = True
        tx.Commit()
        tx.Dispose()
        uid = note.UniqueId
        uids = [uid, vp.UniqueId]
        path = os.path.join(directory, 'Clipboard.rvt')
        doc.SaveAs(path)
        twin = os.path.join(directory, 'ClipboardCopy.rvt')
        shutil.copyfile(path, twin)
        other = app.OpenDocumentFile(twin)
        ctx = Context()
        ctx.MainWindowHandle = IntPtr.Zero
        ctx.ActiveUIDocument = ctx
        ctx.Document, ctx.ActiveView, ctx.Selection = doc, src, TestSelection()
        rows = clip.sheet_items(doc, src, moves, preview)
        check('Pinned item excluded', set(r['uid'] for r in rows) == set(uids))
        for operation in ('copy', 'cut'):
            ctx.Selection.ids = [note.Id, pinned.Id]
            default_show = command.Dialog.show
            try:
                command.Dialog.show = lambda self: test_dialog(self, operation)
                mixed = command.main(ctx, operation)
            finally:
                command.Dialog.show = default_show
            if operation == 'copy':
                mixed_data = clip.info(mixed)
                check('Explicitly selected pinned placement held by name for skip report',
                      any(row['label'] == 'Pinned' and 'pinned' in row['blocked'] for row in mixed_data['rows']))
                ctx.ActiveView, ctx.Selection.point = spare, DB.XYZ(1, 1, 0)
                mixed_result = command.main(ctx, 'paste')
                check('Eligible items pasted and explicitly selected pinned member reported',
                      set(mixed_result) == set(uids) and reports[-1] == (2, [('Pinned', 'The placement is pinned.')]))
                ctx.ActiveView, ctx.Selection.point, ctx.Selection.prompt = src, None, None
                # Reusing just the explicitly selected, ineligible placement requires no point.
                only = clip.store(doc, src, [pinned.UniqueId], 'copy', moves, preview)
                check('All unsupported copy reports zero and reason',
                      command.main(ctx, 'paste') == {} and reports[-1] == (0, [('Pinned', 'The placement is pinned.')])
                      and clip.current(doc)['token'] == only['token'] and ctx.Selection.prompt is None)
        ctx.Selection.ids = [note.Id, vp.Id, view.Id]
        entry = command.main(ctx, 'cut')
        check('View definition and active-sheet viewport resolve to one held placement',
              set(row['uid'] for row in clip.info(entry)['rows']) == set(uids))
        token = entry['token']
        data = clip.info(entry)
        # An independently imported module models reopening the ribbon command.
        fresh = imp.load_source('ndev_main_clip_separate_command', os.path.join(ROOT, 'sheet_clip.py'))
        check('Session clipboard survives command reload', fresh.current(doc)['token'] == token)
        check('Matching UIDs in another document have separate clipboards', other.GetElement(uid) is not None and fresh.current(other) is None)
        ctx.ActiveView = dst
        old = dict((k, moves.item_anchor(doc.GetElement(k))) for k in uids)
        center = DB.XYZ(data['center'][0], data['center'][1], 0)
        point = DB.XYZ(-.4, 1.9, 0)
        check('Direct Paste invokes native picker; Esc retains sources and token', command.main(ctx, 'paste') is None
              and 'center' in ctx.Selection.prompt and 'QA102' in ctx.Selection.prompt
              and fresh.current(doc)['token'] == token and all(doc.GetElement(k) for k in uids))
        original = moves._transfer_viewport
        def fail(*args):
            raise ValueError('Injected transfer failure')
        try:
            moves._transfer_viewport = fail
            expect_error('Injected transfer failure', lambda: fresh.paste(doc, dst, token, moves, preview, lambda: point))
        finally:
            moves._transfer_viewport = original
        check('Mid-transfer rollback retains token and original items', fresh.current(doc)['token'] == token
              and all(doc.GetElement(k) for k in uids) and len(fresh.sheet_items(doc, dst, moves, preview)) == 0)
        transaction_names = []
        def changed(sender, args):
            if args.GetDocument().Equals(doc):
                transaction_names.extend(args.GetTransactionNames())
        app.DocumentChanged += changed
        try:
            ctx.Selection.point = point
            placed = command.main(ctx, 'paste')
        finally:
            app.DocumentChanged -= changed
        check('Paste is one named undo transaction', transaction_names == ['Paste Views'])
        check('Transferred objects selected in Revit', set(placed.values()) == set(doc.GetElement(e).UniqueId for e in ctx.Selection.ids))
        for k in uids:
            actual = moves.item_anchor(doc.GetElement(placed[k]))
            check('Placement offset verified for ' + str(doc.GetElement(placed[k]).GetType().Name),
                  actual.DistanceTo(old[k] + point - center) < 1e-6)
        post = fresh.sheet_items(doc, dst, moves, preview)
        mid = [(min(r['rect'][i] for r in post) + max(r['rect'][i+2] for r in post)) / 2. for i in (0, 1)]
        check('Union-bounds center lands at picked point', abs(mid[0]-point.X) < 1e-6 and abs(mid[1]-point.Y) < 1e-6)
        expect_error('already pasted', lambda: fresh.paste(doc, dst, token, moves, preview, lambda: point))
        check('Successful paste consumes token once', fresh.current(doc) is None)
        # The destination selection from Paste is eligible preselection for Copy.
        copy_entry = command.main(ctx, 'copy')
        copy_token = copy_entry['token']
        copied_uids = set(placed.values())
        ctx.ActiveView = src
        ctx.Selection.point = None
        check('Esc retains repeatable copy', command.main(ctx, 'paste') is None
              and fresh.current(doc)['token'] == copy_token)
        ctx.Selection.point = DB.XYZ(.65, 1.1, 0)
        first_copy = command.main(ctx, 'paste')
        ctx.Selection.point = DB.XYZ(2.1, .8, 0)
        second_copy = command.main(ctx, 'paste')
        check('Copy pastes twice from the same native clipboard', set(first_copy.keys()) == copied_uids
              and set(second_copy.keys()) == copied_uids and not set(second_copy.values()) & set(first_copy.values())
              and fresh.current(doc)['token'] == copy_token)
        check('Both original placements remain on their source sheet',
              set(row['uid'] for row in fresh.sheet_items(doc, dst, moves, preview)) == copied_uids)
        check('Both copy results are on the clicked sheet',
              set(row['uid'] for row in fresh.sheet_items(doc, src, moves, preview)) == set(first_copy.values() + second_copy.values()))
        new_note = doc.GetElement(placed[uid])
        tx = DB.Transaction(doc, 'Change cut placement in disposable model')
        tx.Start()
        DB.ElementTransformUtils.MoveElement(doc, new_note.Id, DB.XYZ(.2, 0, 0))
        tx.Commit()
        tx.Dispose()
        before = fresh.info(fresh.current(doc))['center']
        result = command.main(ctx, 'paste')
        check('Stale copy member skipped, surviving viewport pasted, with names and reason',
              set(result) == set([placed[uids[1]]]) and reports[-1][0] == 1 and len(reports[-1][1]) == 1
              and reports[-1][1][0][0] == 'Clipboard placement' and 'changed' in reports[-1][1][0][1])
        check('Repeated mixed copy retains original reference and clipboard', fresh.info(fresh.current(doc))['center'] == before)
        saved = next(r for r in fresh.info(fresh.current(doc))['rows'] if r['uid'] == placed[uids[1]])
        v = moves.item_anchor(doc.GetElement(result[saved['uid']]))
        check('Skipping a member does not recenter the pasted group',
              abs(v.X - saved['anchor'][0] - (ctx.Selection.point.X - before[0])) < 1e-6
              and abs(v.Y - saved['anchor'][1] - (ctx.Selection.point.Y - before[1])) < 1e-6)
    finally:
        if other is not None:
            other.Close(False)
        doc.Close(False)
        clip._entries()


folder = tempfile.mkdtemp(prefix='ndev-cut-qa-')
report = {'version': __revit__.Application.VersionNumber, 'passed': False,
          'checks': checks, 'special_modes': tested_modes}
try:
    command.report_skips = capture_report
    run(__revit__.Application, folder)
    special_views(__revit__.Application, folder)
    report['passed'] = True
except Exception:
    report['error'] = traceback.format_exc()
finally:
    shutil.rmtree(folder, ignore_errors=True)
    diag = os.path.join(ROOT, 'diagnostics')
    if not os.path.isdir(diag):
        os.makedirs(diag)
    with open(os.path.join(diag, 'native-cut-paste-{}.json'.format(report['version'])), 'w') as handle:
        json.dump(report, handle, indent=2)
