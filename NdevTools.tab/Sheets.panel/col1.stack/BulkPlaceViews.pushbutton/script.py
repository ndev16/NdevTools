# -*- coding: utf-8 -*-
from pyrevit import revit, DB, forms, script
from System.Collections.Generic import List
import json
import random
import System
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import Window, WindowStyle, WindowState, ResizeMode, Thickness, CornerRadius, WindowStartupLocation, TextWrapping, FontWeights, VerticalAlignment, HorizontalAlignment, TextTrimming
from System.Windows.Controls import DockPanel, Dock, Grid, ColumnDefinition, StackPanel, Border, Button, TextBlock, ScrollViewer, Orientation, ComboBox, Expander, ScrollBarVisibility, Canvas, ProgressBar
from System.Windows import GridLength, GridUnitType, Duration
from System.Windows.Media import Color, SolidColorBrush, Brushes, TranslateTransform, FontFamily
from System.Windows.Media.Animation import DoubleAnimation, RepeatBehavior
from System.Windows.Shell import WindowChrome
from System.Windows.Threading import Dispatcher, DispatcherFrame, DispatcherPriority

NDEV_TOOL_TITLE = 'Ndev Tools - SheetPilot'
NDEV_GITHUB_URL = 'https://github.com/ndev16'
NDEV_LINKEDIN_URL = 'https://www.linkedin.com/in/nataraj016/'


def ndev_window_title(title=None):
    """Add Ndev Tools once and keep the original dialog title."""
    if not title:
        return NDEV_TOOL_TITLE
    result = str(title).replace('\r', '').replace('\n\n', ' - ').replace('\n', ' ')
    if result.lower().startswith('ndev tools'):
        return result
    return 'Ndev Tools - ' + result


def ndev_attach_titlebar(window, include_help=True):
    """Add a true custom caption row, including a black window border.

    Preserve window.Content, original pyRevit selectors, event handlers,
    checkbox selection behavior and window sizing. Only the visual frame
    and title bar are changed.
    """
    original = window.Content
    if original is None:
        return
    window.Title = ndev_window_title(window.Title)
    navy = SolidColorBrush(Color.FromRgb(28, 42, 61))
    cyan = SolidColorBrush(Color.FromRgb(0, 165, 194))
    bar = Border()
    bar.Height = 38
    bar.Background = navy
    header = Grid()
    header.ColumnDefinitions.Add(ColumnDefinition())
    actions_column = ColumnDefinition()
    actions_column.Width = System.Windows.GridLength.Auto
    header.ColumnDefinitions.Add(actions_column)
    caption = TextBlock()
    caption.Text = window.Title
    caption.Foreground = Brushes.White
    caption.FontWeight = FontWeights.SemiBold
    caption.VerticalAlignment = VerticalAlignment.Center
    caption.TextTrimming = TextTrimming.CharacterEllipsis
    caption.Margin = Thickness(12, 0, 8, 0)
    Grid.SetColumn(caption, 0)
    header.Children.Add(caption)
    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    Grid.SetColumn(actions, 1)
    header.Children.Add(actions)

    def add_action(text, width, hint, on_click, color=None):
        button = Button()
        button.Content = text
        button.Width = width
        button.Height = 30
        button.Margin = Thickness(2, 4, 2, 4)
        button.Padding = Thickness(4, 0, 4, 0)
        button.ToolTip = hint
        button.BorderThickness = Thickness(0)
        button.Foreground = Brushes.White
        button.Background = color if color is not None else navy
        button.Click += on_click
        actions.Children.Add(button)
        return button

    if include_help:
        add_action(
            '? Help', 78, 'Instructions, GitHub and LinkedIn',
            lambda sender, args: ndev_show_help(window), cyan
        )

    add_action(
        '-', 40, 'Minimize',
        lambda sender, args: setattr(
            window, 'WindowState', WindowState.Minimized
        )
    )

    def maximize_or_restore(sender, args):
        if window.WindowState == WindowState.Maximized:
            window.WindowState = WindowState.Normal
        else:
            window.WindowState = WindowState.Maximized

    add_action('[]', 40, 'Maximize / Restore', maximize_or_restore)
    add_action('X', 40, 'Close', lambda sender, args: window.Close())

    def move_window(sender, args):
        if actions.IsMouseOver:
            return
        if args.ClickCount == 2:
            maximize_or_restore(None, None)
            args.Handled = True
        else:
            try:
                window.DragMove()
            except Exception:
                pass

    bar.Child = header
    bar.MouseLeftButtonDown += move_window
    window.Content = None
    root = DockPanel()
    root.LastChildFill = True
    DockPanel.SetDock(bar, Dock.Top)
    root.Children.Add(bar)
    root.Children.Add(original)
    frame = Border()
    frame.BorderBrush = Brushes.Black
    frame.BorderThickness = Thickness(2)
    frame.SnapsToDevicePixels = True
    frame.Child = root
    window.Content = frame
    window.WindowStyle = getattr(WindowStyle, 'None')
    chrome = WindowChrome()
    chrome.CaptionHeight = 0.0
    chrome.ResizeBorderThickness = Thickness(6)
    chrome.GlassFrameThickness = Thickness(0)
    chrome.CornerRadius = CornerRadius(0)
    WindowChrome.SetWindowChrome(window, chrome)
    try:
        window.Height += 38
    except Exception:
        pass


def ndev_open_link(url):
    """Open the profile with the Windows default browser."""
    try:
        start_info = ProcessStartInfo(url)
        start_info.UseShellExecute = True
        Process.Start(start_info)
    except Exception as error:
        ndev_alert(
            'Unable to open the browser.\n\n{}\n\n{}'.format(url, error),
            title='Help - Browser'
        )


def ndev_show_help(owner=None):
    """Show usage notes and the two public Ndev Tools profile links."""
    window = Window()
    window.Title = NDEV_TOOL_TITLE + ' - Help'
    window.Width = 560
    window.Height = 465
    window.MinWidth = 450
    window.ResizeMode = ResizeMode.NoResize
    window.ShowInTaskbar = False
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen

    if owner is not None:
        window.Owner = owner
        window.WindowStartupLocation = WindowStartupLocation.CenterOwner

    panel = StackPanel()
    panel.Margin = Thickness(20)
    heading = TextBlock()
    heading.Text = 'NDEV TOOLS | SHEETPILOT'
    heading.FontWeight = FontWeights.Bold
    heading.Margin = Thickness(0, 0, 0, 12)
    panel.Children.Add(heading)
    instructions = TextBlock()
    instructions.Text = (
        '1. Save positions with Viewport Position Manager (or Crop Manager).\n'
        '2. Open this window to see all existing sheets.\n'
        '3. Expand a sheet and click + Add View (up to 25 per sheet).\n'
        '4. Select View, Viewport Type and Saved Position in each row.\n'
        '5. Configure any number of sheets in the same window.\n'
        '6. Click Place All Views once; each view completes separately.\n\n'
        'Two-stage: create each viewport at a temporary sheet location '
        'and commit, then move the existing viewport to saved X/Y. '
        'V8 temporarily hides Model, Annotation, Import, Analytical groups '
        'and Revit links while MOVING, then restores original visibility '
        'and the view template. No movement after restoration. '
        '3D views, drafting views, legends, and schedules bypass V8. '
        'Schedules use saved X/Y as their insertion point. '
        'Each view is rollback-safe. One funny flight-status message '
        'appears per sheet while views are placed.\n\n'
        'Compatible with Revit 2022-2027.'
    )
    instructions.TextWrapping = TextWrapping.Wrap
    instructions.Margin = Thickness(0, 0, 0, 14)
    panel.Children.Add(instructions)
    github = Button()
    github.Content = 'GitHub  |  github.com/ndev16'
    github.Height = 34
    github.Margin = Thickness(0, 0, 0, 9)
    github.Click += lambda sender, args: ndev_open_link(NDEV_GITHUB_URL)
    panel.Children.Add(github)
    linkedin = Button()
    linkedin.Content = 'LinkedIn  |  linkedin.com/in/nataraj016'
    linkedin.Height = 34
    linkedin.Click += lambda sender, args: ndev_open_link(NDEV_LINKEDIN_URL)
    panel.Children.Add(linkedin)
    scrolling = ScrollViewer()
    scrolling.Content = panel
    window.Content = scrolling
    ndev_attach_titlebar(window, include_help=False)
    window.ShowDialog()


