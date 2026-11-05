# -*- coding: utf-8 -*-
"""Exercise the graphical Move Views workspace in a separate, empty Revit host.

Run this script in pyRevit or call start(app, output, close_revit=False)
from a private journal runner. Return to Revit's message loop after starting.
A screenshot, the disposable project, and result JSON are saved in a unique run directory.
"""
__persistentengine__ = True
import hashlib
import imp
import json
import os
import tempfile
import traceback
from pyrevit import DB, UI
from System import Action, AppDomain
from System.Diagnostics import Stopwatch
from System.IO import File
from System.Windows import Point, PresentationSource, RoutedEventArgs, WindowState
from System.Windows.Controls import Button
from System.Windows.Interop import ComponentDispatcher
from System.Windows.Input import Key, Keyboard, KeyEventArgs, MouseButton
from System.Windows.Threading import DispatcherPriority
from System.Windows.Media import PixelFormats
from System.Windows.Media.Imaging import BitmapFrame, PngBitmapEncoder, RenderTargetBitmap


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = 'NdevTools.Main.QA.DualPreviewWorkspace'
SESSION = 'NdevTools.Main.MoveViews.Window'

def file_digest(path):
    with open(path, 'rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()

def image(window, path):
    window.UpdateLayout()
    bitmap = RenderTargetBitmap(int(window.ActualWidth), int(window.ActualHeight), 96, 96, PixelFormats.Pbgra32)
    bitmap.Render(window)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    stream = File.Create(path)
    try:
        encoder.Save(stream)
    finally:
        stream.Dispose()

class Pointer:
    """Mouse event test double; movement and hit testing use real WPF coordinates."""
    ChangedButton = MouseButton.Left
    ClickCount = 1
    Handled = False

    def __init__(self, pane, point):
        self.screen = pane.surface.PointToScreen(point)

    def GetPosition(self, visual):
        return visual.PointFromScreen(self.screen)

class WorkspaceSmoke(object):

    def __init__(self, app, output, close_revit):
        self.app = app
        self.output = output
        self.close_revit = close_revit
        self.folder = tempfile.mkdtemp(prefix='run-', dir=output)
        self.path = os.path.join(self.folder, 'Preview fixture.rvt')
        self.doc = None
        self.uidoc = None
        self.session = None
        self.steps = self.exercise()
        self.stage = 'setup'
        self.clock = Stopwatch.StartNew()
        self.out = {'checks': [], 'passed': False, 'version': app.Application.VersionNumber, 'folder': self.folder}
        self.running = False
        self.done = False
        self.condition = None
        self.activations = []
        self.swap_transactions = None

    def save(self):
        self.out['stage'] = self.stage
        with open(os.path.join(self.folder, 'results.json'), 'w') as f:
            json.dump(self.out, f, indent=2)
        with open(os.path.join(self.output, 'last-result.json'), 'w') as f:
            json.dump(self.out, f, indent=2)

    def check(self, msg, condition):
        if not condition:
            raise AssertionError(msg)
        self.out['checks'].append(msg)

    def start(self):
        self.check('Private host started without a project', self.app.ActiveUIDocument is None)
        self.app.Idling += self.idle
        self.app.ViewActivated += self.view_activated
        self.app.Application.DocumentChanged += self.document_changed
        try:
            self.advance()
        except Exception:
            self.finish(traceback.format_exc())

    def advance(self):
        self.stage, self.condition = next(self.steps)
        self.clock.Restart()
        self.save()

    def view_activated(self, sender, args):
        view = args.CurrentActiveView
        if view is not None and self.doc is not None and self.doc.Equals(view.Document):
            self.activations.append(view.UniqueId)

    def document_changed(self, sender, args):
        if self.swap_transactions is not None and self.doc.Equals(args.GetDocument()):
            self.swap_transactions.append(list(args.GetTransactionNames()))

    def idle(self, app, args):
        if self.done or self.running:
            return
        self.running = True
        try:
            self.app = app
            self.uidoc = app.ActiveUIDocument
            if self.uidoc is None or not self.doc or (not self.doc.Equals(self.uidoc.Document)):
                raise RuntimeError('The disposable sheet project is no longer active.')
            if self.clock.Elapsed.TotalSeconds > 70:
                panel = self.session.panel
                native = self.uidoc.ActiveView
                self.out['on_timeout'] = {'active_view': native.UniqueId,
                                          'source': panel.source.uid, 'target': panel.target.uid,
                                          'activations': self.activations}
                raise RuntimeError(u'{} timed out. {}'.format(self.stage, panel.window.FindName('notice').Text))
            if self.condition and self.condition():
                self.advance()
            if not self.done:
                args.SetRaiseWithoutDelay()
        except StopIteration:
            self.finish(None)
        except Exception:
            self.finish(traceback.format_exc())
        finally:
            self.running = False

    def finish(self, error):
        if self.done:
            return
        self.done = True
        self.app.Application.DocumentChanged -= self.document_changed
        self.app.ViewActivated -= self.view_activated
        self.app.Idling -= self.idle
        try:
            if self.session and (not self.session.closed):
                self.session.panel.close()
                if hasattr(self.session, 'arm_cleanup'):
                    self.session.arm_cleanup(self.app)
            if self.doc and self.doc.IsValidObject and (os.path.normcase(os.path.abspath(self.doc.PathName)) == os.path.normcase(self.path)):
                self.doc.Save()
        except Exception:
            self.out['cleanup_error'] = traceback.format_exc()
        if error:
            self.out['error'] = error
        self.out['passed'] = not error and 'cleanup_error' not in self.out
        self.out['terminal'] = True
        self.save()
        AppDomain.CurrentDomain.SetData(KEY, None)
        no_other_documents = all((self.doc is not None and self.doc.Equals(doc) for doc in self.app.Application.Documents))
        if self.close_revit and no_other_documents:
            close = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.ExitRevit)
            if self.app.CanPostCommand(close):
                self.app.PostCommand(close)

    def fixture(self):
        doc = self.app.Application.NewProjectDocument(DB.UnitSystem.Imperial)
        tx = DB.Transaction(doc, 'Disposable preview fixture')
        tx.Start()
        try:
            src = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
            dst = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
            third = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
            src.SheetNumber, src.Name = ('P01', 'Drag source')
            dst.SheetNumber, dst.Name = ('P02', 'Drag target')
            third.SheetNumber, third.Name = ('P03', 'Navigation check')
            self.third = third.UniqueId
            text = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)

            def note(view, x, y, label):
                return DB.TextNote.Create(doc, view.Id, DB.XYZ(x, y, 0), label, text)
            n = note(src, 1.1, 0.9, 'Draggable note')
            for sheet in (src, dst, third):
                note(sheet, 0.05, 0.05, 'Lower left')
                note(sheet, 2.6, 1.7, 'Upper right')
                corners = [DB.XYZ(0, 0, 0), DB.XYZ(3, 0, 0), DB.XYZ(3, 2, 0), DB.XYZ(0, 2, 0)]
                for a, b in zip(corners, corners[1:] + corners[:1]):
                    doc.Create.NewDetailCurve(sheet, DB.Line.CreateBound(a, b))
            types = DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
            try:
                tp = next((t for t in types if t.ViewFamily == DB.ViewFamily.Drafting))
            finally:
                types.Dispose()
            view = DB.ViewDrafting.Create(doc, tp.Id)
            view.Name = 'Drafting detail'
            note(view, 0.0, 0.0, 'Fixture detail')
            doc.Create.NewDetailCurve(view, DB.Line.CreateBound(DB.XYZ.Zero, DB.XYZ(8.0, 5.0, 0)))
            doc.Regenerate()
            viewport = DB.Viewport.Create(doc, src.Id, view.Id, DB.XYZ(1.8, 0.4, 0))
            assert viewport is not None, 'Fixture drafting view could not be placed on the source sheet'
            self.notes, self.viewport, self.view = (n.UniqueId, viewport.UniqueId, view.UniqueId)
            self.source, self.target = (src.UniqueId, dst.UniqueId)
            if tx.Commit() != DB.TransactionStatus.Committed:
                raise RuntimeError('Revit did not commit the disposable sheet fixture.')
        finally:
            if tx.GetStatus() == DB.TransactionStatus.Started:
                tx.RollBack()
            tx.Dispose()
        doc.SaveAs(self.path)
        doc.Close(False)
        self.uidoc = self.app.OpenAndActivateDocument(self.path)
        self.doc = self.uidoc.Document
        self.uidoc.ActiveView = self.doc.GetElement(self.source)

    def snapshot(self, uid):
        return self.session.panel.snapshots.get(uid, {})

    def rows(self, uid):
        return self.snapshot(uid).get('items', [])

    def row(self, sheet, uid):
        return next((r for r in self.rows(sheet) if r['uid'] == uid), None)

    def ready(self):
        panel = self.session.panel
        return (not panel.pending and all(self.snapshot(uid).get('_bitmap') is not None
                                           for uid in (panel.source.uid, panel.target.uid)))

    def layout(self, source, target, active):
        panel = self.session.panel
        return (panel.source.uid == source and panel.target.uid == target and
                self.uidoc.ActiveView.UniqueId == active and self.ready())

    def choose(self, pane, uid):
        # Selecting the live WPF option exercises the real SelectionChanged event.
        pane.sheets.SelectedItem = next(item for item in pane.sheets.Items if item.Tag == uid)

    def confirm_current_choice(self, pane):
        combo = pane.sheets
        combo.IsDropDownOpen = True
        try:
            enter = KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(combo), 0, Key.Enter)
            enter.RoutedEvent = Keyboard.PreviewKeyDownEvent
            combo.RaiseEvent(enter)
        finally:
            combo.IsDropDownOpen = False

    def post(self, command):
        identifier = UI.RevitCommandId.LookupPostableCommandId(command)
        if not self.app.CanPostCommand(identifier):
            raise RuntimeError('Cannot post native command {}'.format(command))
        self.app.PostCommand(identifier)

    def click_swap(self):
        button = self.session.panel.window.FindName('swap')
        if button is None or not button.IsEnabled:
            raise AssertionError('The Swap button must be visible and enabled for two distinct sheets.')
        button.RaiseEvent(RoutedEventArgs(Button.ClickEvent))

    def selected_native_uids(self):
        return set(self.doc.GetElement(i).UniqueId for i in self.uidoc.Selection.GetElementIds())

    def drag(self, src, dst, uid):
        panel = self.session.panel
        src.fit_to(True)
        dst.fit_to(True)
        panel.window.UpdateLayout()
        row = self.row(src.uid, uid)
        rect = row['_bounds']
        origin = Point(*src.screen((rect[0] + rect[2]) * 0.5, (rect[1] + rect[3]) * 0.5))
        self.check('Preview hit test resolves selected item ' + uid[-6:], src.hit(origin) == uid)
        if src is dst:
            end = Point(origin.X + (-39 if origin.X > src.surface.ActualWidth * 0.6 else 39), origin.Y + (-29 if origin.Y > src.surface.ActualHeight * 0.6 else 29))
        else:
            end = Point(dst.surface.ActualWidth * 0.46, dst.surface.ActualHeight * 0.54)
        e0 = Pointer(src, origin)
        e1 = Pointer(dst, end)
        start = src.world(e0.GetPosition(src.surface))
        finish = dst.world(e1.GetPosition(dst.surface))
        src.pointer_down(src.surface, e0)
        self.check('Preview captured drag from its drawn placement', panel.gesture is not None)
        panel.pointer_move(panel.window, e1)
        self.check('Drag ghost renders on destination preview', dst.ghost.Children.Count > 0)
        panel.pointer_up(panel.window, e1)
        self.check('WPF release queued the move and cleared pointer capture', panel.pending and panel.gesture is None)
        self.check('Queued delta equals transformed pointer distance', abs(panel.pending['dx'] - (finish[0] - start[0])) < 1e-07 and abs(panel.pending['dy'] - (finish[1] - start[1])) < 1e-07)
        return DB.XYZ(finish[0] - start[0], finish[1] - start[1], 0)

    def active_viewports(self, sheet):
        return [self.doc.GetElement(i) for i in self.doc.GetElement(sheet).GetAllViewports()]

    def queue_close(self):
        panel = self.session.panel
        panel.window.Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, Action(panel.close))

    def visible_workspace(self):
        window = self.session.panel.window
        return window.IsVisible and window.WindowState != WindowState.Minimized and (not ComponentDispatcher.IsThreadModal)

    def exercise(self):
        self.fixture()
        self.boot = imp.load_source('nd_preview_qa_entry', os.path.join(ROOT, 'script.py'))
        self.session = self.boot.main(self.app)
        p = self.session.panel
        self.check('Real ribbon command opens modeless preview workspace', p.window.IsVisible and (not ComponentDispatcher.IsThreadModal))
        self.check('Re-entry reuses the same modeless session', self.boot.main(self.app) is self.session)
        yield ('initial paired Revit exports', self.ready)
        self.check('Two calibrated nonblank native sheet exports', all((self.snapshot(i).get('image_bounds') and self.snapshot(i)['_bitmap'].PixelWidth > 100 for i in (self.source, self.target))))
        self.check('Distinct source and target drawings', file_digest(self.snapshot(self.source)['image']) != file_digest(self.snapshot(self.target)['image']))
        self.check('Movable text and viewport accessible from preview', self.row(self.source, self.notes) and self.row(self.source, self.viewport))
        self.check('Source right, target left', p.source.surface.PointToScreen(Point(0, 0)).X > p.target.surface.PointToScreen(Point(0, 0)).X)
        image(p.window, os.path.join(self.folder, 'paired-previews.png'))
        panel = self.session.panel
        source, target, third = self.source, self.target, self.third
        self.check('Opening previews keeps the original sheet active', self.layout(source, target, source))
        self.choose(panel.target, third)
        yield 'target dropdown activates third sheet', lambda: self.layout(source, third, third)
        self.check('Target switch activates that sheet and preserves Source', self.layout(source, third, third))

        self.activations = []
        self.choose(panel.target, target)
        self.choose(panel.target, third)
        self.choose(panel.target, target)
        yield 'rapid dropdown choices settle on latest', lambda: self.layout(source, target, target)
        self.check('Rapid choices activate only the final target', self.activations == [target])

        self.uidoc.RequestViewChange(self.doc.GetElement(third))
        yield 'native third sheet replaces last active Target', lambda: self.layout(source, third, third)
        self.check('Native navigation updates Target without replacing Source', self.layout(source, third, third))
        self.uidoc.RequestViewChange(self.doc.GetElement(source))
        yield 'native switch to already visible Source', lambda: self.layout(source, third, source)
        self.uidoc.RequestViewChange(self.doc.GetElement(target))
        yield 'native third sheet replaces last active Source', lambda: self.layout(target, third, target)
        self.check('Native navigation updates Source without replacing Target', self.layout(target, third, target))

        self.choose(panel.source, source)
        yield 'source dropdown activates original sheet', lambda: self.layout(source, third, source)
        self.check('Source switch activates that sheet and preserves Target', self.layout(source, third, source))
        self.choose(panel.target, target)
        yield 'restore original target', lambda: self.layout(source, target, target)
        self.uidoc.RequestViewChange(self.doc.GetElement(source))
        yield 'restore original source for editing', lambda: self.layout(source, target, source)

        self.activations = []
        source_path, target_path = self.snapshot(source)['image'], self.snapshot(target)['image']
        panel.window.FindName('refresh').RaiseEvent(RoutedEventArgs(Button.ClickEvent))
        def refreshed():
            return (self.ready() and self.snapshot(source)['image'] != source_path and
                    self.snapshot(target)['image'] != target_path)
        yield 'refresh visible sheets without navigating Revit', refreshed
        self.check('Refresh re-exported both sheets without native navigation',
                   not self.activations and self.layout(source, target, source))
        self.confirm_current_choice(panel.target)
        yield 'confirm existing target with Enter', lambda: self.layout(source, target, target)
        self.check('Confirming the already selected target brings its sheet forward',
                   self.layout(source, target, target))
        self.confirm_current_choice(panel.source)
        yield 'confirm existing source with Enter', lambda: self.layout(source, target, source)
        self.check('Confirming the already selected source brings its sheet forward',
                   self.layout(source, target, source))
        element = self.doc.GetElement(self.notes)
        before = element.Coord
        change = self.drag(p.source, p.source, self.notes)
        self.check('Host model unchanged during WPF input', element.Coord.DistanceTo(before) < 1e-06)
        want = before + change

        def moved_source():
            row = self.row(self.source, self.notes)
            native = self.doc.GetElement(self.notes).Coord
            self.out['on_sheet'] = {'ready': bool(self.ready()), 'target': [want.X, want.Y], 'actual': [native.X, native.Y], 'snapshot_anchor': row.get('anchor') if row else None}
            return self.ready() and native.DistanceTo(want) < 1e-05 and row and (abs(row['anchor'][0] - want.X) < 1e-05)
        yield ('on-sheet drag and automatic export', moved_source)
        self.check('Text moves to decoded sheet coordinate, keeping its native ID', True)
        vp = self.doc.GetElement(self.viewport)
        before = vp.GetBoxCenter()
        delta = self.drag(p.source, p.target, self.viewport)
        expected = before + delta
        yield ('across-sheet drag and automatic export', lambda: self.ready() and bool(self.active_viewports(self.target)) and self.row(self.target, self.active_viewports(self.target)[0].UniqueId))
        mapped = self.active_viewports(self.target)[0]
        self.check('Cross-sheet viewport lands at its dropped sheet coordinate', mapped.GetBoxCenter().DistanceTo(expected) < 1e-05)
        self.check('Original view preserved, placement belongs only to destination', mapped.ViewId == self.doc.GetElement(self.view).Id and (not self.active_viewports(self.source)))
        self.viewport = mapped.UniqueId
        p.select(self.target, [self.viewport])
        p.window.WindowState = WindowState.Maximized
        p.target.edit_native()
        yield ('activate live Revit sheet and selected viewport', lambda: self.uidoc.ActiveView.UniqueId == self.target and self.doc.GetElement(self.viewport).Id in self.uidoc.Selection.GetElementIds())
        self.check('Edit in Revit selected the exact real viewport on the destination sheet', True)
        self.check('Both graphical panes stay visible and modeless during native editing', self.visible_workspace() and self.ready())
        self.check('Keyboard focus has left the preview workspace after Edit in Revit', not p.window.IsActive)
        self.check('Edit restores a maximized preview so the Revit drawing is exposed',
                   p.window.WindowState == WindowState.Normal)
        before_image = file_digest(self.snapshot(self.target)['image'])
        tx = DB.Transaction(self.doc, 'Simulate a native sheet edit')
        tx.Start()
        try:
            note_type = self.doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
            new = DB.TextNote.Create(self.doc, self.doc.GetElement(self.target).Id, DB.XYZ(0.9, 0.6, 0), 'Changed outside preview', note_type)
            self.new_note = new.UniqueId
            if tx.Commit() != DB.TransactionStatus.Committed:
                raise RuntimeError('Revit did not commit the native test edit.')
        finally:
            if tx.GetStatus() == DB.TransactionStatus.Started:
                tx.RollBack()
            tx.Dispose()
        yield ('refresh after real native sheet edit', lambda: self.ready() and self.row(self.target, self.new_note))
        self.check('Native edit refreshed the visible preview drawing and item list without reopening', self.visible_workspace() and file_digest(self.snapshot(self.target)['image']) != before_image)
        self.check('Background refresh preserved active native sheet and selection', self.uidoc.ActiveView.UniqueId == self.target and self.doc.GetElement(self.viewport).Id in self.uidoc.Selection.GetElementIds())
        native_selection = self.selected_native_uids()
        self.check('The real destination viewport is selected before Swap', self.viewport in native_selection)
        self.activations = []
        self.swap_transactions = []
        self.click_swap()
        yield 'Swap flips both preview roles', lambda: self.layout(target, source, target)
        self.check('Swap flipped both panes and kept native sheet and selection',
                   not self.activations and self.selected_native_uids() == native_selection)
        self.click_swap()
        yield 'second Swap restores original roles', lambda: self.layout(source, target, target)
        self.check('Two swaps restored the original pair without changing native selection',
                   not self.activations and self.selected_native_uids() == native_selection)

        # Select another sheet but click Swap on the same WPF turn, before Revit
        # services the queued navigation. The previews flip as requested; the
        # user continues to edit the original native drawing.
        self.choose(panel.target, third)
        self.click_swap()
        settle = Stopwatch.StartNew()
        yield 'Swap cancels queued selector activation', lambda: (
            settle.Elapsed.TotalMilliseconds >= 500 and self.layout(third, source, target))
        self.check('Swap canceled pending sheet navigation and kept the selected viewport',
                   not self.activations and self.selected_native_uids() == native_selection)
        self.click_swap()
        self.choose(panel.target, target)
        yield 'restore visible pair after queued-navigation check', lambda: self.layout(source, target, target)
        self.check('Swap and navigation generated no model-change transactions', not self.swap_transactions)
        self.swap_transactions = None
        self.post(UI.PostableCommand.Undo)
        yield 'native Undo refreshes the visible sheet', lambda: (
            self.ready() and self.doc.GetElement(self.new_note) is None and
            not self.row(self.target, self.new_note))
        self.check('Undo removed the native note from the visible preview', self.visible_workspace())
        self.check('First Undo after swapping undid the previous real sheet edit', self.doc.GetElement(self.new_note) is None)
        self.post(UI.PostableCommand.Redo)
        yield 'native Redo refreshes the visible sheet', lambda: (
            self.ready() and self.doc.GetElement(self.new_note) is not None and
            self.row(self.target, self.new_note))
        self.check('Redo restored the note to the visible sheet without reopening', self.visible_workspace())
        before = self.doc.GetElement(self.new_note).Coord
        delta = self.drag(p.target, p.source, self.new_note)
        expected = before + delta

        def reverse_note():
            rows = [self.doc.GetElement(r['uid']) for r in self.rows(self.source)]
            return next((e for e in rows if isinstance(e, DB.TextNote) and e.Text.strip() == 'Changed outside preview'), None)
        yield ('reverse target-to-source drag', lambda: self.ready() and reverse_note() is not None)
        self.check('Target-to-source text transfer preserves requested sheet position', reverse_note().Coord.DistanceTo(expected) < 1e-05)
        old = self.session
        tmp = getattr(old, 'temp', None)
        self.queue_close()
        yield ('WPF dispatcher close and deferred native cleanup', lambda: old.disposed and AppDomain.CurrentDomain.GetData(SESSION) is None)
        self.check('Title-bar close released native handlers and preview cache', not old.cleanup_errors and (not tmp or not os.path.exists(tmp)))
        self.session = self.boot.main(self.app)
        yield ('reopen two fresh previews', self.ready)
        self.check('Fresh modeless session renders both sheets after reopen', self.session is not old and self.session.panel.window.IsVisible)
        self.queue_close()
        yield ('second safe dispatcher close', lambda: self.session.disposed and AppDomain.CurrentDomain.GetData(SESSION) is None)
        self.check('Second close recorded no cleanup errors', not self.session.cleanup_errors)

def start(app, output=None, close_revit=False):
    if app.ActiveUIDocument is not None or app.Application.Documents.Size:
        raise ValueError('Run the graphical smoke in a separate Revit process with no open project or family.')
    if AppDomain.CurrentDomain.GetData(KEY) is not None:
        raise ValueError('A graphical workspace smoke is already running.')
    output = output or os.path.join(tempfile.gettempdir(), 'NdevMoveViewsQA')
    if not os.path.isdir(output):
        os.makedirs(output)
    runner = WorkspaceSmoke(app, output, close_revit)
    AppDomain.CurrentDomain.SetData(KEY, runner)
    runner.start()
    return runner.folder
if __name__ == '__main__':
    module = imp.load_source('ndev_main_graphical_workspace_smoke', __file__)
    print(module.start(__revit__))
