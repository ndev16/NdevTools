# -*- coding: utf-8 -*-

from ndev_i18n import show_localized_dialog as _ndev_show_localized_dialog
from ndev_annotation_theme import finish_detail_settings as _ndev_theme_settings
from ndev_annotation_theme import attach_dialog as _ndev_attach_dialog
from ndev_annotation_theme import show_detail_message as _ndev_alert
"""Trace floors, walls, roofs, foundations, and framing as view-specific details.

Regions are static snapshots. Plan footprints do not remove areas hidden by
other elements. Symbolic metal-deck graphics are not necessarily solid geometry.
"""
from pyrevit import revit, DB, forms, script
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List
from System.Windows import Thickness, GridLength, GridUnitType, TextWrapping, RoutedEventHandler
from System.Windows.Controls import Grid, ColumnDefinition, TextBlock, ComboBox, TextBox
from System.Windows.Controls.Primitives import TextBoxBase
from System.Windows.Input import Key
import os
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import (Window, WindowStartupLocation, ResizeMode,
                            VerticalAlignment, FontWeights, WindowState,
                            CornerRadius)
from System.Windows.Shell import WindowChrome
from System.Windows.Controls import (Button, DockPanel, Dock,
                                     StackPanel, ScrollViewer)

TITLE = 'Ndev Tools - Auto Detail Generator'
doc = revit.doc
uidoc = revit.uidoc
view = revit.active_view
EPS = 1.0e-6

# ============================================================
# NDEV TOOLS | SHARED HELP WINDOW AND UI BRANDING
# ============================================================
NDEV_GITHUB_URL = 'https://github.com/ndev16'
NDEV_LINKEDIN_URL = 'https://www.linkedin.com/in/nataraj016/'


def ndev_open_profile(url):
    """Open the author's public profile in the default browser."""
    try:
        info = ProcessStartInfo(url)
        info.UseShellExecute = True
        Process.Start(info)
    except Exception as error:
        _ndev_alert(
            'Could not open your default browser.\n\n'
            'Copy and open this URL:\n{}\n\n{}'.format(url, error),
            title=TITLE + ' - Help')


def ndev_show_help(owner=None):
    """Show Help, GitHub and LinkedIn without changing Revit data."""
    help_window = Window()
    help_window.Title = TITLE + ' - Help'
    help_window.Width = 525
    help_window.Height = 390
    help_window.MinWidth = 460
    help_window.ResizeMode = ResizeMode.NoResize
    help_window.ShowInTaskbar = False
    help_window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    if owner is not None:
        help_window.Owner = owner
        help_window.WindowStartupLocation = WindowStartupLocation.CenterOwner

    panel = StackPanel()
    panel.Margin = Thickness(18, 14, 18, 14)

    heading = TextBlock()
    heading.Text = 'NDEV TOOLS | AUTO DETAIL GENERATOR'
    heading.FontWeight = FontWeights.Bold
    heading.Margin = Thickness(0, 0, 0, 12)
    panel.Children.Add(heading)

    instructions = TextBlock()
    instructions.Text = (
        '1. Open a Revit plan or section view.\n'
        '2. Choose all supported elements or pick individual elements.\n'
        '3. In the settings tabs, select a filled region, outline style, '
        'and optional detail component for each element type.\n'
        '4. Click Create Details. The tool creates view-specific detail '
        'graphics from the current geometry.\n\n'
        'Important: generated details are static snapshots. Re-running '
        'the tool can create additional details.'
    )
    instructions.TextWrapping = TextWrapping.Wrap
    instructions.Margin = Thickness(0, 0, 0, 15)
    panel.Children.Add(instructions)

    github = Button()
    github.Content = 'GitHub  |  github.com/ndev16'
    github.Height = 34
    github.Margin = Thickness(0, 0, 0, 9)
    github.Click += lambda sender, args: ndev_open_profile(NDEV_GITHUB_URL)
    panel.Children.Add(github)

    linkedin = Button()
    linkedin.Content = 'LinkedIn  |  linkedin.com/in/nataraj016'
    linkedin.Height = 34
    linkedin.Margin = Thickness(0, 0, 0, 6)
    linkedin.Click += lambda sender, args: ndev_open_profile(NDEV_LINKEDIN_URL)
    panel.Children.Add(linkedin)

    scroller = ScrollViewer()
    scroller.Content = panel
    help_window.Content = scroller
    _ndev_attach_dialog(help_window, ('Detail', 'Generator'),
                        'TRACE | FILL | OUTLINE | DETAIL')
    _ndev_show_localized_dialog(help_window)


def ndev_attach_help(window, title=None):
    """Give the existing native mode picker the shared ViewPilot frame."""
    if title:
        window.Title = title
    _ndev_attach_dialog(window, ('Detail', 'Generator'),
                        'TRACE | FILL | OUTLINE | DETAIL', ndev_show_help)

class NdevModeSelector(forms.CommandSwitchWindow):
    """Same native pyRevit mode selector, with Ndev Tools Help above it."""
    def _setup(self, **kwargs):
        forms.CommandSwitchWindow._setup(self, **kwargs)
        ndev_attach_help(self, TITLE + ' - Select Elements')



def stop(message):
    _ndev_alert(message, title=TITLE, exitscript=True)


def id_text(element_id):
    return str(element_id.Value if hasattr(element_id, 'Value')
               else element_id.IntegerValue)


def solids_in(geometry):
    if geometry is None:
        return
    for item in geometry:
        if isinstance(item, DB.Solid):
            if item.Faces.Size and item.Volume > EPS ** 3:
                yield item
        elif isinstance(item, DB.GeometryInstance):
            for solid in solids_in(item.GetInstanceGeometry()):
                yield solid


