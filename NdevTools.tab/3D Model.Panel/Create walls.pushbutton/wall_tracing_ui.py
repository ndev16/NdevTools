# -*- coding: utf-8 -*-
"""Two-page WPF wizard. No document mutations occur in this module."""
import os
from pyrevit import DB, UI, forms, script
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
from System import Uri
from System.Windows import Thickness, GridLength, GridUnitType, Visibility, TextWrapping, SystemParameters
from System.Windows.Controls import Grid, ColumnDefinition, TextBlock, ComboBox, CheckBox, StackPanel, Border
from System.Windows.Media import BrushConverter
from System.Windows.Media.Imaging import BitmapImage
from wall_tracing_engine import key, name, levels, host_types, collect_walls, analyze_type, validate
from wall_tracing_math import suggest_wall_type


def brush(value):
    return BrushConverter().ConvertFromString(value)


def text(value, size=14):
    block = TextBlock()
    block.Text = value
    block.FontSize = size
    block.TextWrapping = TextWrapping.Wrap
    block.Margin = Thickness(8, 7, 8, 7)
    return block


def row(widths):
    grid = Grid()
    for width in widths:
        column = ColumnDefinition()
        column.Width = GridLength(width, GridUnitType.Star)
        grid.ColumnDefinitions.Add(column)
    return grid


def add(grid, control, column):
    Grid.SetColumn(control, column)
    grid.Children.Add(control)


def combo(labels, selected=0):
    control = ComboBox()
    control.Margin = Thickness(5)
    for label in labels:
        control.Items.Add(label)
    control.SelectedIndex = selected
    return control


class LinkFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, DB.RevitLinkInstance)

    def AllowReference(self, reference, position):
        return False


