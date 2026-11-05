# -*- coding: utf-8 -*-
"""Display two modeless sheet previews. All Revit calls run inside API callbacks."""
import imp
import os
import shutil
import tempfile
from contextlib import contextmanager

from pyrevit import DB, UI
from System import Action, AppDomain, TimeSpan
from System.Collections.Generic import List
from System.Diagnostics import Stopwatch
from System.Windows import WindowState
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Threading import DispatcherPriority, DispatcherTimer

KEY = 'NdevTools.Main.MoveViews.Window'
VERSION = 'preview-7.4'


def _load(bundle, name):
    return imp.load_source('ndev_main_move_' + name, os.path.join(bundle, name + '.py'))


class Handler(UI.IExternalEventHandler):
    def __init__(self, session):
        self.session = session

    def GetName(self):
        return 'Move Views'

    def Execute(self, app):
        self.session.execute(app)


class Session(object):
    version = VERSION

    def __init__(self, app, bundle, pair=None):
        uidoc = app.ActiveUIDocument
        self.doc = uidoc.Document
        self.title = self.doc.Title
        self.preview = _load(bundle, 'sheet_preview')
        self.moves = _load(bundle, 'sheet_moves')
        self.sheets = self.preview.list_sheets(self.doc)
        if not self.sheets:
            raise ValueError('Create a drawing sheet first.')
        self.sheet_ids = {}
        self.index_sheets()
        ids = [row['uid'] for row in self.sheets]
        active = uidoc.ActiveView.UniqueId
        source = active if active in ids else ids[0]
        target = next((uid for uid in ids if uid != source), source)
        if pair is not None:
            old_source, old_target = pair
            if old_source in ids:
                source = old_source
            target = old_target if old_target in ids else next((uid for uid in ids if uid != source), source)
        self.active_side = 'target' if active == target and source != target else 'source'
        self.navigation = None
        self.nav_ready = False
        self.follow = None
        self.to_draw = set()
        self.changed_sheets = set()
        self.inventory_dirty = False
        self.watches = {}
        self.images = {}
        self.operation = None
        self.committing = False
        self.running = self.scheduled = False
        self.closed = self.disposed = self.cleanup_armed = False
        self.cleanup_errors = []
        self.registered = []
        self.panel = _load(bundle, 'sheet_ui').Panel(bundle, self.sheets, source, target,
                                                     self.request, self.close)
        WindowInteropHelper(self.panel.window).Owner = app.MainWindowHandle
        self.temp = tempfile.mkdtemp(prefix='NdevSheetPreview-')
        self.handler = Handler(self)
        self.event = None
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromMilliseconds(700)
        self.nav_timer = DispatcherTimer()
        self.nav_timer.Interval = TimeSpan.FromMilliseconds(160)
        self.sheet_filter = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_Sheets)
        try:
            self.event = UI.ExternalEvent.Create(self.handler)
            self.timer.Tick += self.refresh_tick
            self.nav_timer.Tick += self.navigation_tick
            self.panel.window.StateChanged += self.state_changed
            app.Application.DocumentChanged += self.changed
            self.registered.append('changed')
            app.Application.DocumentClosing += self.closing
            self.registered.append('closing')
            app.ViewActivated += self.activated
            self.registered.append('activated')
        except Exception:
            self._dispose_in_api(app)
            raise

    def index_sheets(self):
        self.sheet_ids = dict((self.doc.GetElement(row['uid']).Id, row['uid']) for row in self.sheets)

    def request(self, action, payload):
        if self.closed:
            return False
        if action == 'preview':
            self.to_draw.add(payload['sheet'])
        elif action == 'refresh':
            self.inventory_dirty = True
            self.to_draw.update(self.panel.visible_sheet_ids())
        elif action == 'swap':
            if (self.operation or self.panel.pending or not self.panel.source.uid or not self.panel.target.uid or
                    self.panel.source.uid == self.panel.target.uid or
                    (payload.get('source'), payload.get('target')) != (self.panel.target.uid, self.panel.source.uid)):
                return False
            self.cancel_navigation()
            self.follow = None
            self.active_side = 'source' if self.active_side == 'target' else 'target'
            return True
        elif action == 'navigate':
            if self.operation and self.operation[0] == 'edit':
                self.operation = None
            self.follow = None
            self.navigation = (payload['side'], payload['sheet'], Stopwatch.StartNew())
            self.nav_ready = False
            self.nav_timer.Stop()
            self.nav_timer.Start()
            return True
        elif action in ('move', 'edit'):
            if self.operation:
                if action == 'move':
                    self.panel.move_result(False, 'Finish the current operation and drag again.', {})
                return False
            data = dict(payload)
            if action == 'move':
                items = self.panel.snapshots.get(data['source'], {}).get('items', [])
                chosen = set(data['uids'])
                data['anchors'] = dict((row['uid'], row['anchor']) for row in items
                                       if row['uid'] in chosen)
            else:
                self.cancel_navigation()
                data['requested_at'] = Stopwatch.StartNew()
            self.operation = (action, data)
        else:
            return False
        self.schedule()
        return True

    def schedule(self):
        if self.disposed or self.scheduled or self.running or self.cleanup_armed:
            return
        self.scheduled = True
        self.panel.window.Dispatcher.BeginInvoke(DispatcherPriority.Background, Action(self.raise_event))

    def raise_event(self):
        self.scheduled = False
        if self.disposed or self.cleanup_armed:
            return
        try:
            result = self.event.Raise()
            if result not in (UI.ExternalEventRequest.Accepted, UI.ExternalEventRequest.Pending):
                raise ValueError('Finish the current Revit command and try again.')
        except Exception as error:
            if not self.closed:
                self.fail_operation(unicode(error))

    def fail_operation(self, message):
        operation, self.operation = self.operation, None
        if operation and operation[0] == 'move':
            self.panel.move_result(False, message, {})
        else:
            self.panel.status(message)

    def move(self, data):
        if len(data['anchors']) != len(data['uids']):
            raise ValueError('The selection changed. Refresh the preview and select the items again.')
        for uid, anchor in data['anchors'].items():
            item = self.doc.GetElement(uid)
            if item is None or not self.moves.supported(self.doc, item):
                raise ValueError('A selected item changed. Refresh the preview and select it again.')
            point = self.moves.item_anchor(item)
            if max(abs(point.X - anchor[0]), abs(point.Y - anchor[1])) > 1e-6:
                raise ValueError('A selected item moved since the preview. Refresh and drag it again.')
        self.committing = True
        try:
            mapping = self.moves.move(self.doc, data['source'], data['target'],
                                      data['uids'], data['dx'], data['dy'])
        finally:
            self.committing = False
        self.to_draw.update((data['source'], data['target']))
        self.operation = None  # Never report a successful native commit as a failed move.
        self.panel.move_result(True, 'Moved {} sheet item(s).'.format(len(mapping)), mapping)

    def edit(self, app, uidoc, data):
        uid = data['sheet']
        if uid not in self.panel.visible_sheet_ids() or data['requested_at'].Elapsed.TotalSeconds > 10:
            raise ValueError('Choose Edit in Revit again for the current sheet.')
        sheet = self.doc.GetElement(uid)
        if not isinstance(sheet, DB.ViewSheet) or sheet.IsPlaceholder:
            raise ValueError('This sheet is unavailable. Refresh and choose a current sheet.')
        ids = List[DB.ElementId]()
        for key in data.get('uids', []):
            item = self.doc.GetElement(key)
            if item is None or not self.moves.supported(self.doc, item):
                raise ValueError('A selected placement changed. Refresh and select the items again.')
            owner = item.SheetId if isinstance(item, DB.Viewport) else item.OwnerViewId
            if owner != sheet.Id:
                raise ValueError('A selected placement moved to another sheet. Refresh and try again.')
            ids.Add(item.Id)
        # This one explicit handoff runs synchronously inside the ExternalEvent. There
        # is no delayed navigation which could later override the user's active view.
        self.operation = None
        if data.get('side') in ('source', 'target'):
            self.active_side = data['side']
        if uidoc.ActiveView.Id != sheet.Id:
            uidoc.ActiveView = sheet
        uidoc.Selection.SetElementIds(ids)
        if self.panel.window.WindowState == WindowState.Maximized:
            self.panel.window.WindowState = WindowState.Normal
        # Revit and its owned WPF window share the UI thread. Only this explicit
        # edit hands keyboard input back to Revit; both sheet previews stay open.
        import clr
        clr.AddReference('ControlzEx')
        from ControlzEx.Standard import NativeMethods
        NativeMethods.SetActiveWindow(app.MainWindowHandle)
        NativeMethods.SetFocus(app.MainWindowHandle)
        self.panel.status(u'Editing {} in Revit. Both previews update as you work.'.format(
            self.preview.sheet_label(sheet)))

    def cancel_navigation(self):
        self.nav_timer.Stop()
        self.navigation = None
        self.nav_ready = False

    def navigation_tick(self, sender, args):
        self.nav_timer.Stop()
        if not self.closed and self.navigation:
            self.nav_ready = True
            self.schedule()

    def navigate(self, uidoc):
        side, uid, requested = self.navigation
        self.cancel_navigation()
        pane = self.panel.source if side == 'source' else self.panel.target
        if pane.uid != uid:
            return
        if requested.Elapsed.TotalSeconds > 10:
            raise ValueError('Finish the current Revit command, then choose Edit in Revit on this sheet.')
        sheet = self.doc.GetElement(uid)
        if not isinstance(sheet, DB.ViewSheet) or sheet.IsPlaceholder:
            raise ValueError('This sheet is unavailable. Refresh the list of sheets.')
        self.active_side = side
        if uidoc.ActiveView.Id != sheet.Id:
            uidoc.ActiveView = sheet
        self.panel.status(u'{} is active in Revit.'.format(self.preview.sheet_label(sheet)))

    def release_image(self, path):
        if path:
            folder = os.path.dirname(os.path.abspath(path))
            if os.path.dirname(folder) == os.path.abspath(self.temp):
                shutil.rmtree(folder, ignore_errors=True)

    def draw(self, uid):
        if self.doc.GetElement(uid) is None:
            self.panel.requested.discard(uid)
            return
        snap = self.preview.snapshot(self.doc, uid, self.temp, self.moves)
        self.watches[uid] = snap.pop('_watch')
        previous = self.images.get(uid)
        try:
            self.panel.update_snapshot(snap)
        except Exception:
            self.release_image(snap.get('image'))
            raise
        self.images[uid] = snap.get('image')
        if previous != self.images[uid]:
            self.release_image(previous)
        if snap.get('message'):
            self.panel.status(u'{} — {}'.format(snap['label'], snap['message']))

    def execute(self, app):
        if self.closed:
            self.arm_cleanup(app)
            return
        self.running = True
        moved = False
        try:
            uidoc = app.ActiveUIDocument
            if uidoc is None or not self.doc.IsValidObject or not self.doc.Equals(uidoc.Document):
                self.to_draw.clear()
                self.cancel_navigation()
                self.follow = None
                self.fail_operation(u'Activate {} in Revit to continue.'.format(self.title))
                return
            if self.operation is not None:
                action, data = self.operation
                if action == 'move':
                    self.move(data)
                    moved = True
                else:
                    self.edit(app, uidoc, data)
            if self.nav_ready and self.navigation:
                self.navigate(uidoc)
            if self.panel.window.WindowState == WindowState.Minimized:
                return
            if self.inventory_dirty:
                self.inventory_dirty = False
                sheets = self.preview.list_sheets(self.doc)
                if self.sheets != sheets:
                    self.sheets = sheets
                    self.index_sheets()
                    self.panel.set_sheets(sheets)
            if self.follow:
                side, uid = self.follow
                self.follow = None
                if uidoc.ActiveView.UniqueId == uid:
                    self.panel.follow_sheet(side, uid)
            visible = self.panel.visible_sheet_ids()
            self.to_draw.intersection_update(visible)
            for uid in list(self.watches):
                if uid not in visible:
                    self.watches.pop(uid)
                    self.panel.snapshots.pop(uid, None)
                    self.panel.requested.discard(uid)
                    self.release_image(self.images.pop(uid, None))
            # Normal background refresh gives Revit a turn between exports. After
            # a drop, bring both panes up to date before accepting another gesture
            # so the next drag starts from the committed paper coordinates.
            for uid in visible:
                if uid in self.to_draw:
                    self.to_draw.remove(uid)
                    self.draw(uid)
                    if not moved:
                        break
        except Exception as error:
            if moved:
                self.panel.status(u'Move committed. Refresh the sheet preview. {}'.format(error))
            else:
                self.fail_operation(unicode(error))
        finally:
            self.running = False
            if self.closed:
                self.arm_cleanup(app)
            elif self.operation or self.nav_ready or ((self.to_draw or self.follow) and
                                                      self.panel.window.WindowState != WindowState.Minimized):
                self.schedule()

    def changed(self, sender, args):
        if self.closed or self.committing or not self.doc.Equals(args.GetDocument()):
            return
        visible = set(self.panel.visible_sheet_ids())
        deleted = set(args.GetDeletedElementIds())
        if (args.GetAddedElementIds(self.sheet_filter).Count or args.GetModifiedElementIds(self.sheet_filter).Count
                or deleted.intersection(self.sheet_ids)):
            self.inventory_dirty = True
        added, modified = args.GetAddedElementIds(), args.GetModifiedElementIds()
        if added.Count + modified.Count > 100:
            self.changed_sheets.update(visible)
        else:
            changes = list(added) + list(modified)
            elements = [self.doc.GetElement(i) for i in changes]
            owners = set(e.OwnerViewId for e in elements if e is not None)
            owner_sheets = set(e.SheetId for e in elements if isinstance(e, DB.Viewport))
            changed = set(changes)
            # Non-view-owned model/type changes can affect the content of placed
            # views or schedules. Deleted elements have lost their owner; err on
            # the side of refreshing a visible view in that case.
            model_changed = bool(deleted or DB.ElementId.InvalidElementId in owners)
            for uid in visible:
                watched, views = self.watches.get(uid, (set(), set()))
                if (not watched or watched.intersection(changed) or watched.intersection(deleted) or
                        watched.intersection(owners) or watched.intersection(owner_sheets) or
                        views.intersection(changed) or views.intersection(owners) or (views and model_changed)):
                    self.changed_sheets.add(uid)
        if self.changed_sheets or self.inventory_dirty:
            self.debounce()

    def debounce(self):
        self.timer.Stop()
        if self.panel.window.WindowState != WindowState.Minimized:
            self.timer.Start()

    def refresh_tick(self, sender, args):
        self.timer.Stop()
        if not self.closed and self.panel.window.WindowState != WindowState.Minimized:
            self.to_draw.update(self.changed_sheets)
            self.changed_sheets.clear()
            self.schedule()

    def state_changed(self, sender, args):
        if self.closed:
            return
        if self.panel.window.WindowState == WindowState.Minimized:
            self.timer.Stop()
        elif self.changed_sheets or self.inventory_dirty or self.to_draw or self.follow:
            self.debounce()

    def activated(self, sender, args):
        if self.closed:
            self.arm_cleanup(sender)
            return
        # A person switching views while a click waits for Revit has taken
        # control back. Discard that edit rather than replaying it later.
        if self.operation and self.operation[0] == 'edit':
            self.fail_operation('Edit in Revit canceled because the active view changed.')
        self.cancel_navigation()
        self.follow = None
        view = args.CurrentActiveView
        if view is not None and self.doc.Equals(view.Document):
            if isinstance(view, DB.ViewSheet) and not view.IsPlaceholder:
                visible = [pane.side for pane in self.panel.panes if pane.uid == view.UniqueId]
                if visible:
                    if self.active_side not in visible:
                        self.active_side = visible[0]
                else:
                    self.follow = (self.active_side, view.UniqueId)
                    if view.Id not in self.sheet_ids:
                        self.inventory_dirty = True
                    self.schedule()
            old = args.PreviousActiveView
            if old is None or not self.doc.Equals(old.Document):
                self.changed_sheets.update(self.panel.visible_sheet_ids())
                self.inventory_dirty = True
                self.debounce()
        elif self.operation:
            self.fail_operation(u'Activate {} before moving sheet items.'.format(self.title))

    def activate(self, app):
        if self.panel.window.WindowState == WindowState.Minimized:
            self.panel.window.WindowState = WindowState.Normal
        self.panel.window.Activate()

    def close(self):
        if not self.closed:
            self.closed = True
            self.operation = None
            self.cancel_navigation()
            self.follow = None
            self.to_draw.clear()
            self.timer.Stop()
            self.schedule()


    def closing(self, sender, args):
        if self.doc.Equals(args.Document):
            self.panel.close()
            # Use a UIApplication created from this callback's live database application.
            # The modeless close has also queued an ExternalEvent as a fallback.
            with self.cleanup_step(None, 'arm cleanup during document closing'):
                self.arm_cleanup(UI.UIApplication(args.Document.Application))

    @contextmanager
    def cleanup_step(self, app, name):
        """Keep one failed native release from escaping a callback or blocking other releases."""
        try:
            yield
        except Exception as error:
            message = u'Move Views cleanup [{}]: {}'.format(name, error)
            self.cleanup_errors.append(message)
            try:
                app.Application.WriteJournalComment(message, True)
            except Exception:
                try:
                    from pyrevit.coreutils.logger import get_logger
                    get_logger('NdevMoveViews').warning(message)
                except Exception:
                    pass  # Keep the original diagnostic on this session during host shutdown.

    def arm_cleanup(self, app):
        # Called only from a Revit API callback. Dispose the ExternalEvent on a
        # subsequent Idling callback, after its own Execute and any queued Raise.
        if self.disposed or self.cleanup_armed:
            return
        with self.cleanup_step(app, 'subscribe cleanup Idling'):
            app.Idling += self.cleanup_on_idle
            self.cleanup_armed = True

    def cleanup_on_idle(self, app, args):
        if self.disposed or self.running:
            return
        pending = None
        with self.cleanup_step(app, 'inspect ExternalEvent state'):
            pending = self.event.IsPending
        if pending:
            return
        self._dispose_in_api(app, release_event=pending is not None)

    def _dispose_in_api(self, app, release_event=True):
        if self.disposed:
            return
        self.disposed = True
        if self.cleanup_armed:
            with self.cleanup_step(app, 'detach cleanup Idling'):
                app.Idling -= self.cleanup_on_idle
            self.cleanup_armed = False
        with self.cleanup_step(app, 'release preview timer'):
            self.timer.Stop()
            self.timer.Tick -= self.refresh_tick
        with self.cleanup_step(app, 'release sheet chooser timer'):
            self.cancel_navigation()
            self.nav_timer.Tick -= self.navigation_tick
        with self.cleanup_step(app, 'detach window StateChanged'):
            self.panel.window.StateChanged -= self.state_changed
        if 'activated' in self.registered:
            with self.cleanup_step(app, 'detach ViewActivated'):
                app.ViewActivated -= self.activated
        if 'closing' in self.registered:
            with self.cleanup_step(app, 'detach DocumentClosing'):
                app.Application.DocumentClosing -= self.closing
        if 'changed' in self.registered:
            with self.cleanup_step(app, 'detach DocumentChanged'):
                app.Application.DocumentChanged -= self.changed
        with self.cleanup_step(app, 'release sheet filter'):
            self.sheet_filter.Dispose()
        if release_event and self.event is not None:
            with self.cleanup_step(app, 'release ExternalEvent'):
                self.event.Dispose()
        with self.cleanup_step(app, 'clear workspace registry'):
            if AppDomain.CurrentDomain.GetData(KEY) is self:
                AppDomain.CurrentDomain.SetData(KEY, None)
        with self.cleanup_step(app, 'release temporary preview images'):
            if (os.path.dirname(os.path.abspath(self.temp)) == os.path.abspath(tempfile.gettempdir()) and
                    os.path.basename(self.temp).startswith('NdevSheetPreview-')):
                shutil.rmtree(self.temp, ignore_errors=True)