def project_point(point):
    distance = point.Subtract(origin).DotProduct(normal)
    return point.Subtract(normal.Multiply(distance))


def project_loops(loops):
    """Keep native curves for parallel faces; project straight sloping edges."""
    result = List[DB.CurveLoop]()
    for loop in loops:
        projected = DB.CurveLoop()
        if loop.HasPlane() and abs(loop.GetPlane().Normal.DotProduct(normal)) > 1 - EPS:
            distance = loop.GetPlane().Origin.Subtract(origin).DotProduct(normal)
            transform = DB.Transform.CreateTranslation(normal.Multiply(-distance))
            for curve in loop:
                projected.Append(curve.CreateTransformed(transform))
        else:
            for curve in loop:
                if not isinstance(curve, DB.Line):
                    raise ValueError('A sloped face has curved edges; exact projection is unsupported.')
                a = project_point(curve.GetEndPoint(0))
                b = project_point(curve.GetEndPoint(1))
                if a.DistanceTo(b) <= doc.Application.ShortCurveTolerance:
                    raise ValueError('A projected edge is shorter than Revit allows.')
                projected.Append(DB.Line.CreateBound(a, b))
        result.Add(projected)
    return result


def extrude(loops):
    # Temporary geometry only: these solids are never added to the document.
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(loops, normal, 1.0)


def faces_on_plane(solid, plane_origin=None):
    plane_origin = origin if plane_origin is None else plane_origin
    if solid is None:
        return
    for face in solid.Faces:
        if (isinstance(face, DB.PlanarFace)
                and abs(face.FaceNormal.DotProduct(normal)) > 1 - EPS
                and abs(face.Origin.Subtract(plane_origin).DotProduct(normal)) < EPS):
            yield face


def section_faces(solid, plane_origin=None):
    """Reuse an existing cut cap before attempting another Boolean cut."""
    plane_origin = origin if plane_origin is None else plane_origin
    faces = list(faces_on_plane(solid, plane_origin))
    if faces:
        return faces
    # ViewDirection points TOWARDS the viewer. Keep geometry into the view.
    # The old positive half-space could discard an already view-clipped solid.
    plane = DB.Plane.CreateByNormalAndOrigin(normal.Negate(), plane_origin)
    cut = DB.BooleanOperationsUtils.CutWithHalfSpace(solid, plane)
    return list(faces_on_plane(cut, plane_origin))


def section_pieces(element, plane_origin=None):
    """Prefer view geometry, then retry with uncut model solids at the same plane."""
    errors = []
    for use_view in (True, False):
        options = DB.Options()
        options.IncludeNonVisibleObjects = False
        if use_view:
            options.View = view
        else:
            # Do not set View here: it can remove the part needed by the cut.
            options.DetailLevel = DB.ViewDetailLevel.Fine
        pieces = []
        try:
            for solid in solids_in(element.get_Geometry(options)):
                for face in section_faces(solid, plane_origin):
                    pieces.append(extrude(project_loops(face.GetEdgesAsCurveLoops())))
        except Exception as error:
            errors.append('{} geometry: {}'.format(
                'View' if use_view else 'Model', error))
            continue
        if pieces:
            return pieces
    if errors:
        raise ValueError('Section extraction failed. ' + ' | '.join(errors))
    raise ValueError('No cut outline found in view or model geometry at the section '
                     'plane. The element may be visible beyond the cut rather than '
                     'intersecting it.')


def wall_cut_origin():
    view_range = view.GetViewRange()
    plane = DB.PlanViewPlane.CutPlane
    level_id = view_range.GetLevelId(plane)
    level = doc.GetElement(level_id)
    if level is None:
        if level_id == DB.PlanViewRange.Current:
            level = view.GenLevel
        else:
            raise ValueError('The plan cut plane does not reference a usable level.')
    return DB.XYZ(0, 0, level.ProjectElevation + view_range.GetOffset(plane))


def trace_element(element, crop_solid):
    options = DB.Options()
    options.View = view
    options.IncludeNonVisibleObjects = False
    wall_plan = is_plan and category_key(element) == 'Walls'
    if wall_plan:
        pieces = section_pieces(element, wall_cut_origin())
    else:
        pieces = [] if is_plan else section_pieces(element)
    plan_solids = (solids_in(element.get_Geometry(options))
                   if is_plan and not wall_plan else [])
    for solid in plan_solids:
        if is_plan:
            # Top planar patches include shape-edited and sloped slabs.
            for face in solid.Faces:
                if isinstance(face, DB.PlanarFace):
                    if face.FaceNormal.Z > EPS:
                        pieces.append(extrude(project_loops(face.GetEdgesAsCurveLoops())))
                else:
                    # Do not silently omit a curved upward-facing patch.
                    bounds = face.GetBoundingBox()
                    uv = DB.UV((bounds.Min.U + bounds.Max.U) / 2,
                               (bounds.Min.V + bounds.Max.V) / 2)
                    if face.ComputeNormal(uv).Z > EPS:
                        raise ValueError('Curved top surfaces cannot be traced exactly.')
    if not pieces:
        raise ValueError('No component footprint found.' if is_plan
                         else 'Element does not intersect the section plane.')

    # Union patches before extracting loops: no internal facet lines or duplicate fills.
    merged = pieces[0]
    for piece in pieces[1:]:
        merged = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
            merged, piece, DB.BooleanOperationsType.Union)
    if crop_solid is not None:
        merged = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
            merged, crop_solid, DB.BooleanOperationsType.Intersect)
    boundaries = [project_loops(face.GetEdgesAsCurveLoops())
                  for face in faces_on_plane(merged)]
    if not boundaries:
        raise ValueError('No outline remains inside the view crop.')
    return boundaries


