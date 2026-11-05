# -*- coding: utf-8 -*-
"""Modeless two-sheet picker. All model work is dispatched by the owning bridge."""
from __future__ import division

import math
import os

import clr
clr.AddReference('WindowsBase')
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
from System.IO import File, MemoryStream, StreamReader
from System import AppDomain
from System.Windows import FlowDirection, SystemParameters
from System.Windows.Controls import Canvas, ComboBoxItem, Image, ListBoxItem, TextBlock
from System.Windows.Input import Cursors, Key, Keyboard, ModifierKeys, Mouse, MouseButton
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, DoubleCollection, Stretch
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
from System.Windows.Shapes import Rectangle

try:
    text_type = unicode
except NameError:
    text_type = str

_COLORS = {}
HUMOR_PREFERENCE = 'NdevTools.Main.MoveViews.BimHumor'
SHEET_JOKES = (
    'My sheet set has a plot twist. It is on the next page.',
    'The title block gets the credit. The viewport does the heavy lifting.',
    'I asked for a little detail. Revit gave me a whole sheet.',
    'Two views walked into a sheet. One asked the other for some space.',
    'My favorite scale is the one that fits before the meeting.',
    'The legend knows all the symbols and still asks for directions.',
)
def brush(color):
    if color not in _COLORS:
        value = BrushConverter().ConvertFromString(color)
        value.Freeze()
        _COLORS[color] = value
    return _COLORS[color]


def bounds(values):
    if not values or len(values) != 4:
        return None
    try:
        x0, y0, x1, y1 = map(float, values)
        if any(math.isnan(v) or math.isinf(v) for v in (x0,y0,x1,y1)):
            return None
        return min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)
    except (TypeError, ValueError):
        return None


def eligible(item):
    # Native inventory owns eligibility. Defend against standalone line entries.
    kind = ''.join(c for c in item.get('kind','').lower() if c.isalnum())
    return bool(item.get('uid')) and kind not in (
        'line','lines','detailline','detaillines','detailcurve','detailcurves',
        'modelline','modellines','modelcurve','modelcurves','curveelement','curveelements')


def box(canvas, left, top, width, height, fill, stroke=None, weight=1., dashed=False):
    shape = Rectangle()
    shape.Width, shape.Height = max(0.,width), max(0.,height)
    shape.Fill = brush(fill)
    if stroke:
        shape.Stroke = brush(stroke)
        shape.StrokeThickness = weight
    if dashed:
        pattern = DoubleCollection()
        pattern.Add(4.)
        pattern.Add(2.)
        shape.StrokeDashArray = pattern
    Canvas.SetLeft(shape,left)
    Canvas.SetTop(shape,top)
    shape.IsHitTestVisible = False
    canvas.Children.Add(shape)
    return shape


def put_text(canvas, value, left, top, color):
    label = TextBlock()
    label.Text = value
    label.Foreground = brush(color)
    label.FontSize = 13
    label.IsHitTestVisible = False
    Canvas.SetLeft(label,left)
    Canvas.SetTop(label,top)
    canvas.Children.Add(label)


def read_window(bundle, filename):
    reader = StreamReader(os.path.join(bundle, filename))
    try:
        return XamlReader.Parse(reader.ReadToEnd())
    finally:
        reader.Dispose()


