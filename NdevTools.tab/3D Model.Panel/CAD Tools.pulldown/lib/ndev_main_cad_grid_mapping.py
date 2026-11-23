# -*- coding: utf-8 -*-
"""Review and place both directions of straight CAD grids in one operation."""
import math
import os
from pyrevit import DB, UI, forms
from ndev_main_cad_events import CadEventHandler, api_callback
from System import String
from System.Windows import Thickness, GridLength, GridUnitType, TextWrapping
from System.Windows.Controls import CheckBox, Grid, ColumnDefinition, TextBlock, TextBox
from ndev_main_cad_buttons import CadTransaction, eid, name, point, read_cad, source_key, source_lines, source_schema, xyz
from ndev_main_grid_text import fill_names, match_label, read_labels
from ndev_main_cad_math import line_key
from ndev_main_cad_units import level_label
from ndev_main_cad_wall_plan import grid_layer
from ndev_main_cad_mapping import GITHUB_URL, logo_source, open_link

OPEN_WINDOWS=[]
TOL=1.0/304.8


def same_axis(first,second):
    a,b=first
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    return length>TOL and all(abs((p[0]-a[0])*(b[1]-a[1])-(p[1]-a[1])*(b[0]-a[0]))<=TOL*length for p in second)


def axes(lines):
    result=[]
    for a,b in sorted(lines,key=lambda pair:line_key(*pair)):
        a,b=(a[0],a[1],0.),(b[0],b[1],0.)
        length=math.hypot(b[0]-a[0],b[1]-a[1])
        if length<=TOL:
            continue
        for i,axis in enumerate(result):
            if same_axis(axis,(a,b)) and same_axis((a,b),axis):
                index=0 if abs(b[0]-a[0])>abs(b[1]-a[1]) else 1
                ends=sorted(axis+(a,b),key=lambda p:p[index])
                result[i]=(ends[0],ends[-1])
                break
        else:
            result.append((a,b))
    return result


def grid_row(panel, cells):
    row=Grid()
    row.Margin=Thickness(0,2,0,2)
    for i,(cell,width) in enumerate(zip(cells,(1.,1.,1.3))):
        col=ColumnDefinition()
        col.Width=GridLength(width,GridUnitType.Star)
        row.ColumnDefinitions.Add(col)
        if not isinstance(cell,TextBox):
            text=TextBlock()
            text.Text=cell
            text.TextWrapping=TextWrapping.Wrap
            cell=text
        Grid.SetColumn(cell,i)
        row.Children.Add(cell)
    panel.Children.Add(row)