CATEGORIES = [
    ('Walls', DB.BuiltInCategory.OST_Walls),
    ('Floors', DB.BuiltInCategory.OST_Floors),
    ('Structural Foundations', DB.BuiltInCategory.OST_StructuralFoundation),
    ('Structural Framing', DB.BuiltInCategory.OST_StructuralFraming),
    ('Roofs', DB.BuiltInCategory.OST_Roofs)
]
NONE_LABEL = 'None - no fill'
FREQUENT_REGIONS = ['2x4 WOOD STUD', '2x6 WOOD STUD', '2x8 WOOD STUD',
                    '6" CFS', '8" BB', '8" CIP', '8" CMU',
                    '12" BB', '12" CIP', '12" CMU']


def category_key(element):
    if element.Category:
        for name, category in CATEGORIES:
            if id_text(element.Category.Id) == str(int(category)):
                return name
    return None


def mapping_key(element):
    return (category_key(element), id_text(element.GetTypeId()))


def type_label(element):
    element_type = doc.GetElement(element.GetTypeId())
    if element_type is None:
        return 'Type {}'.format(id_text(element.GetTypeId()))
    parameter = element_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    name = parameter.AsString() if parameter else id_text(element_type.Id)
    family = element_type.FamilyName
    return '{} : {}'.format(family, name) if family else name


def region_sort_key(name):
    normalized = name.strip().lower()
    favorites = [item.lower() for item in FREQUENT_REGIONS]
    return (favorites.index(normalized) if normalized in favorites else len(favorites),
            normalized)


def is_cmu(element):
    if category_key(element) != 'Walls':
        return False
    names = [type_label(element)]
    for material_id in element.GetMaterialIds(False):
        material = doc.GetElement(material_id)
        if material:
            names.append(material.Name)
    text = ' '.join(names).lower()
    return 'cmu' in text or 'concrete masonry' in text


def make_combo(choices):
    combo = ComboBox()
    combo.MinHeight = 30
    combo.MaxDropDownHeight = 320
    combo.IsTextSearchEnabled = True
    for name in choices:
        combo.Items.Add(name)
    combo.SelectedIndex = 0
    return combo


def filter_choices(choices, query):
    """Case-insensitive contains search, requiring every typed word."""
    words = query.lower().split()
    return [item for item in choices if all(word in item.lower() for word in words)]


def searchable_dropdown(combo):
    """Editable combo with live, automatically opened matching suggestions."""
    choices = list(combo.Items)
    state = {'busy': False, 'committed': combo.SelectedItem}
    combo.IsEditable = True
    combo.IsTextSearchEnabled = False  # Native prefix completion fights contains search.
    combo.StaysOpenOnEdit = True

    def replace_items(items, text, selected=None):
        state['busy'] = True
        try:
            combo.Items.Clear()
            for item in items:
                combo.Items.Add(item)
            combo.SelectedItem = selected
            combo.Text = text
        finally:
            state['busy'] = False

    def changed(sender, args):
        editor = args.OriginalSource
        if state['busy'] or not isinstance(editor, TextBox) or not editor.IsKeyboardFocusWithin:
            return
        query = editor.Text or ''
        if combo.SelectedItem is not None and query == combo.SelectedItem:
            return  # Clicking a suggestion commits it; do not refilter that click.
        start, length = editor.SelectionStart, editor.SelectionLength
        matches = filter_choices(choices, query)
        replace_items(matches, query)
        state['busy'] = True
        try:
            combo.IsDropDownOpen = True
            editor.Focus()
            editor.Select(min(start, len(query)), min(length, max(0, len(query) - start)))
        finally:
            state['busy'] = False

    def selected(sender, args):
        if not state['busy'] and combo.SelectedItem is not None:
            state['committed'] = combo.SelectedItem

    def opened(sender, args):
        if state['busy']:
            return
        # Opening a committed dropdown manually shows the full catalog again.
        if combo.SelectedItem is not None:
            selected_item = combo.SelectedItem
            replace_items(choices, selected_item, selected_item)

    def key_down(sender, args):
        if args.Key == Key.Enter and combo.IsDropDownOpen:
            args.Handled = True  # Do not also activate the Create Details button.
            item = combo.SelectedItem
            if item is None and combo.Items.Count:
                item = combo.Items[0]
            if item is not None:
                state['committed'] = item
                replace_items(choices, item, item)
                combo.IsDropDownOpen = False
        elif args.Key == Key.Escape and combo.IsDropDownOpen:
            args.Handled = True
            item = state['committed']
            replace_items(choices, item, item)
            combo.IsDropDownOpen = False

    combo.AddHandler(TextBoxBase.TextChangedEvent, RoutedEventHandler(changed))
    combo.SelectionChanged += selected
    combo.DropDownOpened += opened
    combo.PreviewKeyDown += key_down
    return combo


def settings_grid():
    row = Grid()
    row.Margin = Thickness(0, 0, 0, 10)
    for width in (280, 240, 190, 240, 115):
        column = ColumnDefinition()
        column.Width = GridLength(width)
        row.ColumnDefinitions.Add(column)
    return row


