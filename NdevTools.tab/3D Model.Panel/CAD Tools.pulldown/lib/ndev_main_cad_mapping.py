# -*- coding: utf-8 -*-
"""Single-window independent CAD thickness mapping and placement."""
import io
import json
import math
import os
import datetime
from pyrevit import DB, UI, forms, revit, script
from ndev_main_cad_events import CadEventHandler, api_callback
from System.Windows import Clipboard, Thickness, Visibility, GridLength
from System.Windows.Input import Key
from System.Windows.Controls import CheckBox, ComboBox, ComboBoxItem, Grid, ColumnDefinition, TextBlock
from System.Windows.Threading import DispatcherTimer, DispatcherPriority
from System.Windows.Media.Imaging import BitmapImage
from System import Uri, TimeSpan, Action
from System.Diagnostics import Process, ProcessStartInfo
from ndev_main_cad_buttons import read_cad, source_lines, eid, name
from ndev_main_cad_mapping_math import thickness_inventory, below_cutoff, mapped_pairs, matching_wall_type
from ndev_main_cad_units import parse_mm, display_mm, level_label
from ndev_main_cad_math import line_key
from ndev_main_cad_wall_plan import wall_plan,add_perimeter_pairs,grid_layer,wall_type_width

GITHUB_URL='https://github.com/ndev16/NdevTools'
LINKEDIN_URL='https://www.linkedin.com/in/nataraj016/'
OPEN_WINDOWS=[]
JOKES=("Revit isn't frozen. It's just thinking about its life choices.",
       'Coffee first. Constraints later.',
       'Everything is perfectly aligned... in one view.',
       'Level 01, Level 1, L1... Three names, one floor.',
       'The linked model moved. Again. Nobody act surprised.')


def open_link(url):
    info=ProcessStartInfo(url)
    info.UseShellExecute=True
    Process.Start(info)


def logo_source():
    return BitmapImage(Uri(os.path.join(os.path.dirname(__file__),'assets','ndevtools-logo.png')))


class WallTraceReport(forms.WPFWindow):
    def __init__(self,owner,report):
        forms.WPFWindow.__init__(self,os.path.join(os.path.dirname(__file__),'CadTraceReport.xaml'))
        self.Owner=owner
        self.body.Text=report

    def copy_click(self,sender,args):
        try:
            Clipboard.SetText(self.body.Text)
            self.copy_status.Text='Copied'
        except Exception:
            self.body.Focus()
            self.body.SelectAll()
            self.copy_status.Text='Press Ctrl+C to copy'

    def close_click(self,sender,args):
        self.Close()


class MappingHelp(forms.WPFWindow):
    def __init__(self,kind,owner):
        forms.WPFWindow.__init__(self,os.path.join(os.path.dirname(__file__),'CadMappingHelp.xaml'))
        self.Owner=owner
        self.help_logo.Source=logo_source()
        self.help_heading.Text='CAD TO '+kind.upper()+' | HELP'
        constraints=('Walls: Same as bottom uses one level; the top offset sets the wall top. Clear it to choose another top level. Opening head is measured from the wall bottom, including its offset.'
                     if kind=='Walls' else 'Beams: choose the top/target level and its offset. These set the member placement line elevation.')
        self.workflow_text.Text=('1. Select the linked or imported CAD drawing. Choose Metric or Imperial.\n\n'
            '2. With Layers: check the member-face layers. Search layers filters the list; hidden checked layers remain selected. Without Layers: scan the whole drawing across layer boundaries.\n\n'
            '3. Thicknesses scan automatically when the drawing, layer choices, mode or scan limits change. Only overlapping straight parallel face pairs are supported. A detected gap is a candidate, not proof of a wall or beam.\n\n'
            '4. Open each Revit type dropdown and search inside its list. Map the measured thickness to a loaded type. None - do not trace skips the group.\n\n'
            '5. Exclude below skips thinner groups. Thicknesses equal to the cutoff stay included. Thickness labels show two decimals; calculations retain precision.\n\n'
            '6. '+constraints+' Imperial levels display feet and inches; thicknesses display inches. Inputs accept decimal inches, fractions or feet/inches.\n\n'
            '7. Save mapping stores choices locally. For walls, the thicker mapped Revit type wins overlapping parallel runs; thinner portions outside the overlap remain eligible. Equal-width alternatives are flagged for review. Trace report previews each run; Place opens a report with the resulting Revit IDs.\n\n'
            'Review the result in Revit. Curves, hatch/composite interpretation, automatic type creation and CAD-text inference are not included. The commands run independently through pyRevit.')
        if kind=='Walls':
            self.workflow_text.Text+=('\n\nFully paired short wall faces may trace below Min partial overlap. '
                'Choose Door openings and Window openings independently. Clear both to trace walls only. '
                'A local parallel line inside the wall marks a window (sill 3 ft above the wall base). '
                'X marks and aligned breaks with two jambs mark door openings (sill at the wall base). '
                'Only walls taller than 7 ft receive openings. Walls 7 ft or shorter stay solid and are reported. '
                'An unmarked gap up to 8 ft qualifies when both faces stop and resume on the same wall.')

    def github_click(self,sender,args):
        open_link(GITHUB_URL)

    def issue_click(self,sender,args):
        open_link(GITHUB_URL+'/issues/new')

    def linkedin_click(self,sender,args):
        open_link(LINKEDIN_URL)

    def close_click(self,sender,args):
        self.Close()