class NdevSelectFromList(forms.SelectFromList):
    """Original pyRevit SelectFromList with Ndev Tools title-bar Help."""

    def _setup(self, **kwargs):
        forms.SelectFromList._setup(self, **kwargs)
        ndev_attach_titlebar(self)


def ndev_alert(message, title=None, yes=False, no=False,
               exitscript=False, flight=False, **kwargs):
    """Branded alert. `flight` changes only UI, never model transactions."""
    window = Window()
    window.Title = ndev_window_title(title)
    window.Width = 640 if flight else 600
    lines = len(str(message).splitlines())
    window.Height = (430 if flight else min(690, max(255, 170 + 18 * lines)))
    window.MinWidth = 440
    window.MinHeight = 220
    window.ResizeMode = ResizeMode.CanResize
    window.ShowInTaskbar = False
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    content = DockPanel()
    content.Margin = Thickness(16)
    if flight:
        window.Background = SolidColorBrush(Color.FromRgb(17, 27, 41))
    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    actions.HorizontalAlignment = HorizontalAlignment.Right
    actions.Margin = Thickness(0, 12, 0, 0)
    DockPanel.SetDock(actions, Dock.Bottom)
    content.Children.Add(actions)

    def make_choice(caption, result, default=False, cancel=False):
        button = Button()
        button.Content = caption
        button.Width = (152 if result else 108) if flight else 95
        button.Height = 36 if flight else 32
        button.Margin = Thickness(8, 0, 0, 0)
        button.IsDefault = default
        button.IsCancel = cancel
        if flight:
            button.Background = SolidColorBrush(Color.FromRgb(
                0, 165, 194) if result else Color.FromRgb(45, 62, 81))
            button.Foreground = Brushes.White
            button.FontWeight = FontWeights.SemiBold
            button.BorderThickness = Thickness(0)
        button.Click += lambda sender, args: setattr(
            window, 'DialogResult', result
        )
        actions.Children.Add(button)

    if yes and no:
        if flight:
            make_choice(u'\U0001F680  Let\'s Fly!', True, default=True)
            make_choice('Not Yet', False, cancel=True)
        else:
            make_choice('Yes', True, default=True)
            make_choice('No', False, cancel=True)
    else:
        make_choice('OK', True, default=True, cancel=True)

    if flight:
        # A decorative WPF animation only: the Revit document is untouched.
        runway = Canvas()
        runway.Height = 104
        runway.Background = SolidColorBrush(Color.FromRgb(28, 42, 61))
        runway.ClipToBounds = True
        runway.Margin = Thickness(0, 0, 0, 16)
        DockPanel.SetDock(runway, Dock.Top)

        sky_label = TextBlock()
        sky_label.Text = 'SHEETPILOT  |  FLIGHT CONTROL'
        sky_label.Foreground = SolidColorBrush(Color.FromRgb(97, 211, 232))
        sky_label.FontSize = 11
        sky_label.FontWeight = FontWeights.SemiBold
        Canvas.SetLeft(sky_label, 15)
        Canvas.SetTop(sky_label, 10)
        runway.Children.Add(sky_label)

        stars = TextBlock()
        stars.Text = u'\u2728                    \u2601               \u2726             \u2728'
        stars.Foreground = Brushes.White
        stars.FontSize = 17
        Canvas.SetLeft(stars, 22)
        Canvas.SetTop(stars, 49)
        runway.Children.Add(stars)

        rocket = TextBlock()
        rocket.Text = u'\U0001F680'
        rocket.FontFamily = FontFamily('Segoe UI Emoji')
        rocket.FontSize = 38
        rocket.RenderTransform = TranslateTransform()
        Canvas.SetLeft(rocket, 12)
        Canvas.SetTop(rocket, 36)
        runway.Children.Add(rocket)
        content.Children.Add(runway)

        def fly_rocket(sender, args):
            try:
                animation = DoubleAnimation()
                animation.From = 0.0
                # Keep the rocket within the runway on small windows.
                animation.To = max(0.0, runway.ActualWidth - 95.0)
                animation.Duration = Duration(System.TimeSpan.FromSeconds(3.0))
                animation.AutoReverse = True
                animation.RepeatBehavior = RepeatBehavior.Forever
                rocket.RenderTransform.BeginAnimation(
                    TranslateTransform.XProperty, animation
                )
            except Exception:
                # Unicode/font/animation availability must never block work.
                pass
        runway.Loaded += fly_rocket

    scroll = ScrollViewer()
    content_text = TextBlock()
    content_text.Text = str(message)
    content_text.TextWrapping = TextWrapping.Wrap
    if flight:
        content_text.FontSize = 14
        content_text.Foreground = Brushes.White
    scroll.Content = content_text
    content.Children.Add(scroll)
    window.Content = content
    ndev_attach_titlebar(window)
    answer = window.ShowDialog()

    if exitscript:
        script.exit()
    if yes and no:
        return answer is True
    return answer


doc = revit.doc
REVIT_VERSION = str(doc.Application.VersionNumber)
SUPPORTED_VERSIONS = ['2022', '2023', '2024', '2025', '2026', '2027']
VIEWPORT_POSITION_CONFIG = 'NDEV_VIEWPORT_POSITION_MANAGER_{}'.format(
    REVIT_VERSION
)
CROP_POSITION_CONFIG = 'NDEV_CROP_POSITION_MANAGER_{}'.format(
    REVIT_VERSION
)
POSITIONS_KEY = 'positions_json'


def id_value(element_id):
    try:
        return element_id.IntegerValue
    except:
        try:
            return element_id.Value
        except:
            return str(element_id)


def get_config_value(cfg, option_name, default_value):
    try:
        value = getattr(cfg, option_name)
        if value is not None:
            return value
    except:
        pass

    try:
        value = cfg.get_option(option_name, default_value)
        if value is not None:
            return value
    except:
        pass

    return default_value


def normalize_position(position, fallback_name):
    if not isinstance(position, dict):
        return None

    name = position.get('name', fallback_name)
    x_value = None
    for key in ['x', 'X', 'pos_x', 'sheet_x']:
        if key in position:
            x_value = position[key]
            break

    y_value = None
    for key in ['y', 'Y', 'pos_y', 'sheet_y']:
        if key in position:
            y_value = position[key]
            break

    if x_value is None or y_value is None:
        return None

    try:
        x_value = float(x_value)
        y_value = float(y_value)
    except:
        return None

    result = dict(position)
    result['name'] = str(name)
    result['x'] = x_value
    result['y'] = y_value
    return result


def parse_position_data(raw_data):
    data = raw_data
    if isinstance(raw_data, basestring):
        try:
            data = json.loads(raw_data)
        except:
            return []

    result = []

    if isinstance(data, list):
        for index, item in enumerate(data):
            position = normalize_position(
                item, 'Position {}'.format(index + 1)
            )
            if position:
                result.append(position)
        return result

    if isinstance(data, dict):
        for key in data:
            value = data[key]

            if isinstance(value, dict):
                temp = dict(value)
                if 'name' not in temp:
                    temp['name'] = str(key)
                position = normalize_position(temp, str(key))
                if position:
                    result.append(position)

            elif isinstance(value, (list, tuple)):
                if len(value) >= 2:
                    try:
                        result.append({
                            'name': str(key),
                            'x': float(value[0]),
                            'y': float(value[1])
                        })
                    except:
                        pass

        return result

    return []


def load_positions_from_config(config_section):
    try:
        cfg = script.get_config(config_section)
    except:
        return []

    raw_data = get_config_value(cfg, POSITIONS_KEY, '[]')
    return parse_position_data(raw_data)


def load_saved_positions():
    positions = load_positions_from_config(VIEWPORT_POSITION_CONFIG)
    if positions:
        return positions

    positions = load_positions_from_config(CROP_POSITION_CONFIG)
    return positions


def get_view_type_name(view):
    try:
        return view.ViewType.ToString()
    except:
        try:
            return str(view.ViewType)
        except:
            return 'View'


def is_schedule_view(view):
    """Schedule views use ScheduleSheetInstance instead of Viewport."""
    try:
        return (
            isinstance(view, DB.ViewSchedule)
            and get_view_type_name(view) == 'Schedule'
        )
    except Exception:
        return False


# These four plan types always use the full V8 hide/place/restore path.
# Revit's internal ViewType names differ from the names in the View UI.
STRICT_V8_PLAN_TYPES = (
    'FloorPlan',       # Floor Plan
    'CeilingPlan',     # Reflected Ceiling Plan
    'EngineeringPlan', # Structural Plan
    'AreaPlan'         # Area Plan
)