class TraceSettings(forms.WPFWindow):
    def __init__(self, groups, region_choices, line_choices, repeat_choices, detail_choices, floor_choices):
        forms.WPFWindow.__init__(self, os.path.join(
            os.path.dirname(__file__), 'TraceSettings.xaml'))
        self.result = None
        self.controls = {}
        self.choices = (region_choices, line_choices, repeat_choices)
        self.detail_choices = detail_choices
        self.floor_choices = floor_choices
        panels = {'Walls': self.walls_panel, 'Floors': self.floors_panel,
                  'Structural Foundations': self.foundations_panel,
                  'Structural Framing': self.framing_panel,
                  'Roofs': self.roofs_panel}
        for category, panel in panels.items():
            header = settings_grid()
            framing = category == 'Structural Framing'
            floor = category == 'Floors'
            roof = category == 'Roofs'
            detail_heading = ('Centered detail component' if framing else
                              'Horizontal detail component' if floor else
                              'Roof top detail component' if roof else 'CMU repeating detail')
            for index, text in enumerate(('Component type (instances)', 'Filled region',
                                          'Outline line style', detail_heading, 'Direction')):
                label = TextBlock()
                label.Text = text
                Grid.SetColumn(label, index)
                header.Children.Add(label)
            panel.Children.Add(header)
            rows = sorted([(key, data) for key, data in groups.items()
                           if key[0] == category], key=lambda item: item[1]['name'].lower())
            if not rows:
                empty = TextBlock()
                empty.Text = 'No {} in the chosen scope.'.format(category.lower())
                panel.Children.Add(empty)
            for key, data in rows:
                row = settings_grid()
                label = TextBlock()
                label.Text = '{} ({})'.format(data['name'], len(data['elements']))
                label.ToolTip = label.Text
                label.TextWrapping = TextWrapping.Wrap
                label.Margin = Thickness(0, 5, 16, 5)
                row.Children.Add(label)
                fill = make_combo([NONE_LABEL] + region_choices)
                line = make_combo(['Default / no extra lines'] + line_choices)
                repeat = make_combo(['None'] + (detail_choices if framing else
                                               floor_choices if floor or roof else repeat_choices))
                direction = make_combo(['Center aligned'] if framing else ['Horizontal'] if floor else ['Top edges' if is_plan else 'Top slope'] if roof else (
                    ['Horizontal', 'Vertical'] if not is_plan else ['Wall length']))
                cmu = data['cmu']
                repeat.IsEnabled = cmu or framing or floor or roof
                direction.IsEnabled = cmu
                repeat.ToolTip = ('Places one detail per framing element and aligns bounding-box centers.'
                                  if framing else 'Stretches a line-based detail horizontally through the floor. Load a line-based Detail Item family if only None is listed.'
                                  if floor else 'Follows the roof top profile in sections and projected top-face edges in plans with line-based details. Load a line-based Detail Item if only None appears.'
                                  if roof else 'Uses an existing repeating detail as a placement template.'
                                  if cmu else 'Available only for walls with CMU in the type or material name.')
                for index, control in enumerate((fill, line, repeat, direction), 1):
                    dropdown = searchable_dropdown(control)
                    dropdown.Margin = Thickness(0, 0, 10, 0)
                    Grid.SetColumn(dropdown, index)
                    row.Children.Add(dropdown)
                self.controls[key] = (fill, line, repeat, direction)
                panel.Children.Add(row)
        self.create_button.Click += self.accept

        # Ndev Tools custom title bar: Help is in the same row as
        # minimize, maximize, and close. No secondary Help/brand row.
        self.Title = TITLE + ' - Trace Settings'
        self.title_caption.Text = self.Title
        self.title_help_button.Click += self._ndev_title_help
        self.title_minimize_button.Click += self._ndev_title_minimize
        self.title_maximize_button.Click += self._ndev_title_maximize
        self.title_close_button.Click += self._ndev_title_close
        self.title_bar.MouseLeftButtonDown += self._ndev_title_drag
        self.StateChanged += self._ndev_title_state_changed

        # Restore native-like resize borders for WindowStyle=None.
        # CaptionHeight 0 keeps title controls fully clickable.
        chrome = WindowChrome()
        chrome.CaptionHeight = 0.0
        chrome.ResizeBorderThickness = Thickness(6)
        chrome.GlassFrameThickness = Thickness(0)
        chrome.CornerRadius = CornerRadius(0)
        WindowChrome.SetWindowChrome(self, chrome)
        _ndev_theme_settings(self)

    def _ndev_title_help(self, sender, args):
        ndev_show_help(self)

    def _ndev_title_minimize(self, sender, args):
        self.WindowState = WindowState.Minimized

    def _ndev_title_maximize(self, sender, args):
        if self.WindowState == WindowState.Maximized:
            self.WindowState = WindowState.Normal
        else:
            self.WindowState = WindowState.Maximized

    def _ndev_title_close(self, sender, args):
        # Same effect as the original window close/cancel operation.
        self.Close()

    def _ndev_title_drag(self, sender, args):
        # Double-click title bar to maximize/restore like Windows.
        if args.ClickCount == 2:
            self._ndev_title_maximize(None, None)
            args.Handled = True
        else:
            try:
                self.DragMove()
            except Exception:
                pass

    def _ndev_title_state_changed(self, sender, args):
        # Keep maximize/restore symbol informative.
        if self.WindowState == WindowState.Maximized:
            self.title_maximize_button.Content = '❐'
            self.title_maximize_button.ToolTip = 'Restore window'
        else:
            self.title_maximize_button.Content = '□'
            self.title_maximize_button.ToolTip = 'Maximize window'

    def accept(self, sender, args):
        result = {}
        for key, controls in self.controls.items():
            for control in controls:
                if control.IsEnabled and control.SelectedItem is None:
                    _ndev_alert('Select a matching dropdown option, or choose None/default. '
                                'Typed search text is not yet a selection.', title=TITLE)
                    control.Focus()
                    control.IsDropDownOpen = True
                    return
            values = []
            framing = key[0] == 'Structural Framing'
            floor = key[0] == 'Floors'
            roof = key[0] == 'Roofs'
            choices_by_control = (self.choices[:2] + (self.detail_choices,) if framing else
                                  self.choices[:2] + (self.floor_choices,) if floor or roof else self.choices)
            for control, choices in zip(controls[:3], choices_by_control):
                # Filtered indexes no longer correspond to the original choices.
                selected = control.SelectedItem
                values.append(selected if control.IsEnabled and selected in choices else None)
            if any(value is not None for value in values):
                result[key] = {'fill': values[0], 'line': values[1], 'repeat': None if framing or floor or roof else values[2],
                               'detail': values[2] if framing or floor or roof else None,
                               'direction': 1 if controls[3].SelectedItem == 'Vertical' else 0}
        if not result:
            _ndev_alert('Choose a filled region, line style, repeating detail, or floor/roof/framing detail component.', title=TITLE)
            return
        self.result = result
        self.Close()