class Pane(object):
    def __init__(self, panel, side):
        self.panel, self.side = panel, side
        host = panel.window.FindName(side)
        host.ApplyTemplate()
        for name in ('title','sheets','views','surface','ghost','counts','details','showAll','selectAll','fit','editNative'):
            setattr(self,name,host.Template.FindName(name,host))
        self.title.Text = side.capitalize() + ' sheet'
        self.uid = None
        self.scale = None
        self.fit_mode = False
        self.cx, self.cy = 0., 0.
        self.syncing = False
        self.list_rows = {}
        self.sheets.SelectionChanged += self.sheet_changed
        self.sheets.PreviewKeyDown += self.confirm_sheet_key
        self.details.SelectionChanged += self.selection_changed
        self.views.PreviewKeyDown += self.list_key
        self.details.PreviewKeyDown += self.list_key
        self.editNative.Click += self.edit_native
        self.selectAll.Click += self.select_all
        self.showAll.Click += lambda s,e: self.fit_to(True)
        self.fit.Click += lambda s,e: self.fit_to(False)
        self.surface.SizeChanged += self.resized
        self.surface.MouseWheel += self.zoom
        self.surface.MouseDown += self.pointer_down

    def snapshot(self):
        return self.panel.snapshots.get(self.uid,{})

    def options(self, sheets, chosen):
        self.syncing = True
        try:
            self.sheets.Items.Clear()
            for row in sheets:
                option = ComboBoxItem()
                option.Content, option.Tag = row['label'], row['uid']
                option.PreviewMouseLeftButtonUp += self.confirm_sheet_click
                self.sheets.Items.Add(option)
                if row['uid'] == chosen:
                    self.sheets.SelectedItem = option
        finally:
            self.syncing = False
        self.change_sheet(chosen)

    def sheet_changed(self, sender, event):
        if self.syncing:
            return
        item = self.sheets.SelectedItem
        uid = item.Tag if item is not None else None
        if uid == self.uid:
            return
        self.change_sheet(uid)
        if self.panel.shown and uid:
            self.panel.request('navigate', {'side': self.side, 'sheet': uid})
            self.panel.ask_preview(uid)

    def confirm_sheet_click(self, option, event):
        # WPF raises no SelectionChanged when the user explicitly picks the
        # current row again after editing the other sheet in Revit.
        if (self.panel.shown and self.sheets.IsDropDownOpen and option.IsMouseOver
                and option.Tag == self.uid and not self.syncing):
            self.panel.request('navigate', {'side': self.side, 'sheet': self.uid})

    def confirm_sheet_key(self, sender, event):
        if (self.panel.shown and self.sheets.IsDropDownOpen and event.Key == Key.Enter
                and self.uid and not self.syncing):
            self.panel.request('navigate', {'side': self.side, 'sheet': self.uid})

    def change_sheet(self, uid):
        if uid != self.uid:
            self.panel.cancel_gesture()
            self.views.IsChecked = False
            self.uid = uid
            self.scale = None
            self.fit_mode = False
            for cached_uid, cached in self.panel.snapshots.items():
                if cached_uid not in self.panel.visible_sheet_ids():
                    cached['_bitmap'] = None
        self.populate()

    def selected(self):
        return self.panel.selections.get(self.uid,set())

    def populate(self):
        self.syncing = True
        try:
            self.details.Items.Clear()
            self.list_rows = {}
            for row in self.snapshot().get('items',[]):
                uid = row['uid']
                item = ListBoxItem()
                item.Tag = uid
                self.list_rows[uid] = item
                self.details.Items.Add(item)
            self.paint_list()
        finally:
            self.syncing = False
        if self.scale is None:
            self.fit_to(False)
        else:
            self.draw()
        self.panel.update_actions()

    def paint_list(self):
        busy = self.syncing
        self.syncing = True
        try:
            chosen = self.selected()
            same = set(item.Tag for item in self.details.SelectedItems) == chosen
            if not same:self.details.SelectedItems.Clear()
            for row in self.snapshot().get('items',[]):
                item = self.list_rows.get(row['uid'])
                if item is None:
                    continue
                label = row.get('label') or row.get('kind','Detail')
                item.Content = label
                item.ToolTip = row.get('kind','') + u'  ·  ' + label
                if not same and row['uid'] in chosen:
                    self.details.SelectedItems.Add(item)
            self.counts.Text = '%s of %s selected' % (len(chosen.intersection(self.list_rows)),len(self.list_rows))
        finally:
            self.syncing = busy

    def selection_changed(self, sender, event):
        if not self.syncing and self.uid:
            self.panel.select(self.uid,[i.Tag for i in self.details.SelectedItems])

    def list_key(self, sender, event):
        if event.Key == Key.Escape and self.views.IsChecked:
            self.views.IsChecked = False
            self.views.Focus()
            event.Handled = True
        elif sender == self.views and event.Key == Key.Down and self.list_rows:
            self.views.IsChecked = True
            self.details.Focus()
            event.Handled = True

    def edit_native(self, sender=None, event=None):
        if self.uid and not self.panel.pending:
            self.panel.cancel_gesture()
            try:
                self.panel.request('edit', {'side': self.side, 'sheet': self.uid,
                                            'uids': sorted(self.selected())})
            except Exception as error:
                self.panel.status(text_type(error))

    def select_all(self, sender, event):
        if self.uid:
            self.panel.select(self.uid,self.list_rows.keys())

    def resized(self, sender, event):
        if self.fit_mode is not None:
            self.fit_to(self.fit_mode)
        else:
            self.draw()

    def fit_to(self, include_items):
        self.fit_mode = include_items
        data=self.snapshot()
        rect=bounds(data.get('paper_bounds')) or bounds(data.get('image_bounds')) or bounds(data.get('bounds'))
        width, height = self.surface.ActualWidth,self.surface.ActualHeight
        if rect and width>10 and height>10:
            extents = [rect]
            if include_items:
                extents.extend(r['_bounds'] for r in self.snapshot()['items'] if r['_bounds'])
            left,bottom = min(r[0] for r in extents),min(r[1] for r in extents)
            right,top = max(r[2] for r in extents),max(r[3] for r in extents)
            self.cx,self.cy = (left+right)*.5,(bottom+top)*.5
            self.scale = min(width*.86/max(.01,right-left),height*.86/max(.01,top-bottom))
        self.draw()

    def screen(self, x, y):
        return (self.surface.ActualWidth*.5+(x-self.cx)*self.scale,
                self.surface.ActualHeight*.5-(y-self.cy)*self.scale)

    def world(self, point):
        return (self.cx+(point.X-self.surface.ActualWidth*.5)/self.scale,
                self.cy-(point.Y-self.surface.ActualHeight*.5)/self.scale)

    def rect_px(self, rect, dx=0., dy=0.):
        x0,y0,x1,y1=rect
        x,y=self.screen(x0+dx,y1+dy)
        return x,y,(x1-x0)*self.scale,(y1-y0)*self.scale

    def outline(self, canvas, rect, fill, stroke, weight=1., dashed=False, dx=0., dy=0.):
        x,y,w,h=self.rect_px(rect,dx,dy)
        if max(w,h)<.1:
            w,h=3.,3.
        box(canvas,x,y,max(3.,w),max(3.,h),fill,stroke,weight,dashed)

    def draw(self):
        self.surface.Children.Clear()
        self.ghost.Children.Clear()
        data=self.snapshot()
        sheet=bounds(data.get('paper_bounds')) or bounds(data.get('image_bounds')) or bounds(data.get('bounds'))
        if not self.scale or not sheet:
            put_text(self.surface,'Loading sheet preview…' if self.uid else 'Choose a sheet.',12,12,'#DFEAF1')
            return
        x,y,w,h=self.rect_px(sheet)
        box(self.surface,x,y,w,h,'#FFFFFF','#A0B0BB')
        bitmap=data.get('_bitmap')
        if bitmap is not None:
            x,y,w,h=self.rect_px(bounds(data.get('image_bounds')) or sheet)
            img=Image()
            img.Source=bitmap
            img.Width,img.Height=w,h
            img.Stretch=Stretch.Fill
            img.IsHitTestVisible=False
            Canvas.SetLeft(img,x)
            Canvas.SetTop(img,y)
            self.surface.Children.Add(img)
        chosen=self.selected()
        rows=[r for r in data['items'] if r['_bounds']]
        for row in sorted(rows,key=lambda r:r['uid'] in chosen):
            selected=row['uid'] in chosen
            fill='#50219CD0' if selected else '#081687B5'
            stroke='#00648B' if selected else '#806E91A5'
            self.outline(self.surface,row['_bounds'],fill,stroke,2. if selected else 1.)
        if bitmap is None:
            hint=TextBlock()
            hint.Text='Sheet outline and item locations'
            hint.Foreground=brush('#DEEFFB')
            hint.Background=brush('#E609243A')
            hint.IsHitTestVisible=False
            Canvas.SetLeft(hint,7.)
            Canvas.SetTop(hint,4.)
            self.surface.Children.Add(hint)

    def zoom(self,sender,event):
        if self.scale is None or self.panel.gesture:
            return
        point=event.GetPosition(self.surface)
        before=self.world(point)
        self.fit_mode = None
        self.scale=max(.01,min(200000.,self.scale * (1.22 if event.Delta>0 else (1./1.22))))
        after=self.world(point)
        self.cx+=before[0]-after[0]
        self.cy+=before[1]-after[1]
        self.draw()
        event.Handled=True



    def hit(self, point):
        hits=[]
        for row in self.snapshot().get('items',[]):
            if row['_bounds']:
                x,y,w,h=self.rect_px(row['_bounds'])
                if x-3.<=point.X<=x+w+3. and y-3.<=point.Y<=y+h+3.:
                    hits.append((w*h,row['uid']))
        return min(hits)[1] if hits else None

    def pointer_down(self, sender,event):
        if not self.scale or self.panel.gesture:
            return
        self.surface.Focus()
        point=event.GetPosition(self.surface)
        if event.ChangedButton in (MouseButton.Middle,MouseButton.Right):
            self.panel.begin(self,{'mode':'pan','point':point,'cx':self.cx,'cy':self.cy})
        elif event.ChangedButton==MouseButton.Left:
            if self.panel.pending:return
            uid=self.hit(point)
            extend=bool(Keyboard.Modifiers & (ModifierKeys.Control | ModifierKeys.Shift))
            chosen=set(self.selected())
            if not uid:
                if not extend:self.panel.select(self.uid,[])
                return
            if event.ClickCount == 2 and not extend:
                if uid not in chosen:
                    self.panel.select(self.uid, [uid])
                self.edit_native()
                event.Handled = True
                return
            if extend and uid in chosen:
                chosen.remove(uid)
                self.panel.select(self.uid,chosen)
                event.Handled=True
                return
            if extend:chosen.add(uid)
            elif uid not in chosen:chosen={uid}
            self.panel.select(self.uid,chosen)
            if not self.panel.pending:
                self.panel.begin(self,{'mode':'move','point':point,'world':self.world(point),
                                       'uids':sorted(chosen),'moved':False})
        else:
            return
        event.Handled=True