class WallTracingWindow(forms.WPFWindow):
    def __init__(self, doc, uidoc, root):
        forms.WPFWindow.__init__(self, os.path.join(root, 'WallTracing.xaml'))
        self.Height = max(self.MinHeight, min(self.Height, SystemParameters.WorkArea.Height - 40))
        self.doc, self.uidoc = doc, uidoc
        self.result, self.link = None, None
        self.page = 1
        self.checks, self.config_controls = [], []
        self.saved = {}
        self.host_levels, self.wall_types = levels(doc), host_types(doc)
        self.links = sorted(DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance), key=lambda l: l.Name)
        self.brand_logo.Source = BitmapImage(Uri(os.path.join(root, 'reference', 'NdevTools_Logo.png')))
        for link in self.links:
            self.link_combo.Items.Add('{} [ID {}]'.format(link.Name, key(link.Id)))
        self.link_combo.SelectionChanged += self.change_link
        self.pick_button.Click += self.pick_link
        self.search_box.TextChanged += self.filter_levels
        self.select_all_button.Click += self.select_all
        self.deselect_all_button.Click += self.deselect_all
        self.next_button.Click += self.advance
        self.back_button.Click += self.go_back
        self.cancel_button.Click += self.cancel
        self.help_button.Click += self.show_help
        self.search_box.ToolTip = 'Search level names; Select All applies to every linked level.'
        if self.links:
            self.link_combo.SelectedIndex = 0
        else:
            self.link_info.Text = 'No Revit link instances found. Link an architectural model, then run Wall Tracing again.'
            self.next_button.IsEnabled = False

    def length(self, value):
        return DB.UnitFormatUtils.Format(self.doc.GetUnits(), DB.SpecTypeId.Length, value, False)

    def change_link(self, sender, args):
        self.checks = []
        self.saved = {}
        self.level_rows.Children.Clear()
        index = self.link_combo.SelectedIndex
        self.link = self.links[index] if index >= 0 else None
        linked = self.link.GetLinkDocument() if self.link else None
        self.next_button.IsEnabled = linked is not None
        if linked is None:
            self.link_info.Text = 'Status: Unloaded / inaccessible. Select a loaded link.'
            self.update_count(None, None)
            return
        linked_levels = levels(linked)
        self.link_info.Text = 'File: {}\nPath: {}\nStatus: Loaded    |    Total Levels: {}'.format(
            linked.Title, linked.PathName or '(Cloud model / path unavailable)', len(linked_levels))
        header = row([0.5, 3, 1.5, 0.8])
        for i,label in enumerate(('#','Level Name','Elevation','Select')):
            add(header,text(label),i)
        self.level_rows.Children.Add(header)
        for i,level in enumerate(linked_levels):
            grid = row([0.5,3,1.5,0.8])
            grid.Background = brush('#0B2536' if i % 2 == 0 else '#071E2D')
            add(grid,text(str(i+1)),0)
            add(grid,text(level.Name),1)
            add(grid,text(self.length(level.Elevation)),2)
            check = CheckBox()
            check.Checked += self.update_count
            check.Unchecked += self.update_count
            add(grid,check,3)
            self.level_rows.Children.Add(grid)
            self.checks.append((level,check,grid))
        self.filter_levels(None,None)
        self.update_count(None,None)

    def pick_link(self, sender, args):
        self.Hide()
        try:
            reference = self.uidoc.Selection.PickObject(ObjectType.Element, LinkFilter(), 'Pick an architectural Revit link')
            for i,link in enumerate(self.links):
                if link.Id == reference.ElementId:
                    self.link_combo.SelectedIndex = i
                    break
        except OperationCanceledException:
            pass
        except Exception as error:
            forms.alert(str(error), title='Wall Tracing')
        finally:
            self.Show()
            self.Activate()

    def filter_levels(self, sender, args):
        query = (self.search_box.Text or '').lower().strip()
        for level,check,grid in self.checks:
            grid.Visibility = Visibility.Visible if query in level.Name.lower() else Visibility.Collapsed

    def update_count(self, sender, args):
        self.selection_count.Text = '{} of {} levels selected'.format(sum(1 for l,c,g in self.checks if c.IsChecked),len(self.checks))

    def select_all(self, sender, args):
        for level,check,grid in self.checks:
            check.IsChecked = True

    def deselect_all(self, sender, args):
        for level,check,grid in self.checks:
            check.IsChecked = False

    def set_page(self, page):
        self.page = page
        self.page_one.Visibility = Visibility.Visible if page == 1 else Visibility.Collapsed
        self.page_two.Visibility = Visibility.Visible if page == 2 else Visibility.Collapsed
        self.back_button.Visibility = Visibility.Collapsed if page == 1 else Visibility.Visible
        self.next_button.Content = 'Next  →' if page == 1 else 'Create Walls'
        self.step_one.Background = brush('#00C6E8' if page == 1 else '#0B2A3D')
        self.step_two.Background = brush('#00C6E8' if page == 2 else '#0B2A3D')
        self.step_one_text.Foreground = brush('#031A28' if page == 1 else '#8DB6CC')
        self.step_two_text.Foreground = brush('#031A28' if page == 2 else '#8DB6CC')

    def build_mapping(self, selected):
        linked = self.link.GetLinkDocument()
        grouped = collect_walls(linked,[key(l.Id) for l in selected])
        self.mapping_panels.Children.Clear()
        self.config_controls = []
        level_labels = ['{} ({})'.format(l.Name,self.length(l.Elevation)) for l in self.host_levels]
        type_labels = ['None'] + ['{} [ID {}]'.format(name(t),key(t.Id)) for t in self.wall_types]
        for level in selected:
            level_key = key(level.Id)
            saved = self.saved.get(level_key)
            card = Border()
            card.Style = self.FindResource('Card')
            card.Margin = Thickness(0,0,0,12)
            panel = StackPanel()
            card.Child = panel
            panel.Children.Add(text('{}  |  Elevation: {}  |  {} source walls'.format(level.Name,self.length(level.Elevation),len(grouped[level_key])),18))
            heading = row([2,2])
            add(heading,text('Host Bottom Level'),0)
            add(heading,text('Host Top Level'),1)
            panel.Children.Add(heading)
            controls = row([2,2])
            # Suggestions use the transformed source elevation; user retains final control.
            source_z = self.link.GetTotalTransform().OfPoint(DB.XYZ(0,0,level.ProjectElevation)).Z
            bottom_index = min(range(len(self.host_levels)),key=lambda i: abs(self.host_levels[i].ProjectElevation-source_z))
            top_index = bottom_index+1 if bottom_index+1 < len(self.host_levels) else -1
            if saved:
                bottom_index,top_index = saved['bottom_index'],saved['top_index']
            bottom,top = combo(level_labels,bottom_index),combo(level_labels,top_index)
            add(controls,bottom,0)
            add(controls,top,1)
            panel.Children.Add(controls)
            widths = [0.3,2.1,1.0,1.8,2.5]
            header = row(widths)
            for i,label in enumerate(('#','Architectural Wall Type','Structure [1]\nthickness','Detected Layer / Material','Host Wall Type')):
                add(header,text(label,12),i)
            panel.Children.Add(header)
            types = {}
            for wall in grouped[level_key]:
                types[key(wall.GetTypeId())] = wall.WallType
            mappings = {}
            for i,(type_key,source_type) in enumerate(sorted(types.items(),key=lambda item: name(item[1]).lower())):
                analysis = analyze_type(source_type)
                grid = row(widths)
                grid.Background = brush('#0B2536' if i%2 == 0 else '#071E2D')
                add(grid,text(str(i+1)),0)
                add(grid,text(name(source_type)),1)
                add(grid,text(self.length(analysis['thickness']) if analysis['supported'] else 'Unsupported'),2)
                layer = 'Layer {}: {}'.format(analysis['index']+1,analysis['material']) if analysis['supported'] else analysis['reason']
                add(grid,text(layer,12),3)
                suggestion, exact = suggest_wall_type(analysis['thickness'],
                    [(index, wt.Width) for index, wt in enumerate(self.wall_types)])
                default_index = suggestion+1 if analysis['supported'] and suggestion is not None else 0
                selected_index = saved['mapping'].get(type_key,default_index) if saved else default_index
                mapping = combo(type_labels,selected_index)
                mapping.IsEnabled = analysis['supported']
                mapping.ToolTip = layer
                if not analysis['supported']:
                    mapping.SelectedIndex = 0
                mapping_panel = StackPanel()
                mapping_panel.Children.Add(mapping)
                if analysis['supported'] and suggestion is not None:
                    hint = ('Width-based suggestion: same thickness. Review type.' if exact else
                            'Nearest width only: {}. Review type and thickness.'.format(
                                self.length(self.wall_types[suggestion].Width)))
                    note = text(hint,11)
                    note.Foreground = brush('#8DB6CC' if exact else '#FFC66D')
                    mapping_panel.Children.Add(note)
                    mapping.ToolTip = layer + '\n' + hint + '\nWidth does not establish material or structural equivalence.'
                add(grid,mapping_panel,4)
                mappings[type_key] = mapping
                panel.Children.Add(grid)
            if not types:
                panel.Children.Add(text('No walls use this level as their Base Constraint.'))
            self.mapping_panels.Children.Add(card)
            self.config_controls.append((level,bottom,top,mappings))

    def advance(self, sender, args):
        try:
            if self.page == 1:
                selected = [l for l,c,g in self.checks if c.IsChecked]
                if not selected:
                    raise ValueError('Select at least one linked level.')
                if self.link is None or self.link.GetLinkDocument() is None:
                    raise ValueError('Select a loaded architectural link.')
                if len(self.host_levels) < 2 or not self.wall_types:
                    raise ValueError('The host project needs at least two levels and one Basic Wall type.')
                self.build_mapping(selected)
                self.set_page(2)
                return
            configs = []
            for level,bottom,top,mappings in self.config_controls:
                if bottom.SelectedIndex < 0 or top.SelectedIndex < 0:
                    raise ValueError('Choose host bottom and top levels for ' + level.Name)
                values = {}
                for type_key,control in mappings.items():
                    if control.SelectedIndex < 0:
                        raise ValueError('Choose a host wall type or None.')
                    values[type_key] = self.wall_types[control.SelectedIndex-1].Id if control.SelectedIndex > 0 else None
                configs.append(dict(source_level=level.Id,label=level.Name,
                                    bottom=self.host_levels[bottom.SelectedIndex].Id,
                                    top=self.host_levels[top.SelectedIndex].Id,mapping=values))
            validate(self.doc,self.link,configs)
            self.result = (self.link,configs)
            self.Close()
        except Exception as error:
            forms.alert(str(error), title='Wall Tracing')

    def go_back(self, sender, args):
        for level,bottom,top,mappings in self.config_controls:
            self.saved[key(level.Id)] = dict(bottom_index=bottom.SelectedIndex,top_index=top.SelectedIndex,
                                            mapping=dict((k,c.SelectedIndex) for k,c in mappings.items()))
        self.set_page(1)

    def cancel(self, sender, args):
        self.Close()

    def show_help(self, sender, args):
        # Avoid CommandSwitchWindow's WPF resource lookup on affected pyRevit builds.
        dialog = UI.TaskDialog('Wall Tracing Help')
        dialog.MainInstruction = 'Need help with Wall Tracing?'
        dialog.MainContent = ('If you encounter an error or need assistance with this tool, '
                              'please contact me through NdevTools GitHub.')
        dialog.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink1, 'Open NdevTools on GitHub')
        dialog.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink2, 'Report an Issue')
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Close
        choice = dialog.Show()
        if choice == UI.TaskDialogResult.CommandLink1:
            script.open_url('https://github.com/ndev16/NdevTools')
        elif choice == UI.TaskDialogResult.CommandLink2:
            script.open_url('https://github.com/ndev16/NdevTools/issues/new')