def repeating_paths(element, boundaries, direction, horizontal=False):
    """Intersect the centre run with traced solids, so openings split the path."""
    if is_plan and not horizontal:
        location = element.Location
        if not isinstance(location, DB.LocationCurve) or not isinstance(location.Curve, DB.Line):
            raise ValueError('Repeating details currently require a straight wall in plan.')
        axis = project_point(location.Curve.GetEndPoint(1)).Subtract(
            project_point(location.Curve.GetEndPoint(0))).Normalize()
    else:
        axis = view.UpDirection.Normalize() if direction == 1 else view.RightDirection.Normalize()
    across = normal.CrossProduct(axis).Normalize()
    points = [point for loops in boundaries for loop in loops for curve in loop
              for point in curve.Tessellate()]
    distances = [point.Subtract(origin).DotProduct(axis) for point in points]
    offsets = [point.Subtract(origin).DotProduct(across) for point in points]
    center = (min(offsets) + max(offsets)) / 2.0
    base = origin.Add(across.Multiply(center)).Add(normal.Multiply(0.5))
    run = DB.Line.CreateBound(base.Add(axis.Multiply(min(distances) - 1)),
                              base.Add(axis.Multiply(max(distances) + 1)))
    paths = []
    for loops in boundaries:
        intersection = extrude(loops).IntersectWithCurve(run, DB.SolidCurveIntersectionOptions())
        for index in range(intersection.SegmentCount):
            segment = intersection.GetCurveSegment(index)
            if segment.Length > doc.Application.ShortCurveTolerance:
                paths.append(DB.Line.CreateBound(project_point(segment.GetEndPoint(0)),
                                                  project_point(segment.GetEndPoint(1))))
    if not paths:
        raise ValueError('No component material crosses the centre run.')
    return paths


def floor_detail_paths(boundaries):
    paths = []
    # Each separate footprint/cut piece gets its own horizontal centre run.
    for loops in boundaries:
        paths.extend(repeating_paths(None, [loops], 0, horizontal=True))
    return paths


def upper_envelope(segments):
    """Return the highest straight boundary over each occupied horizontal span.

    Inputs and outputs are (u0, v0, u1, v1) in the view plane. Taking the upper
    envelope excludes undersides and internal holes without assuming loop order.
    """
    edges = []
    for x0, y0, x1, y1 in segments:
        if abs(x1 - x0) <= EPS:
            continue
        edges.append((x0, y0, x1, y1) if x0 < x1 else (x1, y1, x0, y0))
    breaks = sorted(set(x for edge in edges for x in (edge[0], edge[2])))
    spans = []
    for left, right in zip(breaks, breaks[1:]):
        if right - left <= EPS:
            continue
        middle = (left + right) / 2.0
        candidates = [(index, edge) for index, edge in enumerate(edges)
                      if edge[0] <= middle <= edge[2]]
        if not candidates:
            continue
        index, edge = max(candidates, key=lambda item: item[1][1] +
                         (middle - item[1][0]) * (item[1][3] - item[1][1]) /
                         (item[1][2] - item[1][0]))
        if spans and spans[-1][0] == index and abs(spans[-1][2] - left) <= EPS:
            spans[-1] = (index, spans[-1][1], right)
        else:
            spans.append((index, left, right))
    result = []
    for index, left, right in spans:
        x0, y0, x1, y1 = edges[index]
        slope = (y1 - y0) / (x1 - x0)
        result.append((left, y0 + (left - x0) * slope,
                       right, y0 + (right - x0) * slope))
    return result


def edge_key(a, b):
    # Order-independent endpoints avoid placing two details on shared roof ridges.
    def key(point):
        return (round(point.X, 6), round(point.Y, 6), round(point.Z, 6))
    return tuple(sorted((key(a), key(b))))


def roof_plan_paths(element, crop_solid):
    paths = []
    seen = set()
    for reference in DB.HostObjectUtils.GetTopFaces(element):
        face = element.GetGeometryObjectFromReference(reference)
        if face is None:
            raise ValueError('Revit could not read a roof top face.')
        for loop in face.GetEdgesAsCurveLoops():
            for curve in loop:
                if not isinstance(curve, DB.Line):
                    raise ValueError('Roof details need straight top-face edges; curved edges are unsupported.')
                a = project_point(curve.GetEndPoint(0))
                b = project_point(curve.GetEndPoint(1))
                if a.DistanceTo(b) <= EPS:
                    continue  # A vertical 3D edge has no length in plan.
                if a.DistanceTo(b) <= doc.Application.ShortCurveTolerance:
                    raise ValueError('A projected roof edge is too short for a detail component.')
                key = edge_key(a, b)
                if key in seen:
                    continue
                seen.add(key)
                path = DB.Line.CreateBound(a, b)
                if crop_solid is None:
                    paths.append(path)
                else:
                    inside = path.CreateTransformed(DB.Transform.CreateTranslation(normal.Multiply(0.5)))
                    clipped = crop_solid.IntersectWithCurve(inside, DB.SolidCurveIntersectionOptions())
                    for index in range(clipped.SegmentCount):
                        part = clipped.GetCurveSegment(index)
                        if part.Length > doc.Application.ShortCurveTolerance:
                            paths.append(DB.Line.CreateBound(project_point(part.GetEndPoint(0)),
                                                              project_point(part.GetEndPoint(1))))
    if not paths:
        raise ValueError('No straight roof top edges are visible inside the crop.')
    return paths