def is_strict_v8_plan(view):
    return get_view_type_name(view) in STRICT_V8_PLAN_TYPES


def bypass_v8_visibility(view):
    """Never bypass V8 for the four plan types. Preserve other exemptions."""
    if is_strict_v8_plan(view):
        return False
    return get_view_type_name(view) in (
        'ThreeD',
        'DraftingView',
        'Legend',
        'Schedule'
    )


def is_supported_view(view):
    if view is None:
        return False

    try:
        if view.IsTemplate:
            return False
    except:
        pass

    view_type_name = get_view_type_name(view)
    excluded_types = [
        'DrawingSheet',
        'ColumnSchedule',
        'PanelSchedule',
        'ProjectBrowser',
        'SystemBrowser',
        'Report',
        'CostReport',
        'LoadsReport',
        'Internal',
        'Undefined'
    ]

    if view_type_name in excluded_types:
        return False

    if is_schedule_view(view):
        try:
            if bool(view.IsTitleblockRevisionSchedule):
                return False
        except Exception:
            pass

        try:
            if bool(view.Definition.IsKeySchedule):
                return False
        except Exception:
            pass

    return True


def get_placed_view_ids():
    result = set()

    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    for viewport in viewports:
        try:
            result.add(id_value(viewport.ViewId))
        except:
            pass

    try:
        schedule_instances = (
            DB.FilteredElementCollector(doc)
            .OfClass(DB.ScheduleSheetInstance)
            .WhereElementIsNotElementType()
            .ToElements()
        )

        for instance in schedule_instances:
            try:
                result.add(id_value(instance.ScheduleId))
            except Exception:
                pass
    except Exception:
        pass

    return result


def get_unplaced_views():
    placed_ids = get_placed_view_ids()

    views = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.View)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    result = []

    for view in views:
        if not is_supported_view(view):
            continue

        try:
            view_id = id_value(view.Id)
        except:
            continue

        if view_id in placed_ids:
            continue

        result.append(view)

    return result


def view_display_name(view):
    view_type = get_view_type_name(view)
    scale_text = ''

    try:
        if view.Scale > 0:
            scale_text = ' | Scale 1:{}'.format(view.Scale)
    except:
        pass

    return '{} | {}{} | ID {}'.format(
        view.Name,
        view_type,
        scale_text,
        id_value(view.Id)
    )


def select_unplaced_views():
    views = get_unplaced_views()

    if not views:
        ndev_alert(
            'No unplaced views were found.\n\n'
            'All compatible views appear to already be placed on sheets.',
            title='SheetPilot'
        )
        return []

    try:
        views = sorted(views, key=lambda x: x.Name.lower())
    except:
        pass

    items = []
    lookup = {}

    for view in views:
        display = view_display_name(view)
        items.append(display)
        lookup[display] = view

    selected = NdevSelectFromList.show(
        items,
        title='Select Unplaced Views',
        button_name='Select Views',
        multiselect=True
    )

    if not selected:
        return []

    return [lookup[item] for item in selected]


def get_sheets():
    sheets = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    result = []

    for sheet in sheets:
        try:
            if sheet.IsPlaceholder:
                continue
        except:
            pass

        result.append(sheet)

    return result


def select_target_sheet():
    sheets = get_sheets()

    if not sheets:
        ndev_alert('No sheets were found.', title='SheetPilot')
        return None

    try:
        sheets = sorted(
            sheets,
            key=lambda x: x.SheetNumber.lower()
        )
    except:
        pass

    items = []
    lookup = {}

    for sheet in sheets:
        display = '{} | {} | ID {}'.format(
            sheet.SheetNumber,
            sheet.Name,
            id_value(sheet.Id)
        )
        items.append(display)
        lookup[display] = sheet

    selected = NdevSelectFromList.show(
        items,
        title='Select Target Sheet',
        button_name='Select Sheet',
        multiselect=False
    )

    if not selected:
        return None

    return lookup[selected]


def get_element_type_name(element_type):
    try:
        value = element_type.Name
        if value:
            return value
    except:
        pass

    try:
        parameter = element_type.get_Parameter(
            DB.BuiltInParameter.SYMBOL_NAME_PARAM
        )
        if parameter:
            value = parameter.AsString()
            if value:
                return value
    except:
        pass

    try:
        parameter = element_type.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
        )
        if parameter:
            value = parameter.AsString()
            if value:
                return value
    except:
        pass

    return 'Viewport Type {}'.format(
        id_value(element_type.Id)
    )


def get_viewport_family_name(element_type):
    try:
        family_name = element_type.FamilyName
        if family_name:
            return family_name
    except:
        pass

    try:
        parameter = element_type.get_Parameter(
            DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME
        )
        if parameter:
            value = parameter.AsString()
            if value:
                return value
    except:
        pass

    return 'Viewport'


def add_viewport_type(result, seen_ids, element_type):
    if element_type is None:
        return

    try:
        type_id = id_value(element_type.Id)
    except:
        return

    if type_id in seen_ids:
        return

    seen_ids.add(type_id)
    result.append(element_type)


def get_viewport_types():
    result = []
    seen_ids = set()

    viewports = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    for viewport in viewports:
        try:
            valid_type_ids = viewport.GetValidTypes()

            for type_id in valid_type_ids:
                element_type = doc.GetElement(type_id)
                add_viewport_type(
                    result, seen_ids, element_type
                )
        except:
            pass

    for viewport in viewports:
        try:
            element_type = doc.GetElement(
                viewport.GetTypeId()
            )
            add_viewport_type(
                result, seen_ids, element_type
            )
        except:
            pass

    try:
        viewport_category = DB.Category.GetCategory(
            doc, DB.BuiltInCategory.OST_Viewports
        )

        if viewport_category:
            viewport_category_id = id_value(
                viewport_category.Id
            )
            element_types = (
                DB.FilteredElementCollector(doc)
                .WhereElementIsElementType()
                .ToElements()
            )

            for element_type in element_types:
                try:
                    category = element_type.Category
                    if category is None:
                        continue

                    if id_value(category.Id) != viewport_category_id:
                        continue

                    add_viewport_type(
                        result,
                        seen_ids,
                        element_type
                    )
                except:
                    pass
    except:
        pass

    try:
        result = sorted(
            result,
            key=lambda x: get_element_type_name(x).lower()
        )
    except:
        pass

    return result


def select_viewport_type():
    viewport_types = get_viewport_types()

    if not viewport_types:
        ndev_alert(
            'No viewport types could be found.\n\n'
            'Make sure the project contains at least one '
            'normal viewport on a sheet.',
            title='SheetPilot'
        )
        return None

    items = []
    lookup = {}

    for viewport_type in viewport_types:
        family_name = get_viewport_family_name(viewport_type)
        type_name = get_element_type_name(viewport_type)

        display = '{} : {} | ID {}'.format(
            family_name,
            type_name,
            id_value(viewport_type.Id)
        )

        if display in lookup:
            display = '{} | {}'.format(
                display,
                id_value(viewport_type.Id)
            )

        items.append(display)
        lookup[display] = viewport_type

    items.sort()

    selected = NdevSelectFromList.show(
        items,
        title='Select Viewport Type',
        button_name='Use Viewport Type',
        multiselect=False
    )

    if not selected:
        return None

    return lookup[selected]


def can_place_view(sheet, view):
    if is_schedule_view(view):
        return is_supported_view(view)

    try:
        return DB.Viewport.CanAddViewToSheet(
            doc,
            sheet.Id,
            view.Id
        )
    except:
        return False


def filter_placeable_views(views, sheet):
    valid = []
    invalid = []

    for view in views:
        if can_place_view(sheet, view):
            valid.append(view)
        else:
            invalid.append(view)

    if invalid:
        message = (
            'These views cannot be placed on the selected sheet:\n\n'
        )

        for view in invalid:
            message += '- {}\n'.format(view.Name)

        if valid:
            message += (
                '\n{} other view(s) can still be placed.'
            ).format(len(valid))

        ndev_alert(message, title='SheetPilot')

    return valid


def position_display_name(position, index):
    name = position.get(
        'name',
        'Position {}'.format(index + 1)
    )
    return '{} | X: {:.4f} | Y: {:.4f}'.format(
        name,
        position['x'],
        position['y']
    )