class GridMapping(forms.WPFWindow):
    def __init__(self,doc):
        self.doc=doc
        self._closed=False
        self._ready=False
        self._api_active=True
        self.source_paths={}
        self.labels={}
        self.text_cache={}
        self.layers_saved={}
        self.fields=[]
        self.active=None
        self.ready=False
        forms.WPFWindow.__init__(self,os.path.join(os.path.dirname(__file__),'CadGridMapping.xaml'))
        self.logo.Source=logo_source()
        self.cads=sorted(DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance),
                         key=lambda c:(name(doc.GetElement(c.GetTypeId())),eid(c.Id)))
        self.drawing.ItemsSource=['{} [{}]'.format(name(doc.GetElement(c.GetTypeId())),eid(c.Id)) for c in self.cads]
        self._event_handler=CadEventHandler(self)
        self._external_event=UI.ExternalEvent.Create(self._event_handler)
        self.Closed+=self.window_closed
        self.refresh_existing()
        self._ready=True
        if self.cads:
            self.drawing.SelectedIndex=0
        else:
            self.create_button.IsEnabled=False
            self.status.Text='Link or import a CAD drawing first.'
        self._api_active=False

    def window_closed(self,sender,args):
        self._closed=True
        self._event_handler.pending=[]
        self._external_event.Dispose()
        if self in OPEN_WINDOWS:
            OPEN_WINDOWS.remove(self)

    def refresh_existing(self):
        self.existing={}
        self.occupied=set()
        schema=source_schema()
        self.tracked={}
        for grid in DB.FilteredElementCollector(self.doc).OfClass(DB.Grid):
            self.occupied.add(grid.Name.lower())
            if isinstance(grid.Curve,DB.Line):
                curve=grid.Curve
                self.existing[grid.Name]=(point(curve.GetEndPoint(0)),point(curve.GetEndPoint(1)))
            entity=grid.GetEntity(schema)
            if entity.IsValid():
                self.tracked[entity.Get[String](schema.GetField('SourceKey'))]=grid.Name
    def remember(self):
        if self.active is not None and self.active.IsValidObject:
            for axis,field,suggestion in self.fields:
                key=(self.active.UniqueId,line_key(*axis))
                if field.Text!=suggestion:
                    self.labels[key]=field.Text
                else:
                    self.labels.pop(key,None)

    def read_source(self,path):
        self.source_paths[self.active.UniqueId]=path
        try:
            transform=self.active.GetTransform()
            rows=[]
            for layer,x,y,h,value in read_labels(path):
                p=transform.OfPoint(DB.XYZ(x,y,0))
                rows.append((layer,p.X,p.Y,h*transform.Scale,value))
            note='Read {} CAD text labels.'.format(len(rows))
        except Exception as error:
            rows=[]
            note='Showing suggested names for unreadable grids. {}'.format(error)
        self.text_cache[self.active.UniqueId]=(rows,note)

    @api_callback
    def browse_click(self,sender,args):
        if self.active is None:
            return
        path=forms.pick_file(file_ext='dwg',title='Select the source DWG for this drawing')
        if path:
            self.remember()
            self.read_source(path)
            self.rebuild()

    def source_path(self):
        try:
            ref=DB.ExternalFileUtils.GetExternalFileReference(self.doc,self.active.GetTypeId())
            path=DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(ref.GetAbsolutePath())
            if os.path.isfile(path):
                return path
        except Exception:
            pass
        return None

    @api_callback
    def drawing_changed(self,sender,args):
        if not self._ready or self.drawing.SelectedIndex<0:
            return
        self.remember()
        self.fields=[]
        self.active=self.cads[self.drawing.SelectedIndex]
        self.layer_rows.Children.Clear()
        self.layer_boxes=[]
        try:
            self.geometry=read_cad(self.doc,self.active)
            if self.active.UniqueId not in self.text_cache:
                path=self.source_path()
                if path:
                    self.read_source(path)
                else:
                    self.text_cache[self.active.UniqueId]=([], 'Select Source DWG to read bubble names. Showing suggested names for unreadable grids.')
            previous=self.layers_saved.get(self.active.UniqueId)
            for layer in sorted(self.geometry):
                box=CheckBox()
                box.Content=layer
                box.IsChecked=layer in previous if previous is not None else grid_layer(layer) and 'IDEN' not in layer.upper()
                box.Click+=self.layer_changed
                self.layer_rows.Children.Add(box)
                self.layer_boxes.append((layer,box))
            self.rebuild()
        except Exception as error:
            self.horizontal_rows.Children.Clear()
            self.vertical_rows.Children.Clear()
            self.create_button.IsEnabled=False
            self.status.Text=str(error)

    @api_callback
    def layer_changed(self,sender,args):
        self.remember()
        self.rebuild()

    def rebuild(self):
        layers=[layer for layer,box in self.layer_boxes if box.IsChecked]
        self.layers_saved[self.active.UniqueId]=layers
        lines=source_lines([obj for layer in layers for obj in self.geometry[layer]])
        self.fields=[]
        self.horizontal_rows.Children.Clear()
        self.vertical_rows.Children.Clear()
        existing_count=0
        candidates=axes(lines)
        self.displayed_axes=set(line_key(*a) for a in candidates)
        texts,note=self.text_cache[self.active.UniqueId]
        cad_names={line_key(*axis):match_label(axis,texts,layers) for axis in candidates}
        reserved=set(self.occupied)
        reserved.update(label.lower() for label in cad_names.values() if label)
        for vertical,panel in ((False,self.horizontal_rows),(True,self.vertical_rows)):
            index=0 if vertical else 1
            series=[axis for axis in candidates if (abs(axis[1][1]-axis[0][1])>=abs(axis[1][0]-axis[0][0]))==vertical]
            series.sort(key=lambda axis:((axis[0][index]+axis[1][index])/2.,line_key(*axis)))
            labels=[cad_names[line_key(*axis)] for axis in series]
            proposals=fill_names(labels,vertical,reserved)
            rows=list(zip(series,labels,proposals))
            intervals={}
            start=0
            while start<len(rows):
                if labels[start]:
                    start+=1
                    continue
                end=start+1
                while end<len(rows) and not labels[end]:
                    end+=1
                left=labels[start-1] if start else None
                right=labels[end] if end<len(rows) else None
                caption=('Between {} and {}'.format(left,right) if left and right else
                         'After {}'.format(left) if left else 'Before {}'.format(right) if right else
                         'No readable CAD labels in this direction')
                intervals[line_key(*series[start])]=caption
                start=end
            for readable,title in ((True,'Readable grids'),(False,'Unreadable grids')):
                group=[row for row in rows if bool(row[1])==readable]
                if not group:
                    continue
                heading=TextBlock()
                heading.Text='{} ({})'.format(title,len(group))
                heading.Margin=Thickness(0,8,0,4)
                heading.Foreground=self.FindResource('Cyan')
                panel.Children.Add(heading)
                if readable:
                    grid_row(panel,('Position','Actual CAD name','Proposed Revit name'))
                for axis,label,suggestion in group:
                    key=line_key(*axis)
                    if key in intervals:
                        interval=TextBlock()
                        interval.Text=intervals[key]
                        interval.Margin=Thickness(0,6,0,2)
                        panel.Children.Add(interval)
                        grid_row(panel,('Position','Actual CAD name','Proposed Revit name'))
                    existing=self.tracked.get(source_key('Grids',self.active,key)) or next((n for n,line in self.existing.items() if same_axis(axis,line) and same_axis(line,axis)),None)
                    position=('X ' if vertical else 'Y ')+level_label(152.4*(axis[0][index]+axis[1][index]),True)
                    field=TextBox()
                    if existing is not None:
                        field.Text=existing
                        field.IsReadOnly=True
                        field.ToolTip='Existing Revit grid'
                        existing_count+=1
                    else:
                        field.Text=self.labels.get((self.active.UniqueId,key),suggestion)
                        field.ToolTip='Edit the name to create in Revit'
                        self.fields.append((axis,field,suggestion))
                    grid_row(panel,(position,label or 'Unreadable',field))
        self.create_button.IsEnabled=bool(self.fields)
        self.status.Text='{} new grids | {} already in Revit. {}'.format(len(self.fields),existing_count,note) if layers else 'Select the layer containing the grid lines.'

    @api_callback
    def create_click(self,sender,args):
        try:
            if not self.fields:
                return
            if self._closed:
                return
            if not self.active.IsValidObject:
                raise ValueError('This CAD drawing was removed. Reopen mapping to choose a drawing.')
            layers=self.layers_saved[self.active.UniqueId]
            before=self.displayed_axes
            fresh=read_cad(self.doc,self.active)
            after=set(line_key(*a) for a in axes(source_lines([o for l in layers for o in fresh.get(l,[])])))
            if before!=after:
                self.remember()
                path=self.source_paths.get(self.active.UniqueId)
                if path:
                    self.read_source(path)
                self.drawing_changed(None,None)
                self.status.Text='The CAD grid lines changed. Review the refreshed mapping before creating grids.'
                return
            self.refresh_existing()
            self.remember()
            self.geometry=fresh
            self.rebuild()
            if not self.fields:
                self.status.Text='All mapped grids already exist in Revit.'
                return
            entries=[(axis,field.Text.strip()) for axis,field,s in self.fields]
            used=set(self.occupied)
            for (axis,label),(_,field,_) in zip(entries,self.fields):
                if not label or label.lower() in used:
                    field.Focus()
                    field.SelectAll()
                    raise ValueError('Enter a unique grid name for each line. "{}" is empty, repeated, or already used.'.format(label))
                used.add(label.lower())
            if len(entries)>2000:
                raise ValueError('Choose layers with at most 2000 new grid lines.')
            schema=source_schema()
            with CadTransaction(self.doc,'CAD to grids'):
                created=[]
                for axis,label in entries:
                    a,b=axis
                    grid=DB.Grid.Create(self.doc,DB.Line.CreateBound(xyz(a,0),xyz(b,0)))
                    grid.Name=label
                    entity=DB.ExtensibleStorage.Entity(schema)
                    entity.Set[String](schema.GetField('SourceKey'),source_key('Grids',self.active,line_key(*axis)))
                    grid.SetEntity(entity)
                    created.append((grid,axis,label))
                self.doc.Regenerate()
                for grid,axis,label in created:
                    actual=tuple(point(grid.Curve.GetEndPoint(i)) for i in (0,1))
                    def end_error(order):
                        return max(math.hypot(a[0]-b[0],a[1]-b[1]) for a,b in zip(axis,order))
                    if grid.Name!=label or min(end_error(actual),end_error(actual[::-1]))>TOL or not grid.GetEntity(schema).IsValid():
                        raise ValueError('Revit did not retain the mapped grid {}.'.format(label))
            self.result_count=len(created)
            self.Close()
        except Exception as error:
            self.status.Text=str(error)

    def cancel_click(self,sender,args):
        self.Close()

    def help_click(self,sender,args):
        forms.alert('Select the grid layers. Linked DWGs supply bubble names automatically. For imports, use Source DWG. Actual CAD names are read-only. Each readable name is copied to Proposed Revit name. Unreadable grids show their neighboring CAD labels and an editable suggestion. Sloped lines keep their angle. Edit horizontal names from bottom to top and vertical names from left to right. Create grids places both lists together. Existing grids are shown read-only.',title='CAD to Grids | Help')

    def github_click(self,sender,args):
        open_link(GITHUB_URL)

def show(doc):
    for window in OPEN_WINDOWS:
        if window.doc.IsValidObject and window.doc.Equals(doc):
            from System.Windows import WindowState
            window.WindowState=WindowState.Normal
            window.Activate()
            return window
    window=GridMapping(doc)
    OPEN_WINDOWS.append(window)
    window.Show()
    return window