def roof_detail_paths(element, crop_solid):
    if is_plan:
        return roof_plan_paths(element, crop_solid)
    # Find the real top before cropping, avoiding an artificial edge at crop top.
    boundaries = trace_element(element, None)
    right = view.RightDirection.Normalize()
    up = view.UpDirection.Normalize()
    paths = []
    for loops in boundaries:
        segments = []
        for loop in loops:
            for curve in loop:
                if not isinstance(curve, DB.Line):
                    raise ValueError('Roof top details currently require straight roof edges; curved roofs are unsupported.')
                a = curve.GetEndPoint(0).Subtract(origin)
                b = curve.GetEndPoint(1).Subtract(origin)
                segments.append((a.DotProduct(right), a.DotProduct(up),
                                 b.DotProduct(right), b.DotProduct(up)))
        for u0, v0, u1, v1 in upper_envelope(segments):
            a = origin.Add(right.Multiply(u0)).Add(up.Multiply(v0))
            b = origin.Add(right.Multiply(u1)).Add(up.Multiply(v1))
            if a.DistanceTo(b) <= doc.Application.ShortCurveTolerance:
                raise ValueError('A roof top segment is too short for a detail component.')
            path = DB.Line.CreateBound(a, b)
            if crop_solid is None:
                paths.append(path)
            else:
                inside = path.CreateTransformed(DB.Transform.CreateTranslation(normal.Multiply(0.5)))
                clipped = crop_solid.IntersectWithCurve(inside, DB.SolidCurveIntersectionOptions())
                for index in range(clipped.SegmentCount):
                    part = clipped.GetCurveSegment(index)
                    if part.Length > doc.Application.ShortCurveTolerance:
                        paths.append(DB.Line.CreateBound(project_point(part.GetEndPoint(0)),
                                                          project_point(part.GetEndPoint(1))))
    if not paths:
        raise ValueError('The actual roof top is outside the visible crop.')
    return paths


def place_linear_details(symbol_id, paths):
    symbol = doc.GetElement(symbol_id)
    if symbol.Family.FamilyPlacementType != DB.FamilyPlacementType.CurveBasedDetail:
        raise ValueError('Floor and roof details must use a line-based Detail Item family.')
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    return [doc.Create.NewFamilyInstance(path, symbol, view).Id for path in paths]


def place_repeating_detail(template, type_id, path):
    source_view = doc.GetElement(template.OwnerViewId)
    source_ids = List[DB.ElementId]()
    source_ids.Add(template.Id)
    copied_ids = DB.ElementTransformUtils.CopyElements(
        source_view, source_ids, view, DB.Transform.Identity, DB.CopyPasteOptions())
    copies = [doc.GetElement(item_id) for item_id in copied_ids]
    repeats = [item for item in copies if isinstance(item, DB.CurveElement)
               and item.CurveElementType == DB.CurveElementType.RepeatingDetail]
    if len(repeats) != 1:
        raise ValueError('Revit did not copy exactly one repeating detail.')
    detail = repeats[0]
    if detail.Pinned:
        detail.Pinned = False
    if detail.GetTypeId() != type_id:
        replacement_id = detail.ChangeTypeId(type_id)
        if replacement_id != DB.ElementId.InvalidElementId:
            detail = doc.GetElement(replacement_id)
    doc.Regenerate()
    # View-specific copies can occupy an annotation plane offset from view.Origin.
    # Move the target run to that plane without changing its screen position.
    plane = detail.SketchPlane.GetPlane()
    shift = plane.Normal.Multiply(plane.Origin.Subtract(path.GetEndPoint(0)).DotProduct(plane.Normal))
    detail.SetGeometryCurve(path.CreateTransformed(DB.Transform.CreateTranslation(shift)), True)
    return detail.Id


def outline_center(boundaries):
    """Center of the traced extents in view coordinates, including rotated views."""
    points = [point for loops in boundaries for loop in loops for curve in loop
              for point in curve.Tessellate()]
    if not points:
        raise ValueError('No framing outline is available for centering.')
    right = view.RightDirection.Normalize()
    up = view.UpDirection.Normalize()
    u = [point.Subtract(origin).DotProduct(right) for point in points]
    v = [point.Subtract(origin).DotProduct(up) for point in points]
    return origin.Add(right.Multiply((min(u) + max(u)) / 2.0)).Add(
        up.Multiply((min(v) + max(v)) / 2.0))


def detail_center(instance):
    bounds = instance.get_BoundingBox(view)
    if bounds is None:
        raise ValueError('The detail has no bounding box in this view; center cannot be verified.')
    midpoint = bounds.Min.Add(bounds.Max).Multiply(0.5)
    return project_point(bounds.Transform.OfPoint(midpoint))