def choose_position(available_positions, view):
    items = []
    lookup = {}

    for index, position in enumerate(available_positions):
        display = position_display_name(position, index)
        unique_display = '{} | #{}'.format(
            display,
            index + 1
        )
        items.append(unique_display)
        lookup[unique_display] = position

    selected = NdevSelectFromList.show(
        items,
        title='Select Saved Position\n\nView: {}'.format(view.Name),
        button_name='Use Position',
        multiselect=False
    )

    if not selected:
        return None

    return lookup[selected]


def assign_positions(views, saved_positions):
    """Legacy selector: saved positions are REUSABLE, as in the batch UI."""
    assignments = []
    for view in views:
        position = choose_position(saved_positions, view)
        if position is None:
            return []
        assignments.append((view, position))
    return assignments


_VG_CLASS_FLAGS = (
    'AreModelCategoriesHidden',
    'AreAnnotationCategoriesHidden',
    'AreAnalyticalModelCategoriesHidden',
    'AreImportCategoriesHidden'
)


def _all_vg_categories():
    """Enumerate model, annotation, analytical, import and subcategories."""
    result = []
    seen = set()

    def visit(category):
        if category is None:
            return

        try:
            key = id_value(category.Id)
        except Exception:
            return

        if key in seen:
            return

        seen.add(key)
        result.append(category)

        try:
            for subcategory in category.SubCategories:
                visit(subcategory)
        except Exception:
            pass

    for category in doc.Settings.Categories:
        visit(category)

    try:
        for imported in (
            DB.FilteredElementCollector(doc)
            .OfClass(DB.ImportInstance)
            .WhereElementIsNotElementType()
            .ToElements()
        ):
            visit(imported.Category)
    except Exception:
        pass

    try:
        visit(
            DB.Category.GetCategory(
                doc,
                DB.BuiltInCategory.OST_RvtLinks
            )
        )
    except Exception:
        pass

    return result


_V8_VISIBILITY_FLAGS = (
    'AreModelCategoriesHidden',
    'AreAnnotationCategoriesHidden',
    'AreImportCategoriesHidden',
    'AreAnalyticalModelCategoriesHidden'
)


def _v8_link_instances():
    return list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.RevitLinkInstance)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def _v8_one_element_id(element_id):
    ids = List[DB.ElementId]()
    ids.Add(element_id)
    return ids


def _v8_hide_each_category(view, state):
    """Temporarily hide individual V/G categories on the four plan types.

    Category-group flags alone do not represent every visibility override.
    Save ONLY categories changed by this tool; pre-hidden ones remain hidden.
    Legacy helper, intentionally NOT used in the two-stage placement path. A failed required category operation aborts and
    rolls back the complete view placement.
    """
    for category in _all_vg_categories():
        category_id = category.Id
        try:
            if not view.CanCategoryBeHidden(category_id):
                continue
        except Exception:
            # Revit does not expose a hide capability for all categories.
            continue

        try:
            was_hidden = bool(view.GetCategoryHidden(category_id))
        except Exception as error:
            raise Exception(
                'Cannot read V/G category {}: {}'.format(
                    str(category.Name), error
                )
            )

        if was_hidden:
            continue

        try:
            view.SetCategoryHidden(category_id, True)
            if not bool(view.GetCategoryHidden(category_id)):
                raise Exception('Revit did not hide the category')
            state['category_ids_newly_hidden'].append(category_id)
        except Exception as error:
            raise Exception(
                'Cannot temporarily hide V/G category {}: {}'.format(
                    str(category.Name), error
                )
            )


def save_and_hide_view_for_placement(view):
    """V8 transaction 1: snapshot, detach template, hide, then regenerate.

    Hide the same four category GROUPS and Revit links as the working
    Viewport Position Manager. A failure rolls back the complete view.
    """
    state = {
        'template_id': view.ViewTemplateId,
        'class_flags': {},
        'category_ids_newly_hidden': [],
        'link_ids_newly_hidden': [],
        'link_strategy': None
    }

    for flag in _V8_VISIBILITY_FLAGS:
        try:
            state['class_flags'][flag] = bool(getattr(view, flag))
        except Exception as error:
            raise Exception(
                'Cannot capture original visibility {}: {}'.format(flag, error)
            )

    links = _v8_link_instances()
    to_hide = []
    for link in links:
        try:
            if not bool(link.IsHidden(view)):
                to_hide.append(link)
        except Exception as error:
            raise Exception(
                'Cannot read Revit link {} visibility: {}'.format(
                    id_value(link.Id), error
                )
            )

    if state['template_id'] != DB.ElementId.InvalidElementId:
        view.ViewTemplateId = DB.ElementId.InvalidElementId
        if view.ViewTemplateId != DB.ElementId.InvalidElementId:
            raise Exception('Unable to detach original view template.')
        doc.Regenerate()

    # The working manager does not separately hide every subcategory.
    for flag in _V8_VISIBILITY_FLAGS:
        try:
            setattr(view, flag, True)
            if not bool(getattr(view, flag)):
                raise Exception('Revit left category group visible')
        except Exception as error:
            raise Exception('Cannot hide {}: {}'.format(flag, error))

    doc.Regenerate()
    state['link_strategy'] = 'element' if to_hide else 'none_needed'

    for link in to_hide:
        try:
            if not link.CanBeHidden(view):
                raise Exception('Revit does not allow hiding this link')
            view.HideElements(_v8_one_element_id(link.Id))
            if not bool(link.IsHidden(view)):
                raise Exception('Link remained visible')
            state['link_ids_newly_hidden'].append(link.Id)
        except Exception as error:
            raise Exception(
                'Cannot temporarily hide Revit link {}: {}'.format(
                    id_value(link.Id), error
                )
            )

    # Everything supported is hidden BEFORE any viewport gets created.
    doc.Regenerate()
    return state


def restore_view_after_placement(view, state):
    """V8 transaction 3: restore link/category/group overrides and template.

    The template is restored LAST. This routine does not move the viewport.
    Never realign the viewport after restoring template-controlled visibility.
    Any failure causes the outer transaction group to roll back both the
    placement and all temporary visibility changes.
    """
    for link_id in state['link_ids_newly_hidden']:
        try:
            link = doc.GetElement(link_id)
            if link is None:
                raise Exception('Link no longer exists')
            if bool(link.IsHidden(view)):
                view.UnhideElements(_v8_one_element_id(link_id))
            if bool(link.IsHidden(view)):
                raise Exception('Link remains hidden')
        except Exception as error:
            raise Exception(
                'Cannot restore Revit link {}: {}'.format(
                    id_value(link_id), error
                )
            )

    # Switch group visibility back before restoring per-category overrides.
    for flag in _V8_VISIBILITY_FLAGS:
        original = state['class_flags'][flag]
        try:
            setattr(view, flag, original)
            if bool(getattr(view, flag)) != original:
                raise Exception('Revit did not restore the original value')
        except Exception as error:
            raise Exception(
                'Cannot restore visibility group {}: {}'.format(flag, error)
            )

    for category_id in reversed(state['category_ids_newly_hidden']):
        try:
            view.SetCategoryHidden(category_id, False)
            if bool(view.GetCategoryHidden(category_id)):
                raise Exception('Category remains hidden')
        except Exception as error:
            raise Exception(
                'Cannot restore category {}: {}'.format(
                    id_value(category_id), error
                )
            )

    if view.ViewTemplateId != state['template_id']:
        view.ViewTemplateId = state['template_id']
    if view.ViewTemplateId != state['template_id']:
        raise Exception('Cannot restore original view template.')

    doc.Regenerate()
    # Template-controlled flags may differ from the temporarily detached
    # values; source view template is authoritative after re-application.
    # Confirm direct flags only when the original view had NO template.
    if state['template_id'] == DB.ElementId.InvalidElementId:
        for flag in _V8_VISIBILITY_FLAGS:
            if bool(getattr(view, flag)) != state['class_flags'][flag]:
                raise Exception('Original {} was not restored'.format(flag))


def _begin_transaction(name):
    tx = DB.Transaction(doc, name)

    if tx.Start() != DB.TransactionStatus.Started:
        raise Exception(
            'Could not start transaction: {}'.format(name)
        )

    return tx


def _finish_transaction(tx, stage):
    if tx.Commit() != DB.TransactionStatus.Committed:
        raise Exception(
            'Could not commit: {}'.format(stage)
        )