class Panel(object):
    def __init__(self,bundle,sheets,source_uid,target_uid,request,on_closed):
        self.request,self.on_closed=request,on_closed
        self.shown=False
        self.closed=False
        self.pending=None
        self.gesture=None
        self.selections={}
        self.snapshots={}
        self.requested=set()
        self.panes=[]
        self.bundle = bundle
        self.window = read_window(bundle, 'SheetDetails.xaml')
        from pyrevit.coreutils import applocales, yaml
        locale = applocales.get_current_applocale()
        self.language = locale.locale_code if locale else 'en_us'
        tips = yaml.load_as_dict(os.path.join(bundle, 'bundle.yaml'))['tooltip']
        self.help_text = tips.get(self.language, tips['en_us']).strip()
        self.window.FindName('credit').Text = self.help_text.splitlines()[-1]
        self.window.FindName('help').Click += self.show_help
        self.window.FindName('githubHeader').Click += self.open_support
        humor = self.window.FindName('humorEnabled')
        humor.IsChecked = AppDomain.CurrentDomain.GetData(HUMOR_PREFERENCE) != False
        humor.Click += self.humor_toggled
        self.joke_index = 0
        self.window.FindName('joke').Text = SHEET_JOKES[0]
        self.window.FindName('nextJoke').Click += self.next_joke
        self.window.Width=min(self.window.Width,SystemParameters.WorkArea.Width)
        self.window.Height=min(self.window.Height,SystemParameters.WorkArea.Height)
        self.source=Pane(self,'source')
        self.target=Pane(self,'target')
        self.panes=[self.target,self.source]
        self.window.FindName('move').Click+=self.move_click
        self.window.FindName('swap').Click+=self.swap_click
        self.window.FindName('refresh').Click+=self.refresh_click
        self.window.PreviewMouseMove+=self.pointer_move
        self.window.PreviewMouseUp+=self.pointer_up
        self.window.PreviewKeyDown+=self.key_down
        self.window.Deactivated+=self.deactivated
        self.window.Closed+=self.closed_event
        self.set_sheets(sheets,source_uid,target_uid)
        self.status('Choose sheet items in the preview or list.')

    def show_help(self, sender, event):
        self.cancel_gesture()
        dialog = read_window(self.bundle, 'MoveViewsHelp.xaml')
        dialog.Owner = self.window
        dialog.Resources.MergedDictionaries.Add(self.window.Resources)
        heading, body = self.help_text.split('\n', 1)
        dialog.FindName('heading').Text = heading.strip()
        dialog.FindName('instructions').Text = body.strip()
        if self.language in ('ar', 'fa'):
            dialog.FlowDirection = FlowDirection.RightToLeft
        for name in ('github', 'linkedin'):
            dialog.FindName(name).Click += self.open_support
        dialog.ShowDialog()

    def open_support(self, sender, event):
        from pyrevit import script
        url = unicode(sender.Tag) if sender.Name == 'linkedin' else 'https://github.com/ndev16/NdevTools'
        script.open_url(url)

    def humor_toggled(self, sender, event):
        AppDomain.CurrentDomain.SetData(HUMOR_PREFERENCE, bool(sender.IsChecked))

    def next_joke(self, sender, event):
        self.joke_index = (self.joke_index + 1) % len(SHEET_JOKES)
        self.window.FindName('joke').Text = SHEET_JOKES[self.joke_index]

    def show(self):
        if self.closed:
            return
        first=not self.shown
        self.shown=True
        self.window.Show()
        self.window.UpdateLayout()
        if first:
            for uid in self.visible_sheet_ids():self.ask_preview(uid)

    def close(self):
        if not self.closed:self.window.Close()

    def closed_event(self,sender,event):
        self.cancel_gesture()
        self.closed=True
        self.shown=False
        self.snapshots.clear()
        self.requested.clear()
        if self.on_closed:self.on_closed()

    def deactivated(self,sender,event):
        self.cancel_gesture()

    def visible_sheet_ids(self):
        result=[]
        for pane in self.panes:
            if pane.uid and pane.uid not in result:result.append(pane.uid)
        return result

    def set_sheets(self,sheets,source_uid=None,target_uid=None):
        sheets=list(sheets)
        valid=[r['uid'] for r in sheets]
        source_uid=source_uid or self.source.uid
        if source_uid not in valid:source_uid=valid[0] if valid else None
        target_uid=target_uid or self.target.uid
        if target_uid not in valid:
            target_uid=next((uid for uid in valid if uid!=source_uid),source_uid)
        self.source.options(sheets,source_uid)
        self.target.options(sheets,target_uid)
        for uid in list(self.snapshots):
            if uid not in valid:
                self.snapshots.pop(uid,None)
                self.selections.pop(uid,None)
        if self.shown:
            for uid in self.visible_sheet_ids():self.ask_preview(uid)

    def follow_sheet(self, side, uid):
        """Update one selector from Revit without echoing another navigation request."""
        pane = self.source if side == 'source' else self.target
        option = next((item for item in pane.sheets.Items if item.Tag == uid), None)
        if option is None:
            return
        pane.syncing = True
        try:
            pane.sheets.SelectedItem = option
        finally:
            pane.syncing = False
        pane.change_sheet(uid)
        self.ask_preview(uid)

    def ask_preview(self,uid):
        if self.closed or not uid or uid in self.requested:return
        self.requested.add(uid)
        try:
            if self.request('preview',{'sheet':uid}) is False:
                self.requested.discard(uid)
        except Exception as error:
            self.requested.discard(uid)
            self.status(text_type(error))

    def status(self,message):
        if not self.closed:self.window.FindName('notice').Text=text_type(message)

    def refresh_click(self,sender,event):
        if self.pending:return
        self.requested.clear()
        try:self.request('refresh',{})
        except Exception as error:self.status(text_type(error))

    def update_snapshot(self,snap):
        if self.closed or not snap:return
        data=dict(snap)
        uid=data['uid']
        self.requested.discard(uid)
        rows=[]
        for row in data.get('items',[]):
            if eligible(row):
                item=dict(row)
                item['_bounds']=bounds(item.get('rect'))
                rows.append(item)
        data['items']=rows
        data['_bitmap']=None
        path=data.get('image')
        if uid in self.visible_sheet_ids() and path and os.path.isfile(path):
            stream=None
            try:
                stream=MemoryStream(File.ReadAllBytes(path))
                image=BitmapImage()
                image.BeginInit()
                image.CacheOption=BitmapCacheOption.OnLoad
                image.StreamSource=stream
                image.EndInit()
                image.Freeze()
                data['_bitmap']=image
            except Exception:
                self.status('The sheet image could not be displayed. The item locations are available.')
            finally:
                if stream is not None:stream.Dispose()
        self.snapshots[uid]=data
        self.selections.setdefault(uid,set()).intersection_update(r['uid'] for r in rows)
        for pane in self.panes:
            if pane.uid==uid:pane.populate()

    def select(self,uid,chosen):
        if not uid:return
        self.selections[uid]=set(chosen)
        for pane in self.panes:
            if pane.uid==uid:
                pane.paint_list()
                pane.draw()
        self.update_actions()

    def update_actions(self):
        if not self.panes:return
        ready=not self.pending
        source,target=self.source,self.target
        self.window.FindName('swap').IsEnabled = bool(ready and source.uid and target.uid and source.uid != target.uid)
        self.window.FindName('move').IsEnabled=bool(ready and source.selected() and target.uid
                                                     and source.uid!=target.uid)
        self.window.FindName('refresh').IsEnabled=ready
        for pane in self.panes:
            pane.sheets.IsEnabled=ready
            pane.editNative.IsEnabled=bool(ready and pane.uid)
            pane.views.IsEnabled=bool(ready and pane.list_rows)
            if not pane.list_rows:
                pane.views.IsChecked=False
            pane.selectAll.IsEnabled=bool(ready and pane.list_rows)
            pane.details.IsEnabled=ready
            pane.fit.IsEnabled=bool(pane.snapshot())
            pane.showAll.IsEnabled=bool(pane.snapshot())

    def move_click(self,sender,event):
        self.submit(self.source.uid,self.target.uid,self.source.selected(),0.,0.,'move')

    def swap_click(self, sender, event):
        source, target = self.source, self.target
        if self.closed or self.pending or not source.uid or not target.uid or source.uid == target.uid:
            return
        # Capture both sheets before changing either pane. Zoom, pan, bitmaps
        # and selections belong to the sheet and follow it to the other side.
        updates = []
        for pane, other in ((source, target), (target, source)):
            option = next((item for item in pane.sheets.Items if item.Tag == other.uid), None)
            if option is None:
                return
            updates.append((pane, option, other.scale, other.fit_mode, other.cx, other.cy, other.views.IsChecked))
        try:
            if self.request('swap', {'source': target.uid, 'target': source.uid}) is False:
                return
        except Exception as error:
            self.status(text_type(error))
            return
        self.cancel_gesture()
        for pane, option, scale, fit_mode, cx, cy, expanded in updates:
            pane.syncing = True
            try:
                pane.sheets.SelectedItem = option
            finally:
                pane.syncing = False
            pane.uid = option.Tag
            pane.scale, pane.fit_mode, pane.cx, pane.cy = scale, fit_mode, cx, cy
            pane.views.IsChecked = expanded
        for pane in (source, target):
            pane.populate()
        self.status('Source and target swapped.')

    def submit(self,source,target,uids,dx,dy,mode):
        if self.closed or self.pending or not source or not target or not uids:return
        if source==target and math.hypot(dx,dy)<1.e-9:return
        payload={'source':source,'target':target,'uids':sorted(uids),'dx':float(dx),'dy':float(dy),'mode':mode}
        self.pending=payload
        self.update_actions()
        self.status('Moving %d selected item(s)…' % len(uids))
        try:
            if self.request('move',payload) is False:
                self.move_result(False,'A sheet operation is already pending. Try the move again.',{})
        except Exception as error:
            self.move_result(False,text_type(error),{})

    def move_result(self,success,message,mapping=None):
        if self.closed:return
        sent=self.pending
        self.pending=None
        if success and sent:
            self.selections.setdefault(sent['source'],set()).difference_update(sent['uids'])
            ids=(mapping or {}).values()
            self.selections[sent['target']]=set(ids or sent['uids'])
            for pane in self.panes:
                if pane.uid in (sent['source'],sent['target']):
                    pane.paint_list()
                    pane.draw()
            for uid in set((sent['source'],sent['target'])):
                self.requested.discard(uid)
                self.ask_preview(uid)
        self.update_actions()
        self.status(message)

    def begin(self,pane,gesture):
        if not Mouse.Capture(pane.surface):return
        gesture['pane']=pane
        self.gesture=gesture
        if gesture['mode']=='pan':pane.surface.Cursor=Cursors.ScrollAll

    def cancel_gesture(self):
        old=self.gesture
        self.gesture=None
        if old:
            pane=old['pane']
            pane.surface.Cursor=None
            if Mouse.Captured==pane.surface:Mouse.Capture(None)
        for pane in self.panes:pane.ghost.Children.Clear()

    def key_down(self,sender,event):
        if event.Key == Key.Escape and self.gesture:
            self.cancel_gesture()
            event.Handled = True

    def drop_at(self,event):
        start=self.gesture
        for pane in self.panes:
            p=event.GetPosition(pane.surface)
            if (pane.uid and pane.scale and 0<=p.X<=pane.surface.ActualWidth
                    and 0<=p.Y<=pane.surface.ActualHeight):
                wx,wy=pane.world(p)
                return pane,wx-start['world'][0],wy-start['world'][1]
        return None

    def pointer_move(self,sender,event):
        start=self.gesture
        if not start:return
        pane=start['pane']
        if Mouse.Captured!=pane.surface:
            self.cancel_gesture()
            return
        p=event.GetPosition(pane.surface)
        dx,dy=p.X-start['point'].X,p.Y-start['point'].Y
        if start['mode']=='pan':
            pane.fit_mode = None
            pane.cx=start['cx']-dx/pane.scale
            pane.cy=start['cy']+dy/pane.scale
            pane.draw()
        else:
            if not start['moved']:
                if abs(dx)<SystemParameters.MinimumHorizontalDragDistance and abs(dy)<SystemParameters.MinimumVerticalDragDistance:return
                start['moved']=True
                pane.surface.Cursor=Cursors.SizeAll
            for each in self.panes:each.ghost.Children.Clear()
            target=self.drop_at(event)
            if target:
                dest,wx,wy=target
                chosen=set(start['uids'])
                for row in pane.snapshot()['items']:
                    if row['uid'] in chosen and row['_bounds']:
                        dest.outline(dest.ghost,row['_bounds'],'#6067D0DB','#005C75',2.,True,wx,wy)
        event.Handled=True

    def pointer_up(self,sender,event):
        start=self.gesture
        if not start:return
        if start['mode']=='pan' and event.ChangedButton==MouseButton.Left:return
        if start['mode']=='move' and event.ChangedButton!=MouseButton.Left:return
        dest=self.drop_at(event) if start['mode']=='move' and start['moved'] else None
        self.cancel_gesture()
        if dest:
            pane,dx,dy=dest
            self.submit(start['pane'].uid,pane.uid,start['uids'],dx,dy,'drag')
        event.Handled=True