def framing_detail_path(element, boundaries, center):
    """Line-based details follow the visible framing axis when it is available."""
    axis = None
    location = element.Location
    if isinstance(location, DB.LocationCurve) and isinstance(location.Curve, DB.Line):
        vector = project_point(location.Curve.GetEndPoint(1)).Subtract(
            project_point(location.Curve.GetEndPoint(0)))
        if vector.GetLength() > doc.Application.ShortCurveTolerance:
            axis = vector.Normalize()
    if axis is None:
        edges = [curve for loops in boundaries for loop in loops for curve in loop
                 if isinstance(curve, DB.Line)]
        if not edges:
            raise ValueError('A line-based framing detail needs a straight outline edge.')
        longest = max(edges, key=lambda curve: curve.Length)
        axis = longest.GetEndPoint(1).Subtract(longest.GetEndPoint(0)).Normalize()
    distances = [point.Subtract(center).DotProduct(axis)
                 for loops in boundaries for loop in loops for curve in loop
                 for point in curve.Tessellate()]
    length = max(distances) - min(distances)
    if length <= doc.Application.ShortCurveTolerance:
        raise ValueError('The framing is too short in this view for a line-based detail.')
    return DB.Line.CreateBound(center.Subtract(axis.Multiply(length / 2.0)),
                              center.Add(axis.Multiply(length / 2.0)))


def place_framing_detail(element, symbol_id, boundaries):
    symbol = doc.GetElement(symbol_id)
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    center = outline_center(boundaries)
    if symbol.Family.FamilyPlacementType == DB.FamilyPlacementType.CurveBasedDetail:
        path = framing_detail_path(element, boundaries, center)
        instance = doc.Create.NewFamilyInstance(path, symbol, view)
    else:
        instance = doc.Create.NewFamilyInstance(center, symbol, view)
    doc.Regenerate()
    # Family insertion origins can be asymmetric. Align displayed extents, not origins.
    offset = center.Subtract(detail_center(instance))
    if offset.GetLength() > EPS:
        DB.ElementTransformUtils.MoveElement(doc, instance.Id, offset)
        doc.Regenerate()
    if center.DistanceTo(detail_center(instance)) > EPS * 10:
        raise ValueError('Revit could not align the detail center with the framing center.')
    return instance.Id


class ComponentFilter(ISelectionFilter):
    def AllowElement(self, element):
        return id_text(element.Id) in visible_ids

    def AllowReference(self, reference, position):
        return False


if doc is None or view is None:
    stop('Open a Revit project first.')
if doc.IsFamilyDocument or view.IsTemplate:
    stop('Open a project plan or section view.')
is_plan = view.ViewType in (DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan)
if not is_plan and view.ViewType != DB.ViewType.Section:
    stop('Open a floor plan, structural plan, or section view.')
if not is_plan and view.IsSplitSection():
    stop('Jogged sections use multiple cut planes. Use a straight section for tracing.')

normal = view.ViewDirection.Normalize()
# ViewPlan.Origin is not meaningful; its level supplies a stable annotation plane.
origin = (DB.XYZ(0, 0, view.GenLevel.ProjectElevation) if is_plan else view.Origin)

crop_solid = None
try:
    if view.CropBoxActive:
        manager = view.GetCropRegionShapeManager()
        if manager.NumberOfSplitRegions > 1:
            stop('Split crops are unsupported. Use an unsplit view for tracing.')
        crop_solid = extrude(project_loops(manager.GetCropShape()))
except Exception as error:
    stop('Could not read the view crop:\n\n{}'.format(error))

elements = []
for category_name, category in CATEGORIES:
    elements.extend(list(DB.FilteredElementCollector(doc, view.Id).OfCategory(category)
                         .WhereElementIsNotElementType()))
if not elements:
    stop('No host-model floors, walls, roofs, structural foundations, or structural framing were found in this view.')
visible_ids = set(id_text(element.Id) for element in elements)
mode = NdevModeSelector.show(
    ['All supported elements in this view', 'Pick elements in this view'],
    title=TITLE, message='Choose components to trace')
if not mode:
    script.exit()
if mode == 'Pick elements in this view':
    try:
        references = uidoc.Selection.PickObjects(
            ObjectType.Element, ComponentFilter(),
            'Select floors, walls, roofs, structural foundations, or structural framing, then click Finish')
    except OperationCanceledException:
        script.exit()
    unique = {}
    for reference in references:
        unique[id_text(reference.ElementId)] = doc.GetElement(reference.ElementId)
    elements = list(unique.values())
if not elements:
    script.exit()

groups = {}
for element in elements:
    key = mapping_key(element)
    if key not in groups:
        groups[key] = {'name': type_label(element), 'elements': [], 'cmu': is_cmu(element)}
    groups[key]['elements'].append(element)

region_types = {}
region_names = {}
for region_type in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
    parameter = region_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    name = parameter.AsString() if parameter else 'Filled Region'
    label = '{} [ID {}]'.format(name, id_text(region_type.Id))
    region_types[label] = region_type.Id
    region_names[label] = name
region_choices = sorted(region_types, key=lambda label: region_sort_key(region_names[label]))
line_types = {}
for style_id in DB.FilledRegion.GetValidLineStyleIdsForFilledRegion(doc):
    style = doc.GetElement(style_id)
    line_types['{} [ID {}]'.format(style.Name, id_text(style_id))] = style_id
repeat_types = {}
for element_type in DB.FilteredElementCollector(doc).OfClass(DB.ElementType):
    if element_type.get_Parameter(DB.BuiltInParameter.REPEATING_DETAIL_ELEMENT):
        parameter = element_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        name = parameter.AsString() if parameter else id_text(element_type.Id)
        repeat_types['{} [ID {}]'.format(name, id_text(element_type.Id))] = element_type.Id
repeat_templates = [item for item in DB.FilteredElementCollector(doc).OfClass(DB.CurveElement)
                    if item.CurveElementType == DB.CurveElementType.RepeatingDetail
                    and isinstance(item.GeometryCurve, DB.Line)]