def _temporary_sheet_point(sheet):
    """Stable temporary position on the sheet, independent of saved X/Y.

    A deterministic center is preferable to a random point. It is ONLY for
    creation; the saved position is applied after the viewport is committed.
    """
    try:
        outline = sheet.Outline
        x = (float(outline.Min.U) + float(outline.Max.U)) / 2.0
        y = (float(outline.Min.V) + float(outline.Max.V)) / 2.0
        return DB.XYZ(x, y, 0.0)
    except Exception:
        return DB.XYZ(0.0, 0.0, 0.0)


def place_one_view(sheet, view, viewport_type, position):
    """FIRST STAGE: create and assign viewport type, but DO NOT align yet.

    Unlike the old SheetPilot, the source view remains fully visible during
    creation. A separate, committed transaction follows before applying X/Y.
    Schedules retain their native insertion-point placement (no Viewport).
    """
    if is_schedule_view(view):
        point = DB.XYZ(float(position['x']), float(position['y']), 0.0)
        instance = DB.ScheduleSheetInstance.Create(
            doc, sheet.Id, view.Id, point
        )
        if instance is None:
            raise Exception('ScheduleSheetInstance.Create returned None.')
        return instance

    viewport = DB.Viewport.Create(
        doc, sheet.Id, view.Id, _temporary_sheet_point(sheet)
    )
    if viewport is None:
        raise Exception('Viewport.Create returned None.')
    if viewport_type is None:
        raise Exception('A viewport type is required for this view.')
    try:
        if viewport.GetTypeId() != viewport_type.Id:
            viewport.ChangeTypeId(viewport_type.Id)
    except Exception as error:
        raise Exception('Unable to apply the selected viewport type: {}'.format(error))
    # Finish regeneration, but deliberately DO NOT position the new viewport.
    doc.Regenerate()
    return viewport


def _apply_position_like_viewport_manager(viewport, position):
    """SECOND STAGE: exact existing-viewport move from working Position Manager.

    Called in its own transaction, AFTER the viewport creation transaction has
    committed. If V8 is enabled, categories/links are already hidden.
    There is a single SetBoxCenter move; no reposition after V8 restoration.
    """
    was_pinned = bool(viewport.Pinned)
    if was_pinned:
        viewport.Pinned = False
    try:
        doc.Regenerate()
        current_center = viewport.GetBoxCenter()
        target_center = DB.XYZ(
            float(position['x']), float(position['y']), current_center.Z
        )
        viewport.SetBoxCenter(target_center)
    finally:
        if was_pinned:
            viewport.Pinned = True


def build_confirmation(sheet, viewport_type, assignments):
    message = (
        'SHEETPILOT\n\n'
        'TARGET SHEET:\n{} - {}\n\n'
        'VIEWPORT TYPE:\n{}\n\n'
        'VIEW / POSITION:\n'
    ).format(
        sheet.SheetNumber,
        sheet.Name,
        get_element_type_name(viewport_type)
    )

    for view, position in assignments:
        message += '\n{}  ->  {}'.format(
            view.Name,
            position.get('name', 'Saved Position')
        )

    message += '\n\nPlace {} view(s)?'.format(
        len(assignments)
    )

    return message


def process_views(sheet, viewport_type, assignments):
    """Two-stage placement matching the WORKING Viewport Position Manager.

    One self-contained TransactionGroup per view (rollback all on failure):
      1. CREATE viewport at temporary sheet center, commit transaction.
      2. Re-acquire its ElementId after that commit, as an EXISTING viewport.
      3. V8: hide four VG groups and Revit links, commit transaction.
      4. MOVE using the exact Position Manager SetBoxCenter step, commit.
      5. V8: restore original flags/links/template, commit; NEVER move again.

    3D, drafting, legend and schedule views bypass V8. Schedules keep their
    native insertion point. Each view finishes before the next one starts.
    """
    successful, failed = [], []
    for source_view, position in assignments:
        use_v8 = not bypass_v8_visibility(source_view)
        group = DB.TransactionGroup(
            doc, 'SheetPilot two-stage placement - {}'.format(source_view.Name)
        )
        group_active = False
        tx = None
        stage = 'Starting two-stage view placement'
        try:
            if group.Start() != DB.TransactionStatus.Started:
                raise Exception('Unable to start per-view rollback group')
            group_active = True

            # FIRST: create at a provisional coordinate with NORMAL visibility.
            stage = 'Creating viewport at temporary sheet position'
            tx = _begin_transaction('1 - Create viewport at temporary location')
            created = place_one_view(sheet, source_view, viewport_type, position)
            instance_id = created.Id
            _finish_transaction(tx, stage)
            tx = None

            # A committed viewport now exists. Refresh both elements before
            # applying the position (as the independent Position Manager does).
            created = None
            # Transaction.Commit() already regenerates the new viewport.
            # Do not call Document.Regenerate() with no open Transaction.
            existing = doc.GetElement(instance_id)
            view = doc.GetElement(source_view.Id)
            if existing is None or view is None:
                raise Exception('New viewport or source view not found after creation')

            if not is_schedule_view(view):
                if use_v8:
                    # Same FOUR CATEGORY-GROUP FLAGS + REVIT LINKS as the
                    # working Viewport Position Manager; do not additionally
                    # hide individual categories or subcategories.
                    stage = 'Hiding VG category groups and Revit links'
                    tx = _begin_transaction('2 - Hide VG before moving existing viewport')
                    state = save_and_hide_view_for_placement(view)
                    _finish_transaction(tx, stage)
                    tx = None

                # Move this already-created viewport in an independent tx.
                stage = 'Applying saved X/Y to existing viewport'
                tx = _begin_transaction('3 - Apply saved viewport position')
                _apply_position_like_viewport_manager(existing, position)
                _finish_transaction(tx, stage)
                tx = None

                if use_v8:
                    stage = 'Restoring original VG, links, and view template'
                    tx = _begin_transaction('4 - Restore original view graphics')
                    restore_view_after_placement(view, state)
                    # IMPORTANT: DO NOT SetBoxCenter or move after restoration.
                    _finish_transaction(tx, stage)
                    tx = None

            stage = 'Finishing this independent view cycle'
            if group.Assimilate() != DB.TransactionStatus.Committed:
                raise Exception('Unable to assimilate grouped transactions')
            group_active = False
            successful.append((
                source_view.Name, position.get('name', 'Saved Position')
            ))

        except Exception as error:
            if tx is not None:
                try:
                    if tx.GetStatus() == DB.TransactionStatus.Started:
                        tx.RollBack()
                except Exception:
                    pass
            if group_active:
                try:
                    if group.GetStatus() == DB.TransactionStatus.Started:
                        group.RollBack()
                except Exception as rollback_error:
                    error = Exception('{}; rollback failed: {}'.format(
                        error, rollback_error
                    ))
            failed.append((source_view.Name, '{}: {}'.format(stage, error)))

    return (successful, failed)


def show_results(sheet, successful, failed):
    message = (
        'PLACE VIEWS COMPLETE\n\n'
        'SHEET:\n{} - {}\n\n'
        'PLACED: {}\n'
        'FAILED / SKIPPED: {}'
    ).format(
        sheet.SheetNumber,
        sheet.Name,
        len(successful),
        len(failed)
    )

    if successful:
        message += '\n\nPLACED:\n'

        for view_name, position_name in successful:
            message += '\n{} -> {}'.format(
                view_name,
                position_name
            )

    if failed:
        message += '\n\nFAILED / SKIPPED:\n'

        for view_name, error in failed:
            message += '\n{}: {}'.format(
                view_name,
                error
            )

    ndev_alert(message, title='SheetPilot')


MAX_VIEWS_PER_SHEET = 25


def _ndev_brush(red, green, blue):
    return SolidColorBrush(
        Color.FromRgb(red, green, blue)
    )


_NDEV_BG = _ndev_brush(17, 27, 41)
_NDEV_NAVY = _ndev_brush(28, 42, 61)
_NDEV_PANEL = _ndev_brush(34, 49, 67)
_NDEV_CYAN = _ndev_brush(0, 165, 194)
_NDEV_MUTED = _ndev_brush(188, 208, 218)
_NDEV_LIGHT = _ndev_brush(242, 248, 251)


def _ndev_label(value, size=12, color=None, bold=False):
    label = TextBlock()
    label.Text = value
    label.FontSize = size
    label.Foreground = (
        color if color is not None else Brushes.White
    )
    label.VerticalAlignment = VerticalAlignment.Center
    label.TextTrimming = TextTrimming.CharacterEllipsis

    if bold:
        label.FontWeight = FontWeights.SemiBold

    return label