class MappingCancel(forms.WPFWindow):
    def __init__(self,owner):
        self.confirmed=False
        forms.WPFWindow.__init__(self,os.path.join(os.path.dirname(__file__),'CadMappingCancel.xaml'))
        self.Owner=owner

    def yes_click(self,sender,args):
        self.confirmed=True
        self.Close()

    def no_click(self,sender,args):
        self.Close()


def millimetres(text):
    value=float(text)
    if math.isnan(value) or math.isinf(value):
        raise ValueError('Enter a finite number in millimetres.')
    return value


class MappingWindow(forms.WPFWindow):
    def __init__(self, kind, doc):
        self._api_active=True
        self._closed=False
        self._busy_operation=None
        self._event_handler=CadEventHandler(self)
        self._external_event=UI.ExternalEvent.Create(self._event_handler)
        self._ready=False
        self.kind,self.doc=kind,doc
        self.rows=[]
        self.controls={}
        self.checks=[]
        self.geometry={}
        self._choices={}
        self._context=None
        self.saved=False
        self.report_path=None
        self._imperial=False
        self._joke_index=-1
        self._measure_cache={}
        self._formatting=False
        self.path=script.get_data_file('ndev_main_cad_mapping_'+kind.lower(),'json')
        self.previous={}
        try:
            if os.path.isfile(self.path):
                with io.open(self.path,'r',encoding='utf-8') as stream:
                    self.previous=json.load(stream)
        except (ValueError,IOError):
            self.previous={}
        forms.WPFWindow.__init__(self,os.path.join(os.path.dirname(__file__),'CadMapping.xaml'),handle_esc=False)
        self.trace_report_button.Visibility=Visibility.Visible if kind=='Walls' else Visibility.Collapsed
        self.PreviewKeyDown += self.mapping_key_down
        self.Closing += self.confirm_close
        self._scan_timer=DispatcherTimer()
        self._scan_timer.Interval=TimeSpan.FromMilliseconds(350)
        self._scan_timer.Tick += self.auto_scan
        self.brand_logo.Source=logo_source()
        self.Title='NdevTools | CAD to '+kind+' Mapping'
        self.heading.Text='CAD '+('WALL' if kind=='Walls' else 'BEAM')+' MAPPING'
        self.layer_heading.Text=('WALL' if kind=='Walls' else 'BEAM')+' LAYERS'
        self.exclude_below.Content='Exclude '+('wall thickness' if kind=='Walls' else 'beam width')+' below'
        if kind=='Beams':
            self.bottom_level_panel.Visibility=Visibility.Collapsed
            self.bottom_offset_panel.Visibility=Visibility.Collapsed
            self.same_level.Visibility=Visibility.Collapsed
            self.opening_choices.Visibility=Visibility.Collapsed
        self.cads=list(DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance))
        labels=[]
        for cad in self.cads:
            cad_type=doc.GetElement(cad.GetTypeId())
            labels.append('{} [{}]'.format(name(cad_type) if cad_type else name(cad),eid(cad.Id)))
        self.cad_choice.ItemsSource=labels
        self.cad_choice.SelectedIndex=next((i for i,c in enumerate(self.cads) if c.UniqueId==self.previous.get('cad_uid')),0 if self.cads else -1)
        self.levels=sorted(list(DB.FilteredElementCollector(doc).OfClass(DB.Level)),key=lambda l:l.ProjectElevation)
        self._level_z=[l.ProjectElevation for l in self.levels]
        level_labels=['{} | {}'.format(name(l),level_label(l.Elevation*304.8)) for l in self.levels]
        self.bottom_level.ItemsSource=level_labels
        self.top_level.ItemsSource=level_labels
        active=getattr(doc.ActiveView,'GenLevel',None)
        base_index=next((i for i,l in enumerate(self.levels) if active and l.Id==active.Id),-1)
        top_default=(base_index if kind=='Beams' else base_index+1) if base_index>=0 else -1
        if top_default>=len(self.levels):
            top_default=-1
        self.bottom_level.SelectedIndex=next((i for i,l in enumerate(self.levels) if l.UniqueId==self.previous.get('bottom_level_uid')),base_index)
        self.top_level.SelectedIndex=next((i for i,l in enumerate(self.levels) if l.UniqueId==self.previous.get('top_level_uid')),top_default)
        self.unit_choice.ItemsSource=['Metric (mm)','Imperial (in / ft-in)']
        self.unit_choice.SelectedIndex=0
        for field in ('minimum_width','maximum_width','minimum_overlap','cutoff_width','bottom_offset','top_offset'):
            if field in self.previous:
                getattr(self,field).Text=str(self.previous[field])
        if kind=='Walls':
            self.create_doors.IsChecked=bool(self.previous.get('create_doors',True))
            self.create_windows.IsChecked=bool(self.previous.get('create_windows',True))
            self.same_level.IsChecked=bool(self.previous.get('same_level',True))
            if self.same_level.IsChecked:
                bi=self.bottom_level.SelectedIndex
                ti=self.top_level.SelectedIndex
                if bi>=0 and 'same_level' not in self.previous:
                    # Keep the former top elevation when migrating an old saved mapping.
                    if self.previous.get('top_level_uid') not in [l.UniqueId for l in self.levels]:
                        ti=next((i for i,z in enumerate(self._level_z) if z>self._level_z[bi]+1.e-6),-1)
                    if ti>=0:
                        self.set_measurement('top_offset',self.measure('top_offset')+(self._level_z[ti]-self._level_z[bi])*304.8)
                self.top_level.SelectedIndex=bi
                self.top_level.IsEnabled=False
        self.exclude_below.IsChecked=bool(self.previous.get('exclude_below',False))
        self.with_layers.IsChecked=self.previous.get('mode','with_layers')=='with_layers'
        self.without_layers.IsChecked=not bool(self.with_layers.IsChecked)
        self.load_types()
        self._ready=True
        self.save_button.IsEnabled=False
        self.place_button.IsEnabled=False
        self.cutoff_width.IsEnabled=bool(self.exclude_below.IsChecked)
        self.load_cad()
        self.update_mode()
        # Start in Imperial as requested; saved measurements remain unit-neutral.
        self.unit_choice.SelectedIndex=1
        self.status.Text='Choose source layers or Without Layers; thicknesses scan automatically.'
        self._ui_path=script.get_data_file('ndev_main_cad_mapping_ui','json')
        try:
            with io.open(self._ui_path,'r',encoding='utf-8') as stream:
                self.humor_enabled.IsChecked=bool(json.load(stream).get('humor',True))
        except (IOError,ValueError):
            pass
        self._joke_timer=DispatcherTimer()
        self._joke_timer.Interval=TimeSpan.FromSeconds(60)
        self._joke_timer.Tick += self.next_joke_click
        self.Closed += self.window_closed
        self.update_humor()
        self.format_measurements()
        self._api_active=False

    def measure(self, control):
        text=getattr(self,control).Text
        cached=self._measure_cache.get(control)
        return cached[1] if cached and text==cached[0] else parse_mm(text,self._imperial)

    def bottom_level_changed(self,sender,args):
        if self._ready and self.kind=='Walls' and self.same_level.IsChecked:
            self.top_level.SelectedIndex=self.bottom_level.SelectedIndex

    def same_level_click(self,sender,args):
        if not self._ready: return
        bi,ti=self.bottom_level.SelectedIndex,self.top_level.SelectedIndex
        if self.same_level.IsChecked and bi>=0 and ti>=0 and bi!=ti:
            try:
                self.set_measurement('top_offset',self.measure('top_offset')+(self._level_z[ti]-self._level_z[bi])*304.8)
            except ValueError as error:
                self.same_level.IsChecked=False
                self.status.Text=str(error)
                return
        if self.same_level.IsChecked: self.top_level.SelectedIndex=bi
        self.top_level.IsEnabled=not bool(self.same_level.IsChecked)

    def set_measurement(self,field,value_mm):
        value=value_mm/(25.4 if self._imperial else 1)
        text='{:.2f}'.format(0.0 if abs(value)<0.005 else value)
        self._measure_cache[field]=(text,value_mm)
        getattr(self,field).Text=text

    def format_measurements(self):
        self._formatting=True
        try:
            for field in ('minimum_width','maximum_width','minimum_overlap','cutoff_width','bottom_offset','top_offset'):
                self.set_measurement(field,self.measure(field))
        finally:
            self._formatting=False

    def measurement_lost_focus(self,sender,args):
        if not self._ready:
            return
        try:
            self._formatting=True
            self.set_measurement(sender.Name,self.measure(sender.Name))
        except Exception as error:
            self.status.Text='Enter a valid measurement: '+str(error)
        finally:
            self._formatting=False

    @api_callback
    def units_changed(self,sender,args):
        if not self._ready:
            return
        new=self.unit_choice.SelectedIndex==1
        try:
            fields=('minimum_width','maximum_width','minimum_overlap','cutoff_width','bottom_offset','top_offset')
            values={f:self.measure(f) for f in fields}
            bottom_index=self.bottom_level.SelectedIndex
            top_index=self.top_level.SelectedIndex
            self.remember()
            self._ready=False
            self._imperial=new
            for f in fields:
                self.set_measurement(f,values[f])
            suffix='in' if new else 'mm'
            self.spacing_label.Text='Scan spacing ('+suffix+')'
            self.overlap_label.Text=('Min partial overlap (' if self.kind=='Walls' else 'Min overlap (')+suffix+')'
            if self.kind=='Walls':
                self.minimum_overlap.ToolTip='Short wall returns also qualify when the full shorter face has a parallel mate.'
            self.cutoff_unit.Text=suffix
            self.bottom_offset_label.Text='Bottom offset ('+suffix+')'
            self.top_offset_label.Text='Top offset ('+suffix+')'
            self.bottom_level.ItemsSource=['{} | {}'.format(name(l),level_label(l.Elevation*304.8,new)) for l in self.levels]
            self.top_level.ItemsSource=list(self.bottom_level.ItemsSource)
            self.bottom_level.SelectedIndex=bottom_index
            self.top_level.SelectedIndex=top_index
            self.load_types()
            self.render_rows()
        except Exception as error:
            self._ready=False
            self.status.Text='Correct measurement fields before switching units: '+str(error)
            self.unit_choice.SelectedIndex=1 if self._imperial else 0
            return
        finally:
            self._ready=True
        self.filter_changed(None,None)

    def load_types(self):
        if self.kind=='Walls':
            self.types=[t for t in DB.FilteredElementCollector(self.doc).OfClass(DB.WallType)
                        if t.Kind in (DB.WallKind.Basic,DB.WallKind.Curtain,DB.WallKind.Stacked)]
        else:
            self.types=list(DB.FilteredElementCollector(self.doc).OfCategory(DB.BuiltInCategory.OST_StructuralFraming).OfClass(DB.FamilySymbol))
        self.types.sort(key=lambda t:(t.FamilyName,name(t)))
        self.type_labels=['None - do not trace']
        for item in self.types:
            width=wall_type_width(item) if self.kind=='Walls' else 0
            suffix=' | {:.2f} {}'.format(width*304.8/(25.4 if self._imperial else 1),'in' if self._imperial else 'mm') if width else ''
            self.type_labels.append('{} : {}{}'.format(item.FamilyName,name(item),suffix))

    def cad(self):
        i=self.cad_choice.SelectedIndex
        return self.cads[i] if 0<=i<len(self.cads) else None

    def context(self):
        cad=self.cad()
        return json.dumps([cad.UniqueId if cad else None,bool(self.with_layers.IsChecked),self.selected_layers()])

    def remember(self):
        if self._context is None:
            return
        choices=self._choices.setdefault(self._context,{})
        for key,(panel,combo) in self.controls.items():
            if combo.SelectedIndex!=combo.Tag:
                item=self.selected_type(combo)
                choices[str(key)]=item.UniqueId if item is not None else None
                combo.Tag=combo.SelectedIndex

    def selected_type(self,combo):
        return combo.SelectedItem.Tag if combo.SelectedItem is not None else None

    def layer_search_changed(self,sender,args):
        if not self._ready:
            return
        query=self.layer_search.Text.strip().lower()
        for layer,check in self.checks:
            check.Visibility=Visibility.Visible if query in layer.lower() else Visibility.Collapsed

    def dropdown_opened(self,sender,args):
        search=sender.Template.FindName('PART_TypeSearch',sender)
        if search is not None:
            if search.Tag is None:
                search.Tag=sender
                search.TextChanged += self.dropdown_search_changed
            search.Text=''
            search.Focus()

    def dropdown_search_changed(self,sender,args):
        combo=sender.Tag
        query=sender.Text.strip().lower()
        for item in combo.Items:
            item.Visibility=(Visibility.Visible if item.Tag is None or query in str(item.Content).lower()
                             else Visibility.Collapsed)

    def invalidate(self,message='Source changed. Updating thicknesses automatically.',schedule=True):
        if not self._ready:
            return
        self.remember()
        self.rows=[]
        self.controls={}
        self.mapping_rows.Children.Clear()
        self._context=None
        self.status.Text=message
        self.save_button.IsEnabled=False
        self.place_button.IsEnabled=False
        self.scan_notes.Text=message
        self._scan_timer.Stop()
        if schedule:
            self.queue_scan()

    def show_activity(self,operation,paint=False):
        self._busy_operation=operation
        if operation=='place':
            self.activity_message.Text=('Wall Tracing is placing your walls...' if self.kind=='Walls'
                                        else 'Beam Tracing is placing your beams...')
            self.activity_hint.Text='Please wait. The placement results will appear when finished.'
        else:
            self.activity_message.Text=('NdevTools is scanning wall thickness...' if self.kind=='Walls'
                                        else 'NdevTools is scanning beam widths...')
            self.activity_hint.Text='Preparing thicknesses, candidates and Revit types.'
        self.activity_overlay.Visibility=Visibility.Visible
        if paint and self.IsVisible:
            # Paint before raising the Revit event, outside any model transaction.
            # Loaded runs after layout/render, before input; never pump all UI events
            # while scanning or placing, which could re-enter a model transaction.
            self.activity_overlay.UpdateLayout()
            self.Dispatcher.Invoke(Action(lambda:None),DispatcherPriority.Loaded)

    def api_request_started(self,callback_name):
        # A second click must not queue another placement while the first waits.
        if self._busy_operation=='place':
            return False
        if not self._ready:
            return True
        if callback_name=='place_click':
            self.show_activity('place',paint=True)
        elif callback_name in ('auto_scan','scan_click','layer_changed','cad_changed',
                               'mode_click','all_layers','no_layers','scan_setting_changed'):
            self.show_activity('scan',paint=True)
        return True

    def api_request_finished(self,cancelled=False):
        if self._closed:
            return
        if cancelled:
            self._scan_timer.Stop()
        if self._scan_timer.IsEnabled:
            # Keep the card visible through the auto-scan debounce and row rendering.
            self.show_activity('scan')
        else:
            self._busy_operation=None
            self.activity_overlay.Visibility=Visibility.Collapsed

    def queue_scan(self):
        self._scan_timer.Stop()
        if self.cad() is not None and self.selected_layers():
            self.show_activity('scan')
            self.status.Text=self.activity_message.Text
            self._scan_timer.Start()
        else:
            self.status.Text='Choose source layers or Without Layers to detect thicknesses automatically.'

    @api_callback
    def auto_scan(self,sender,args):
        self._scan_timer.Stop()
        if self._ready and self.cad() is not None and self.selected_layers():
            self.scan_click(None,None)

    def load_cad(self):
        self.invalidate('Choose source layers to scan thicknesses automatically.')
        self.layer_checks.Children.Clear()
        self.checks=[]
        cad=self.cad()
        self.geometry=read_cad(self.doc,cad) if cad else {}
        saved_layers=self.previous.get('layers',[]) if cad and cad.UniqueId==self.previous.get('cad_uid') else []
        for layer in sorted(self.geometry):
            check=CheckBox()
            check.Content=layer
            check.IsChecked=layer in saved_layers
            check.Click += self.layer_changed
            self.layer_checks.Children.Add(check)
            self.checks.append((layer,check))
        self.layer_search_changed(None,None)
        self.queue_scan()

    def selected_layers(self):
        return sorted(self.geometry) if self.without_layers.IsChecked else [n for n,c in self.checks if c.IsChecked]

    def source_stamp(self,geometry):
        layers=sorted(geometry) if self.without_layers.IsChecked else list(self.selected_layers())
        if self.perimeter_active(layers):
            layers=sorted(geometry)
        return sorted((layer,line_key(a,b)) for layer in layers
                      for a,b in source_lines(geometry.get(layer,[])))

    def perimeter_active(self,layers):
        return (self.kind=='Walls' and self.with_layers.IsChecked
                and bool(layers))

    def update_mode(self):
        layered=bool(self.with_layers.IsChecked)
        self.layer_card.Visibility=Visibility.Visible if layered else Visibility.Collapsed
        self.layer_column.Width=GridLength(260 if layered else 0)
        self.mode_hint.Text=('Check the layers containing member faces.' if layered else
                             'Inspect all straight-line geometry; review non-member pairs carefully.')

    @api_callback
    def mode_click(self,sender,args):
        self.with_layers.IsChecked=sender==self.with_layers
        self.without_layers.IsChecked=sender==self.without_layers
        self.invalidate()
        self.update_mode()

    @api_callback
    def cad_changed(self,sender,args):
        if self._ready:
            try:
                self.load_cad()
            except Exception as error:
                self.status.Text=str(error)

    @api_callback
    def layer_changed(self,sender,args):
        self.invalidate()

    @api_callback
    def scan_setting_changed(self,sender,args):
        if not self._ready or self._formatting:
            return
        self.invalidate()

    @api_callback
    def all_layers(self,sender,args):
        for layer,check in self.checks:
            if check.Visibility==Visibility.Visible:
                check.IsChecked=True
        self.invalidate()

    @api_callback
    def no_layers(self,sender,args):
        for layer,check in self.checks:
            if check.Visibility==Visibility.Visible:
                check.IsChecked=False
        self.invalidate()

    @api_callback
    def scan_click(self,sender,args):
        try:
            self.remember()
            cad=self.cad()
            if cad is not None:
                self.geometry=read_cad(self.doc,cad)
            selected=self.selected_layers()
            if cad is None or not selected:
                raise ValueError('Choose a CAD drawing and at least one layer, or use Without Layers.')
            low,high=self.measure('minimum_width'),self.measure('maximum_width')
            overlap=self.measure('minimum_overlap')
            if low<=0 or high<low or overlap<=0:
                raise ValueError('Scan spacing and minimum overlap must be positive; maximum must be at least minimum.')
            self._source_stamp=self.source_stamp(self.geometry)
            lines=[]
            # With Layers pairs within each checked layer. Without Layers ignores
            # layer boundaries. Face indices are made globally unique below.
            batches=[]
            for layer in selected:
                if self.kind=='Walls' and grid_layer(layer):
                    continue
                source=[(a,b,layer) for a,b in source_lines(self.geometry.get(layer,[]))]
                if self.with_layers.IsChecked or self.kind=='Walls':
                    batches.append(source)
                else:
                    lines.extend(source)
            if self.without_layers.IsChecked and self.kind!='Walls':
                batches=[lines]
            merged={}
            offset=0
            self._scan_lines=[]
            self._scan_diagnostics={}
            known_widths=[wall_type_width(t)*304.8 for t in self.types if t.Kind==DB.WallKind.Basic] if self.kind=='Walls' else []
            for batch in batches:
                diagnostics={}
                self._scan_lines.extend(batch)
                for row in thickness_inventory(batch,low,high,overlap,diagnostics,min_shared_fraction=0 if self.kind=='Walls' else 0.6,
                                               short_wall_faces=self.kind=='Walls',supported_widths=known_widths):
                    target=merged.setdefault(row['key'],{'key':row['key'],'width_mm':row['width_mm'],'pairs':[],'layers':set()})
                    for pair in row['pairs']:
                        combined=dict(pair)
                        combined['faces']=tuple(i+offset for i in pair['faces'])
                        combined['midline_faces']=tuple(i+offset for i in pair['midline_faces'])
                        target['pairs'].append(combined)
                    target['layers'].update(row['layers'])
                self._scan_diagnostics.update((i+offset,counts) for i,counts in diagnostics.items())
                offset+=len(batch)
            if self.perimeter_active(selected):
                for layer in self.geometry:
                    if layer not in selected and not grid_layer(layer):
                        self._scan_lines.extend((a,b,layer) for a,b in source_lines(self.geometry[layer]))
                add_perimeter_pairs(merged,self._scan_lines,self._scan_diagnostics,low,high,overlap,selected,known_widths)
            if self.kind=='Walls' and self.without_layers.IsChecked:
                add_perimeter_pairs(merged,self._scan_lines,self._scan_diagnostics,low,high,overlap,selected,known_widths)
            self.rows=[merged[k] for k in sorted(merged)]
            self._context=self.context()
            if self._context not in self._choices and cad.UniqueId==self.previous.get('cad_uid') and self.previous.get('mode')==('with_layers' if self.with_layers.IsChecked else 'without_layers') and selected==self.previous.get('layers'):
                self._choices[self._context]=self.previous.get('mappings',{})
            self.render_rows()
            self.filter_changed(None,None)
            if not self.rows:
                self.status.Text='Scan complete. No thickness candidates found for the selected layers and settings.'
        except Exception as error:
            self.invalidate(str(error),schedule=False)

    def render_rows(self):
        self.mapping_rows.Children.Clear()
        self.controls={}
        previous=self._choices.get(self._context,{})
        specifications=[(t.UniqueId,wall_type_width(t)*304.8,self.type_labels[i+1]) for i,t in enumerate(self.types)
                        if t.Kind==DB.WallKind.Basic] if self.kind=='Walls' else []
        for row in self.rows:
            panel=Grid()
            panel.Margin=Thickness(0,0,0,8)
            for width in (130,100):
                column=ColumnDefinition()
                column.Width=GridLength(width)
                panel.ColumnDefinitions.Add(column)
            panel.ColumnDefinitions.Add(ColumnDefinition())
            for i,label in enumerate(('{:.2f} {}'.format(row['width_mm']/(25.4 if self._imperial else 1),'in' if self._imperial else 'mm'),str(len(row['pairs'])))):
                text=TextBlock()
                text.Text=label
                Grid.SetColumn(text,i)
                panel.Children.Add(text)
            combo=ComboBox()
            combo.Template=self.FindResource('SearchableTypeTemplate')
            uid=previous.get(str(row['key']))
            match_count=0
            options=list(zip(self.types,self.type_labels[1:]))
            uids=[t.UniqueId for t,label in options]
            automatic=(str(row['key']) not in previous or (uid is not None and uid not in uids))
            if self.kind=='Walls':
                best,match_count=matching_wall_type(row['width_mm'],specifications)
                if automatic:
                    uid=best
                options.sort(key=lambda option: abs(wall_type_width(option[0])*304.8-row['width_mm'])>0.100001)
                uids=[t.UniqueId for t,label in options]
            no_match=automatic and not match_count and self.kind=='Walls'
            # Keep an unmatched automatic result distinct from an explicit skip.
            if no_match:
                item=ComboBoxItem()
                item.Content='No matching width - choose a type'
                item.IsEnabled=False
                combo.Items.Add(item)
            for item_type,label in [(None,'None - do not trace')]+options:
                item=ComboBoxItem()
                item.Content=label
                item.Tag=item_type
                combo.Items.Add(item)
            combo.SelectedIndex=uids.index(uid)+1+int(no_match) if uid in uids else 0
            combo.Tag=combo.SelectedIndex
            combo.ToolTip='Source layers: '+', '.join(sorted(row['layers']))+'\nNone skips this thickness entirely.'
            if match_count and automatic:
                combo.ToolTip+='\nWidth match suggested automatically ({} matching types). Review the type before placement.'.format(match_count)
            combo.SelectionChanged += self.mapping_changed
            combo.DropDownOpened += self.dropdown_opened
            Grid.SetColumn(combo,2)
            panel.Children.Add(combo)
            self.mapping_rows.Children.Add(panel)
            self.controls[row['key']]=(panel,combo)

    @api_callback
    def mapping_changed(self,sender,args):
        if self._ready:
            self.remember()
            self.filter_changed(None,None)

    @api_callback
    def filter_changed(self,sender,args):
        if not self._ready:
            return
        try:
            self.cutoff_width.IsEnabled=bool(self.exclude_below.IsChecked)
            cutoff=self.measure('cutoff_width') if self.exclude_below.IsChecked else 0
            if cutoff<0:
                raise ValueError('The exclusion cutoff cannot be negative.')
            excluded=0
            choices={}
            for row in self.rows:
                panel,combo=self.controls[row['key']]
                hidden=below_cutoff(row['width_mm'],bool(self.exclude_below.IsChecked),cutoff)
                panel.Visibility=Visibility.Collapsed if hidden else Visibility.Visible
                excluded+=int(hidden)
                choices[row['key']]=self.selected_type(combo)
            if self.kind=='Walls':
                decisions=[]
                accepted=wall_plan(self.rows,choices,bool(self.exclude_below.IsChecked),cutoff,decisions,self.doc.Application.ShortCurveTolerance)
                self.scan_notes.Text='{} groups; {} excluded; {} eligible runs; {} stretches yielded to thicker walls; {} candidates have equal-width conflicts. See Trace report for locations.'.format(
                    len(self.rows),excluded,sum(len(p) for r,t,p,d in accepted),sum(s.startswith('thicker') for r,p,s in decisions),sum(d for r,t,p,d in accepted))
            else:
                accepted=mapped_pairs(self.rows,choices,bool(self.exclude_below.IsChecked),cutoff)
                self.scan_notes.Text='{} thickness groups; {} excluded; {} mapped candidates; {} ambiguous pairs withheld.'.format(len(self.rows),excluded,sum(len(p) for r,t,p,d in accepted),sum(d for r,t,p,d in accepted))
            self.save_button.IsEnabled=bool(self.rows)
            self.place_button.IsEnabled=any(p for r,t,p,d in accepted)
            if self.rows:
                self.status.Text='Review mappings and levels. Save stores choices; Place creates mapped candidates.'
        except Exception as error:
            self.save_button.IsEnabled=False
            self.place_button.IsEnabled=False
            self.status.Text=str(error)

    @api_callback
    def refresh_click(self,sender,args):
        self.remember()
        self.load_types()
        self.render_rows()
        self.filter_changed(None,None)

    @api_callback
    def save_click(self,sender,args):
        try:
            if self._context is None or self._context!=self.context():
                raise ValueError('Scan the current source settings before saving.')
            top_index=self.top_level.SelectedIndex
            bottom_index=self.bottom_level.SelectedIndex
            if top_index<0 or (self.kind=='Walls' and bottom_index<0):
                raise ValueError('Choose the required levels.')
            top_offset=self.measure('top_offset')
            bottom_offset=self.measure('bottom_offset') if self.kind=='Walls' else 0
            if self.kind=='Walls' and self._level_z[top_index]+top_offset/304.8<=self._level_z[bottom_index]+bottom_offset/304.8:
                raise ValueError('The top level plus offset must be above the bottom level plus offset.')
            self.filter_changed(None,None)
            if not self.save_button.IsEnabled:
                return
            self.remember()
            # Persist overrides only. Automatic rows resolve against current types on reopen.
            saved_choices=dict(self._choices[self._context])
            data={'schema':1,'kind':self.kind,'cad_uid':self.cad().UniqueId,
                  'mode':'with_layers' if self.with_layers.IsChecked else 'without_layers',
                  'layers':self.selected_layers(),'mappings':saved_choices,
                  'bottom_level_uid':self.levels[bottom_index].UniqueId if bottom_index>=0 else None,
                  'top_level_uid':self.levels[top_index].UniqueId,
                  'bottom_offset':bottom_offset,'top_offset':top_offset,
                  'exclude_below':bool(self.exclude_below.IsChecked),'imperial':self._imperial}
            if self.kind=='Walls':
                data['same_level']=bool(self.same_level.IsChecked)
                data['create_doors']=bool(self.create_doors.IsChecked)
                data['create_windows']=bool(self.create_windows.IsChecked)
            for field in ('minimum_width','maximum_width','minimum_overlap'):
                data[field]=self.measure(field)
            data['cutoff_width']=self.measure('cutoff_width') if self.exclude_below.IsChecked else self.previous.get('cutoff_width',100)
            with io.open(self.path,'w',encoding='utf-8') as stream:
                stream.write(unicode(json.dumps(data,indent=2,ensure_ascii=False)))
            self._choices[self._context]=saved_choices
            self.previous=data
            self.saved=True
            self.status.Text='Mapping saved. No model elements were created.'
        except Exception as error:
            self.status.Text=str(error)

    @api_callback
    def report_click(self,sender,args):
        if self._context!=self.context() or self._context is None:
            self.status.Text='Wait for the current scan to finish before opening its report.'
            return
        self.write_report('Scan preview')

    def write_report(self,phase,result=None,failed=None):
        if self.kind!='Walls':
            return
        try:
            from ndev_main_cad_trace_report import trace_report
            choices={}
            labels={}
            unmatched=[]
            for row in self.rows:
                key=row['key']
                combo=self.controls[key][1]
                sym=self.selected_type(combo)
                choices[key]=sym
                labels[key]=name(sym) if sym is not None else None
                if sym is None and not any(t.Kind==DB.WallKind.Basic and abs(wall_type_width(t)*304.8-row['width_mm'])<=0.100001 for t in self.types):
                    unmatched.append(key)
            threshold=self.measure('cutoff_width') if self.exclude_below.IsChecked else 0
            details='{} | {} | {} | {}\nLayers: {}\nSpacing {:.2f} to {:.2f} mm; minimum overlap {:.2f} mm; exclude below: {}\nBottom: {} + {} | Top: {} + {}'.format(
                phase,self.doc.Title,self.cad_choice.SelectedItem,'With Layers' if self.with_layers.IsChecked else 'Without Layers',
                ', '.join(self.selected_layers()),self.measure('minimum_width'),self.measure('maximum_width'),self.measure('minimum_overlap'),
                str(threshold)+' mm' if self.exclude_below.IsChecked else 'off',self.bottom_level.SelectedItem,self.bottom_offset.Text,
                self.top_level.SelectedItem,self.top_offset.Text)
            details+='\nDoor openings: {} | Window openings: {}'.format(
                'on' if self.create_doors.IsChecked else 'off','on' if self.create_windows.IsChecked else 'off')
            report=trace_report(self.rows,choices,self._scan_lines,self._scan_diagnostics,bool(self.exclude_below.IsChecked),
                threshold,details,(result or {}).get('outcomes'),unmatched,failed,labels,self.doc.Application.ShortCurveTolerance)
            if result is not None:
                report+='\nCommitted: {} created; {} already present or duplicate.\n'.format(result['created'],result['existing'])
                report+='Created {} door openings (0 to 7 ft) and {} window openings (3 to 7 ft above the actual wall bottom). Walls 7 ft or shorter stay solid.\n'.format(
                    result.get('door_openings',0),result.get('window_openings',0))
                if result.get('corner_joins') or result.get('extended_corner_ends'):
                    report+='Extended {} wall ends to corners and joined {} pairs of touching wall faces.\n'.format(
                        result.get('extended_corner_ends',0),result.get('corner_joins',0))
                if 'flush_corners' in result:
                    report+='Verified both faces at {} wall corners; repaired {} exterior corners during this run.\n'.format(
                        result['flush_corners'],result['face_repairs'])
                if result.get('consolidated'):
                    report+='Consolidated {} previously traced perimeter segments.\n'.format(result['consolidated'])
                for warning in result.get('warnings',[]):
                    report+='Revit: '+warning+'\n'
            previous=getattr(self,'_report_window',None)
            if previous is not None and previous.IsVisible:
                previous.Close()
            self._report_window=WallTraceReport(self,report)
            self._report_window.Show()
        except Exception as error:
            self.status.Text+=' Report could not be opened: '+str(error)

    @api_callback
    def place_click(self,sender,args):
        try:
            if self._context is None or self._context!=self.context():
                raise ValueError('Scan the current source before placement.')
            fresh=read_cad(self.doc,self.cad())
            if self.source_stamp(fresh)!=self._source_stamp:
                self.geometry=fresh
                self.invalidate('CAD geometry changed. Refreshing thicknesses before placement.')
                return
            self.filter_changed(None,None)
            if not self.place_button.IsEnabled:
                return
            top=self.levels[self.top_level.SelectedIndex] if self.top_level.SelectedIndex>=0 else None
            bottom=self.levels[self.bottom_level.SelectedIndex] if self.bottom_level.SelectedIndex>=0 else None
            choices={k:self.selected_type(c) for k,(p,c) in self.controls.items()}
            from ndev_main_cad_mapping_place import place
            result=place(self.doc,self.kind,self.cad(),self.rows,choices,bottom,top,
                         self.measure('bottom_offset')/304.8 if self.kind=='Walls' else 0,
                         self.measure('top_offset')/304.8,bool(self.exclude_below.IsChecked),
                         self.measure('cutoff_width') if self.exclude_below.IsChecked else 0,
                         create_doors=bool(self.create_doors.IsChecked),
                         create_windows=bool(self.create_windows.IsChecked))
            self.status.Text='Created {} {}. {} existing placements. {} ambiguous pairs withheld.'.format(
                result['created'],self.kind.lower(),result['existing'],result['ambiguous'])
            if result.get('openings'):
                self.status.Text+=' {} openings created.'.format(result['openings'])
            if result.get('corner_joins') or result.get('extended_corner_ends') or result.get('face_repairs'):
                self.status.Text+=' Corner repairs are listed in the Trace report.'
            if result['warnings']:
                self.status.Text+=' See Trace report for placement details.'
            if result.get('rejected'):
                self.status.Text+=' {} runs rejected. See Trace report for locations and reasons.'.format(result['rejected'])
            self.write_report('Placement completed',result)
        except Exception as error:
            self.status.Text='Placement stopped: '+str(error)
            if self._context is not None and self.rows:
                self.write_report('Placement stopped',failed=str(error))

    def help_click(self,sender,args):
        MappingHelp(self.kind,self).show_dialog()

    def github_click(self,sender,args):
        open_link(GITHUB_URL)

    def next_joke_click(self,sender,args):
        if self.humor_enabled.IsChecked:
            self._joke_index=(self._joke_index+1)%len(JOKES)
            self.joke_text.Text=JOKES[self._joke_index]

    def update_humor(self):
        enabled=bool(self.humor_enabled.IsChecked)
        self.next_joke.IsEnabled=enabled
        self.joke_text.Visibility=Visibility.Visible if enabled else Visibility.Collapsed
        if enabled:
            self.next_joke_click(None,None)
            self._joke_timer.Start()
        else:
            self._joke_timer.Stop()

    def humor_click(self,sender,args):
        self.update_humor()
        try:
            with io.open(self._ui_path,'w',encoding='utf-8') as stream:
                stream.write(unicode(json.dumps({'humor':bool(self.humor_enabled.IsChecked)})))
        except IOError as error:
            self.status.Text='Could not save the BIM Humor preference: '+str(error)

    def window_closed(self,sender,args):
        self._closed=True
        self._event_handler.pending=[]
        self._external_event.Dispose()
        if self in OPEN_WINDOWS:
            OPEN_WINDOWS.remove(self)
        self._scan_timer.Stop()
        self._scan_timer.Tick -= self.auto_scan
        self._joke_timer.Stop()
        self._joke_timer.Tick -= self.next_joke_click

    def mapping_key_down(self,sender,args):
        if self._busy_operation is not None:
            args.Handled=True
            return
        if args.Key==Key.Escape:
            args.Handled=True
            # Escape first dismisses an open list, keeping the mapping window.
            combos=[self.cad_choice,self.unit_choice,self.bottom_level,self.top_level]
            combos.extend(c for p,c in self.controls.values())
            for combo in combos:
                if combo.IsDropDownOpen:
                    combo.IsDropDownOpen=False
                    return
            self.Close()

    def confirm_close(self,sender,args):
        prompt=MappingCancel(self)
        prompt.show_dialog()
        args.Cancel=not prompt.confirmed

    def cancel_click(self,sender,args):
        self.Close()


def show(kind):
    if revit.doc is None or revit.doc.IsFamilyDocument:
        forms.alert('Open a Revit project before mapping CAD.',exitscript=True)
    window=MappingWindow(kind,revit.doc)
    OPEN_WINDOWS.append(window)
    window.Show()