def open_window(app, bundle):
    uidoc = app.ActiveUIDocument
    if uidoc is None or uidoc.Document.IsFamilyDocument:
        raise ValueError('Open a Revit project containing drawing sheets.')
    previous = AppDomain.CurrentDomain.GetData(KEY)
    pair = None
    if previous is not None and not previous.closed:
        if previous.doc.Equals(uidoc.Document):
            if getattr(previous, 'version', None) == VERSION:
                previous.activate(app)
                return previous
            # Keep the sheet roles when upgrading an open, older workspace.
            pair = tuple(getattr(getattr(previous.panel, role, None), 'uid', None) or
                         getattr(previous, role, None) for role in ('source', 'target'))
        if not hasattr(previous, 'arm_cleanup') and previous.event.IsPending:
            raise ValueError('The previous Move Views command is finishing. Open it again in a moment.')
        previous.panel.close()
        if hasattr(previous, 'arm_cleanup'):
            previous.arm_cleanup(app)
        elif not previous.disposed:
            # Retire the legacy session here, inside the external command.
            previous.dispose()
    session = Session(app, bundle, pair)
    AppDomain.CurrentDomain.SetData(KEY, session)
    try:
        session.panel.show()
    except Exception:
        session.panel.close()
        session.arm_cleanup(app)
        raise
    return session