def _ndev_button(text, width, bg=None):
    button = Button()
    button.Content = text
    button.Width = width
    button.Height = 30
    button.Padding = Thickness(8, 0, 8, 0)
    button.Background = (
        bg if bg is not None else _NDEV_NAVY
    )
    button.Foreground = Brushes.White
    button.BorderThickness = Thickness(0)
    return button


def _ndev_column(width, star=True):
    col = ColumnDefinition()

    if star:
        col.Width = GridLength(
            width,
            GridUnitType.Star
        )
    else:
        col.Width = GridLength(width)

    return col


class MultiSheetPlacementWindow(Window):
    """Collect all sheet/view/type/position assignments before model changes."""

    def __init__(self, sheets, available_views,
                 viewport_types, positions):
        Window.__init__(self)
        self.Title = NDEV_TOOL_TITLE
        self.Width = 1150
        self.Height = 780
        self.MinWidth = 800
        self.MinHeight = 500
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.Background = _NDEV_BG
        self.sheets = sheets
        self.available_views = available_views
        self.viewport_types = viewport_types
        self.positions = positions
        self.sections = []
        self.result_assignments = None
        self._build_window()
        ndev_attach_titlebar(self)

    def _build_window(self):
        root = DockPanel()
        root.Background = _NDEV_BG
        root.Margin = Thickness(17, 12, 17, 15)
        root.LastChildFill = True
        heading = StackPanel()
        heading.Margin = Thickness(0, 0, 0, 12)

        heading.Children.Add(
            _ndev_label(
                'SHEETPILOT | MULTI-SHEET VIEW PLACEMENT',
                19,
                _NDEV_LIGHT,
                True
            )
        )

        heading.Children.Add(
            _ndev_label(
                'Expand any sheet, click + Add View, '
                'and configure up to 25 views per sheet.',
                12,
                _NDEV_MUTED
            )
        )

        DockPanel.SetDock(heading, Dock.Top)
        root.Children.Add(heading)
        bottom = DockPanel()
        bottom.LastChildFill = True
        bottom.Margin = Thickness(0, 12, 0, 0)
        bottom.Height = 44
        DockPanel.SetDock(bottom, Dock.Bottom)
        root.Children.Add(bottom)
        actions = StackPanel()
        actions.Orientation = Orientation.Horizontal
        actions.HorizontalAlignment = HorizontalAlignment.Right
        DockPanel.SetDock(actions, Dock.Right)
        bottom.Children.Add(actions)
        cancel = _ndev_button(
            'Cancel', 100, _NDEV_NAVY
        )
        cancel.Margin = Thickness(0, 3, 10, 3)
        cancel.Click += self._cancel_clicked
        actions.Children.Add(cancel)
        self.place_button = _ndev_button(
            'PLACE ALL VIEWS', 184, _NDEV_CYAN
        )
        self.place_button.Height = 37
        self.place_button.Margin = Thickness(0, 0, 2, 0)
        self.place_button.Click += self._place_clicked
        actions.Children.Add(self.place_button)
        self.counter_label = _ndev_label(
            '', 13, _NDEV_MUTED, True
        )
        self.counter_label.Margin = Thickness(3, 0, 12, 0)
        bottom.Children.Add(self.counter_label)
        scroll = ScrollViewer()
        scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
        scroll.Background = _NDEV_BG
        root.Children.Add(scroll)
        self.sheet_stack = StackPanel()
        self.sheet_stack.Orientation = Orientation.Vertical
        scroll.Content = self.sheet_stack

        for index, sheet in enumerate(self.sheets):
            self._make_sheet_section(
                sheet,
                index == 0
            )

        self._update_counts()
        self.Content = root

    def _make_sheet_section(self, sheet, expanded):
        expander = Expander()
        expander.IsExpanded = expanded
        expander.Foreground = Brushes.White
        expander.Background = _NDEV_PANEL
        expander.Margin = Thickness(3, 2, 7, 10)
        expander.Padding = Thickness(10, 8, 10, 8)
        header_label = _ndev_label(
            '', 14, _NDEV_LIGHT, True
        )
        header_label.Margin = Thickness(4, 2, 0, 2)
        expander.Header = header_label
        body = StackPanel()
        body.Margin = Thickness(8, 12, 8, 7)
        expander.Content = body
        body.Children.Add(self._make_table_header())
        rows_panel = StackPanel()
        rows_panel.Margin = Thickness(0, 3, 0, 6)
        body.Children.Add(rows_panel)
        add_button = _ndev_button(
            '+ Add View',
            118,
            _NDEV_CYAN
        )
        add_button.HorizontalAlignment = HorizontalAlignment.Left
        add_button.Margin = Thickness(4, 6, 0, 2)
        body.Children.Add(add_button)

        section = {
            'sheet': sheet,
            'expander': expander,
            'header': header_label,
            'rows_panel': rows_panel,
            'add_button': add_button,
            'rows': []
        }

        add_button.Click += (
            lambda sender, args, section=section:
            self._add_row(section)
        )

        self.sections.append(section)
        self.sheet_stack.Children.Add(expander)

    def _make_table_header(self):
        grid = self._make_row_grid()
        headings = [
            ('VIEW', 0),
            ('VIEWPORT TYPE', 1),
            ('SAVED POSITION', 2)
        ]

        for value, column in headings:
            label = _ndev_label(
                value,
                11,
                _NDEV_MUTED,
                True
            )
            label.Margin = Thickness(5, 2, 5, 5)
            Grid.SetColumn(label, column)
            grid.Children.Add(label)

        return grid

    def _make_row_grid(self):
        grid = Grid()
        grid.ColumnDefinitions.Add(
            _ndev_column(5, True)
        )
        grid.ColumnDefinitions.Add(
            _ndev_column(3, True)
        )
        grid.ColumnDefinitions.Add(
            _ndev_column(3, True)
        )
        grid.ColumnDefinitions.Add(
            _ndev_column(42, False)
        )
        return grid

    def _make_combo(self, labels, placeholder, searchable=False):
        combo = ComboBox()
        combo.Height = 31
        combo.Margin = Thickness(4, 3, 4, 3)
        combo.Background = _NDEV_LIGHT
        combo.Foreground = Brushes.Black
        combo.IsEditable = bool(searchable)
        combo.IsTextSearchEnabled = True
        combo.MaxDropDownHeight = 400
        combo.Items.Add(placeholder)

        for item in labels:
            combo.Items.Add(item)

        combo.SelectedIndex = 0
        return combo

    def _add_row(self, section):
        if len(section['rows']) >= MAX_VIEWS_PER_SHEET:
            return

        row_grid = self._make_row_grid()
        row_grid.Margin = Thickness(0, 0, 0, 3)
        view_items = [
            view_display_name(v)
            for v in self.available_views
        ]
        type_items = [
            '{} : {} | ID {}'.format(
                get_viewport_family_name(vt),
                get_element_type_name(vt),
                id_value(vt.Id)
            )
            for vt in self.viewport_types
        ]
        pos_items = [
            '{} | #{}'.format(
                position_display_name(pos, index),
                index + 1
            )
            for index, pos in enumerate(self.positions)
        ]

        view_combo = self._make_combo(
            view_items,
            '-- Choose View --',
            True
        )
        type_combo = self._make_combo(
            type_items,
            '-- Choose Type --'
        )
        pos_combo = self._make_combo(
            pos_items,
            '-- Choose Position --'
        )

        for column, combo in enumerate(
            (view_combo, type_combo, pos_combo)
        ):
            Grid.SetColumn(combo, column)
            row_grid.Children.Add(combo)

        remove_button = _ndev_button(
            'X', 34, _NDEV_NAVY
        )
        remove_button.ToolTip = 'Remove this view from the sheet'
        remove_button.Margin = Thickness(4, 3, 2, 3)
        Grid.SetColumn(remove_button, 3)
        row_grid.Children.Add(remove_button)

        row = {
            'grid': row_grid,
            'view': view_combo,
            'type': type_combo,
            'position': pos_combo
        }

        def selected_view_changed(sender, args):
            v_index = view_combo.SelectedIndex - 1
            is_schedule = (
                0 <= v_index < len(self.available_views)
                and is_schedule_view(
                    self.available_views[v_index]
                )
            )

            type_combo.IsEnabled = not is_schedule
            type_combo.Items[0] = (
                '-- Not used for Schedule --'
                if is_schedule
                else '-- Choose Type --'
            )

            if is_schedule:
                type_combo.SelectedIndex = 0

        view_combo.SelectionChanged += selected_view_changed

        remove_button.Click += (
            lambda sender, args, section=section, row=row:
            self._remove_row(section, row)
        )

        section['rows'].append(row)
        section['rows_panel'].Children.Add(row_grid)
        section['expander'].IsExpanded = True
        self._update_counts()

    def _remove_row(self, section, row):
        if row in section['rows']:
            section['rows'].remove(row)
            section['rows_panel'].Children.Remove(
                row['grid']
            )

        self._update_counts()

    def _update_counts(self):
        sheets_with_rows = 0
        rows_count = 0

        for section in self.sections:
            count = len(section['rows'])
            rows_count += count

            if count:
                sheets_with_rows += 1

            sheet = section['sheet']

            section['header'].Text = (
                '{}  |  {}     ({} / {} views)'
            ).format(
                sheet.SheetNumber,
                sheet.Name,
                count,
                MAX_VIEWS_PER_SHEET
            )

            section['add_button'].IsEnabled = (
                count < MAX_VIEWS_PER_SHEET
            )

        self.counter_label.Text = (
            '{} sheets configured  |  '
            '{} views ready to configure'
        ).format(
            sheets_with_rows,
            rows_count
        )

        self.place_button.IsEnabled = (
            rows_count > 0
        )

    def _validate_assignments(self):
        assignments = []
        assigned_view_ids = set()
        errors = []

        for section in self.sections:
            sheet = section['sheet']

            for row_number, row in enumerate(section['rows']):
                v_index = row['view'].SelectedIndex - 1
                t_index = row['type'].SelectedIndex - 1
                p_index = row['position'].SelectedIndex - 1

                name = '{} / row {}'.format(
                    sheet.SheetNumber,
                    row_number + 1
                )

                if (
                    v_index < 0
                    or p_index < 0
                    or v_index >= len(self.available_views)
                    or p_index >= len(self.positions)
                ):
                    errors.append(
                        '{}: select View and Saved Position'.format(
                            name
                        )
                    )
                    continue

                view = self.available_views[v_index]

                if is_schedule_view(view):
                    viewport_type = None
                else:
                    if (
                        t_index < 0
                        or t_index >= len(self.viewport_types)
                    ):
                        errors.append(
                            '{}: select a Viewport Type'.format(
                                name
                            )
                        )
                        continue

                    viewport_type = self.viewport_types[t_index]

                position = self.positions[p_index]
                view_id = id_value(view.Id)

                if view_id in assigned_view_ids:
                    errors.append(
                        '{}: view "{}" is assigned more than once'.format(
                            name,
                            view.Name
                        )
                    )
                    continue

                if not can_place_view(sheet, view):
                    errors.append(
                        '{}: Revit does not allow "{}" on this sheet'.format(
                            name,
                            view.Name
                        )
                    )
                    continue

                assigned_view_ids.add(view_id)
                assignments.append((
                    sheet,
                    view,
                    viewport_type,
                    position
                ))

        return (assignments, errors)

    def _place_clicked(self, sender, args):
        assignments, errors = (
            self._validate_assignments()
        )

        if errors:
            ndev_alert(
                'Please correct the following before placing views:\n\n'
                + '\n'.join(errors[:25])
                + (
                    '\n... and more.'
                    if len(errors) > 25
                    else ''
                ),
                title='Check View Assignments'
            )
            return

        if not assignments:
            ndev_alert(
                'Add and configure at least one view before placing.',
                title='SheetPilot'
            )
            return

        sheet_count = len(set([
            id_value(item[0].Id)
            for item in assignments
        ]))

        prompt = (
            'ALL VIEWS ABOARD!\n'
            'Ready to land them in their perfect spots?\n\n'
            '{} view(s)  |  {} sheet(s)\n\n'
            'A quick stop at a temporary location, then a precise '
            'landing at each saved position. Existing placed viewports '
            'stay untouched.'
        ).format(
            len(assignments),
            sheet_count
        )

        if not ndev_alert(
            prompt,
            title='SheetPilot - Ready for Takeoff?',
            yes=True,
            no=True,
            flight=True
        ):
            return

        self.result_assignments = assignments
        self.DialogResult = True

    def _cancel_clicked(self, sender, args):
        self.DialogResult = False