detail_types = {}
floor_detail_types = {}
for symbol in (DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_DetailComponents)
               .OfClass(DB.FamilySymbol)):
    if symbol.Family.FamilyPlacementType in (DB.FamilyPlacementType.ViewBased,
                                           DB.FamilyPlacementType.CurveBasedDetail):
        parameter = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        name = parameter.AsString() if parameter else id_text(symbol.Id)
        label = '{} : {} [ID {}]'.format(symbol.FamilyName, name, id_text(symbol.Id))
        detail_types[label] = symbol.Id
        if symbol.Family.FamilyPlacementType == DB.FamilyPlacementType.CurveBasedDetail:
            floor_detail_types[label] = symbol.Id
settings = TraceSettings(groups, region_choices, sorted(line_types), sorted(repeat_types),
                         sorted(detail_types), sorted(floor_detail_types))
_ndev_show_localized_dialog(settings)
assignments = settings.result
if not assignments:
    script.exit()
if any(value['repeat'] for value in assignments.values()) and not repeat_templates:
    stop('Place one Repeating Detail Component manually in any plan, section, or drafting '
         'view in this project, then run Trace Elements again. It is used as a copy '
         'template; your original detail is not modified.')
included = [element for element in elements if mapping_key(element) in assignments]
excluded_count = len(elements) - len(included)

# Prepare outlines before opening a transaction. Report failed elements individually.
prepared = []
failures = []
with forms.ProgressBar(title='Tracing elements ({value} of {max_value})', cancellable=True) as progress:
    for index, element in enumerate(included):
        if progress.cancelled:
            script.exit()
        try:
            assignment = assignments[mapping_key(element)]
            boundaries = trace_element(element, crop_solid)
            paths = (repeating_paths(element, boundaries, assignment['direction'])
                     if assignment['repeat'] else
                     floor_detail_paths(boundaries) if assignment['detail'] and
                     category_key(element) == 'Floors' else
                     roof_detail_paths(element, crop_solid) if assignment['detail'] and
                     category_key(element) == 'Roofs' else [])
            prepared.append((element.Id, assignment, boundaries, paths))
        except Exception as error:
            failures.append((element.Id, 'Outline extraction: {}: {}'.format(
                type(error).__name__, error)))
        progress.update_progress(index + 1, len(included))

created_ids = List[DB.ElementId]()
created_elements = 0
created_regions = 0
created_lines = 0
created_repeats = 0
created_components = 0
if prepared:
    transaction = DB.Transaction(doc, 'Trace elements with filled regions')
    try:
        transaction.Start()
        for element_id, assignment, boundaries, paths in prepared:
            sub = DB.SubTransaction(doc)
            try:
                sub.Start()
                ids = []
                region_count = line_count = repeat_count = component_count = 0
                fill_id = region_types.get(assignment['fill'])
                line_id = line_types.get(assignment['line'])
                for loops in boundaries:
                    if fill_id is not None:
                        region = DB.FilledRegion.Create(doc, fill_id, view.Id, loops)
                        if line_id is not None:
                            region.SetLineStyleId(line_id)
                        ids.append(region.Id)
                        region_count += 1
                    elif line_id is not None:
                        for loop in loops:
                            for curve in loop:
                                detail_line = doc.Create.NewDetailCurve(view, curve)
                                detail_line.LineStyle = doc.GetElement(line_id)
                                ids.append(detail_line.Id)
                                line_count += 1
                if assignment['repeat']:
                    repeat_id = repeat_types[assignment['repeat']]
                    template = sorted(repeat_templates, key=lambda item: (
                        item.GetTypeId() != repeat_id, item.OwnerViewId != view.Id))[0]
                    for path in paths:
                        ids.append(place_repeating_detail(template, repeat_id, path))
                        repeat_count += 1
                if assignment['detail']:
                    if category_key(doc.GetElement(element_id)) in ('Floors', 'Roofs'):
                        floor_ids = place_linear_details(floor_detail_types[assignment['detail']], paths)
                        ids.extend(floor_ids)
                        component_count += len(floor_ids)
                    else:
                        ids.append(place_framing_detail(doc.GetElement(element_id),
                                   detail_types[assignment['detail']], boundaries))
                        component_count += 1
                if sub.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit did not commit the element regions.')
                for region_id in ids:
                    created_ids.Add(region_id)
                created_elements += 1
                created_regions += region_count
                created_lines += line_count
                created_repeats += repeat_count
                created_components += component_count
            except Exception as error:
                if sub.GetStatus() == DB.TransactionStatus.Started:
                    sub.RollBack()
                failures.append((element_id, 'Detail creation: {}: {}'.format(
                    type(error).__name__, error)))
        if transaction.Commit() != DB.TransactionStatus.Committed:
            stop('Revit did not commit the transaction. No created regions were confirmed.')
    except Exception as error:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        stop('Could not create filled regions:\n\n{}'.format(error))

if failures:
    output = script.get_output()
    output.print_md('### Elements not traced')
    for element_id, reason in failures:
        output.print_html('<p>Element {}</p>'.format(output.linkify(element_id)))
        print(reason)
if created_ids.Count:
    uidoc.Selection.SetElementIds(created_ids)
failure_details = ''
if failures:
    failure_details = '\n\nReasons:\n' + '\n\n'.join(
        'Element {}: {}'.format(id_text(element_id), reason)
        for element_id, reason in failures[:3])
    if len(failures) > 3:
        failure_details += '\n\nMore details are in the output window.'
_ndev_alert('Traced {} element(s).\nCreated {} filled region(s), {} detail line(s), '
            '{} repeating-detail run(s), and {} floor/roof/framing detail component(s).\n'
            'Excluded by None: {}. Failed: {}.{}\n\n'
            'Details are static copies; running again creates additional details.'.format(
                created_elements, created_regions, created_lines, created_repeats, created_components,
                excluded_count, len(failures), failure_details), title=TITLE)