# The message changes ONCE per sheet, not once per view. Every selected
# sheet gets one different joke until this list is exhausted, then it cycles.
# Emojis are Unicode escape sequences for IronPython 2.7 compatibility.
SHEETPILOT_SHEET_JOKES = (
    u'\U0001F680 Revit is negotiating landing rights with your views... Please hold!',
    u'\U0001F6F8 Your views are flying first class. Preparing for landing!',
    u'\u2615 Revit is having a coffee break... Just kidding, still working!',
    u'\U0001F9ED GPS recalculating... Your views are almost home!',
    u'\U0001F477 BIM engineers at work! Please don\'t disturb the coordinates.',
    u'\U0001FA84 Aligning views with magic... and a little Revit API!',
    u'\U0001F6EC Easy, captain! We\'re parking your views perfectly.',
    u'\U0001F6F0 Aligning stars, grids, and viewports... almost there!',
    u'\u2615 SheetPilot is fueling up with coffee before the next landing...',
    u'\U0001F3AF Calibrating perfect parking spots for your views...',
    u'\U0001F6EC Air traffic control says your views are cleared for landing!',
    u'\U0001F60E Moving views like a boss... try not to blink.',
    u'\U0001F527 Tightening the bolts on your sheet layout...',
    u'\u2728 Polishing the landing zone for a smooth touchdown...'
)


def _refresh_sheetpilot_progress_window():
    """Allow WPF to paint a status change BETWEEN Revit API view cycles.

    Called outside of any Revit transaction. Does not move views, reenter the
    placement code, or introduce an asynchronous Revit API operation.
    """
    try:
        frame = DispatcherFrame()

        def stop_pumping():
            frame.Continue = False

        dispatcher = Dispatcher.CurrentDispatcher
        dispatcher.BeginInvoke(
            DispatcherPriority.Background, System.Action(stop_pumping)
        )
        Dispatcher.PushFrame(frame)
    except Exception:
        # Progress display is cosmetic and must never interrupt placements.
        pass


class SheetPilotSheetProgressWindow(Window):
    """Nonmodal flight-status window, with ONE funny line for EACH sheet."""

    def __init__(self, sheet_count, view_count):
        Window.__init__(self)
        self.Title = 'Ndev Tools - SheetPilot | Refreshing'
        self.Width = 670
        self.Height = 300
        self.MinWidth = 550
        self.MinHeight = 260
        self.WindowStyle = getattr(WindowStyle, 'None')
        self.ResizeMode = ResizeMode.NoResize
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ShowInTaskbar = False
        self.Topmost = False
        self.Background = _NDEV_BG

        frame = Border()
        frame.Background = _NDEV_BG
        frame.BorderBrush = _NDEV_CYAN
        frame.BorderThickness = Thickness(2)
        frame.Padding = Thickness(22, 18, 22, 18)
        content = StackPanel()
        frame.Child = content
        self.Content = frame

        title = _ndev_label('SHEETPILOT  |  FLIGHT CONTROL', 14, _NDEV_CYAN, True)
        title.Margin = Thickness(0, 0, 0, 12)
        content.Children.Add(title)

        self.sheet_label = _ndev_label('Preparing sheet...', 19, _NDEV_LIGHT, True)
        self.sheet_label.Margin = Thickness(0, 0, 0, 12)
        content.Children.Add(self.sheet_label)

        joke_panel = Border()
        joke_panel.Background = _NDEV_NAVY
        joke_panel.CornerRadius = CornerRadius(9)
        joke_panel.Padding = Thickness(15, 13, 15, 13)
        joke_panel.Margin = Thickness(0, 0, 0, 16)
        self.joke_label = _ndev_label('', 14, Brushes.White)
        self.joke_label.FontFamily = FontFamily('Segoe UI Emoji')
        self.joke_label.TextWrapping = TextWrapping.Wrap
        self.joke_label.TextTrimming = getattr(TextTrimming, 'None')
        joke_panel.Child = self.joke_label
        content.Children.Add(joke_panel)

        self.status_label = _ndev_label(
            'Getting the runway ready...', 12, _NDEV_MUTED
        )
        self.status_label.Margin = Thickness(0, 0, 0, 8)
        content.Children.Add(self.status_label)

        self.progress_bar = ProgressBar()
        self.progress_bar.Height = 10
        self.progress_bar.Minimum = 0.0
        self.progress_bar.Maximum = max(1, int(view_count))
        self.progress_bar.Value = 0.0
        self.progress_bar.Foreground = _NDEV_CYAN
        self.progress_bar.Background = _NDEV_PANEL
        content.Children.Add(self.progress_bar)

        footer = _ndev_label(
            'Please wait while your views find their parking spots.',
            11, _NDEV_MUTED
        )
        footer.Margin = Thickness(0, 10, 0, 0)
        content.Children.Add(footer)

    def start_sheet(self, current_index, sheet_total, sheet_number,
                    sheet_name, joke, sheet_views, finished_views):
        self.sheet_label.Text = 'Sheet {} of {}  |  {} - {}'.format(
            current_index, sheet_total, sheet_number, sheet_name
        )
        # Leave the same joke visible throughout ALL views on this sheet.
        self.joke_label.Text = joke
        self.status_label.Text = 'Preparing {} view(s) on this sheet...'.format(
            sheet_views
        )
        self.progress_bar.Value = float(finished_views)

    def finish_view(self, view_name, finished_views, total_views):
        self.status_label.Text = 'Finished {} of {} views  |  {}'.format(
            finished_views, total_views, view_name
        )
        self.progress_bar.Value = float(finished_views)


def _snapshot_batch_jobs(assignments):
    """Collect all choices once; use only IDs and copied position values."""
    jobs = []
    for sheet, view, viewport_type, position in assignments:
        jobs.append({
            'sheet_id': sheet.Id,
            'view_id': view.Id,
            'viewport_type_id': (
                viewport_type.Id if viewport_type is not None else None
            ),
            'sheet_number': str(sheet.SheetNumber),
            'sheet_name': str(sheet.Name),
            'view_name': str(view.Name),
            'position': {
                'name': str(position.get('name', 'Saved Position')),
                'x': float(position['x']),
                'y': float(position['y'])
            }
        })
    return jobs


def _run_batch_placements(assignments):
    """One status joke per SHEET; unchanged two-stage per-VIEW Revit API.

    The selection window has closed. Each view has its own independent
    TransactionGroup. We only update the modeless WPF display between view
    cycles and before starting a new sheet. No Revit API runs in UI callbacks.
    """
    successes = []
    failures = []
    jobs = _snapshot_batch_jobs(assignments)
    if not jobs:
        return (successes, failures)

    # Group only to ensure every sheet receives exactly ONE joke and one
    # status transition, even if the input happened to interleave sheets.
    sheet_order = []
    jobs_by_sheet = {}
    for job in jobs:
        key = id_value(job['sheet_id'])
        if key not in jobs_by_sheet:
            sheet_order.append(key)
            jobs_by_sheet[key] = []
        jobs_by_sheet[key].append(job)

    # Randomize jokes once per run; do not repeat until all have appeared.
    shuffled_jokes = list(SHEETPILOT_SHEET_JOKES)
    random.shuffle(shuffled_jokes)

    progress_window = None
    finished_views = 0
    try:
        # Cosmetic status window only; failure to show it does not prevent
        # the fully working placement procedure from running.
        try:
            progress_window = SheetPilotSheetProgressWindow(
                len(sheet_order), len(jobs)
            )
            progress_window.Show()
        except Exception:
            if progress_window is not None:
                try:
                    progress_window.Close()
                except Exception:
                    pass
            progress_window = None

        for sheet_index, sheet_key in enumerate(sheet_order):
            sheet_jobs = jobs_by_sheet[sheet_key]
            representative = sheet_jobs[0]
            joke = shuffled_jokes[sheet_index % len(shuffled_jokes)]

            if progress_window is not None:
                try:
                    progress_window.start_sheet(
                        sheet_index + 1, len(sheet_order),
                        representative['sheet_number'],
                        representative['sheet_name'], joke,
                        len(sheet_jobs), finished_views
                    )
                    _refresh_sheetpilot_progress_window()
                except Exception:
                    pass

            for job in sheet_jobs:
                sheet_number = job['sheet_number']
                view_name = job['view_name']

                try:
                    # Re-acquire elements AFTER the previous independent
                    # placement group has committed or rolled back.
                    sheet = doc.GetElement(job['sheet_id'])
                    view = doc.GetElement(job['view_id'])
                    viewport_type = (
                        doc.GetElement(job['viewport_type_id'])
                        if job['viewport_type_id'] is not None
                        else None
                    )

                    if sheet is None or view is None:
                        raise Exception('Sheet or view no longer exists in Revit.')
                    if not is_schedule_view(view) and viewport_type is None:
                        raise Exception('Selected viewport type no longer exists.')
                    if not can_place_view(sheet, view):
                        raise Exception('Revit no longer permits this view on the sheet.')

                    # UNCHANGED proven flow: create -> commit -> hide ->
                    # move existing viewport -> restore. The two-stage
                    # function completely commits or rolls back per view.
                    completed, failed = process_views(
                        sheet, viewport_type, [(view, job['position'])]
                    )

                    for completed_name, position_name in completed:
                        successes.append((
                            sheet_number, completed_name, position_name
                        ))
                    for failed_name, message in failed:
                        failures.append((sheet_number, failed_name, message))

                except Exception as error:
                    failures.append((sheet_number, view_name, str(error)))

                finished_views += 1
                if progress_window is not None:
                    try:
                        progress_window.finish_view(
                            view_name, finished_views, len(jobs)
                        )
                        _refresh_sheetpilot_progress_window()
                    except Exception:
                        pass

        return (successes, failures)
    finally:
        # Close before the existing landing-success/failure report opens.
        if progress_window is not None:
            try:
                progress_window.Close()
            except Exception:
                pass


def _report_batch_results(assignments, successes, failures):
    sheets_processed = len(set([
        id_value(item[0].Id)
        for item in assignments
    ]))

    if successes and not failures:
        headline = u'LANDING SUCCESSFUL! \U0001F3AF'
    elif failures:
        headline = 'FLIGHT REPORT - SOME VIEWS NEED ATTENTION'
    else:
        headline = 'FLIGHT REPORT - NO VIEWS PLACED'

    message = (
        headline + '\n\n'
        'Sheets processed: {}\n'
        'Views placed: {}\n'
        'Failed / skipped: {}'
    ).format(
        sheets_processed,
        len(successes),
        len(failures)
    )

    if successes:
        message += '\n\nPLACED:'

        for sheet_number, view_name, position_name in successes:
            message += '\n{} | {} -> {}'.format(
                sheet_number,
                view_name,
                position_name
            )

    if failures:
        message += '\n\nFAILED / SKIPPED:'

        for sheet_number, view_name, error in failures:
            message += '\n{} | {}: {}'.format(
                sheet_number,
                view_name,
                error
            )

    ndev_alert(
        message,
        title='Batch View Placement Results'
    )


def main():
    if REVIT_VERSION not in SUPPORTED_VERSIONS:
        ndev_alert(
            'This tool supports Revit 2022 - 2027.\n\n'
            'Current version: {}'.format(REVIT_VERSION),
            title='SheetPilot'
        )
        return

    saved_positions = load_saved_positions()

    if not saved_positions:
        ndev_alert(
            'No saved viewport positions were found for Revit {}.\n\n'
            'Save at least one position using Viewport Position Manager '
            'or Crop Position Manager first.'.format(REVIT_VERSION),
            title='No Saved Positions'
        )
        return

    sheets = sorted(
        get_sheets(),
        key=lambda s: s.SheetNumber.lower()
    )

    available_views = sorted(
        get_unplaced_views(),
        key=lambda v: v.Name.lower()
    )

    viewport_types = get_viewport_types()

    if not sheets:
        ndev_alert(
            'There are no non-placeholder sheets in this project.',
            title='SheetPilot'
        )
        return

    if not available_views:
        ndev_alert(
            'No unplaced views are available in this project.',
            title='SheetPilot'
        )
        return

    if not viewport_types:
        ndev_alert(
            'No viewport types were found. Add a standard viewport '
            'to the project, then try again.',
            title='SheetPilot'
        )
        return

    window = MultiSheetPlacementWindow(
        sheets,
        available_views,
        viewport_types,
        saved_positions
    )

    if window.ShowDialog() is not True:
        return

    assignments = window.result_assignments

    if not assignments:
        return

    successes, failures = _run_batch_placements(
        assignments
    )

    _report_batch_results(
        assignments,
        successes,
        failures
    )


try:
    main()
except Exception as error:
    ndev_alert(
        'SheetPilot Error:\n\n{}'.format(error),
        title='SheetPilot'
    )
