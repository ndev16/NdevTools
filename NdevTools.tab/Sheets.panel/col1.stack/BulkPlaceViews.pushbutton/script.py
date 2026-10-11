# -*- coding: utf-8 -*-

# ============================================================
# PLACE VIEWS ON SHEET
#
# Created by Nataraj Devaraj
#
# pyRevit / IronPython 2.7
# Revit 2022 - 2027
#
# WORKFLOW
# ------------------------------------------------------------
# 1. Read saved viewport positions.
# 2. Show ONLY views not already placed on sheets.
# 3. Multi-select views.
# 4. Select target sheet.
# 5. Select viewport type.
# 6. Select a saved position for each selected view.
# 7. Confirm.
# 8. V8: snapshot original view flags and links; hide all before placing.
# 8a. Roll back rather than place if any category/link cannot hide.
# 8b. Restore original states AFTER placement; no final recenter.
# 9. Apply viewport type.
# 10. Move each viewport to exact saved X/Y position.
# 11. Ask whether user wants to repeat.
#
# YES = Run workflow again.
# NO  = Close tool.
#
# ============================================================


from pyrevit import revit, DB, forms, script
from System.Collections.Generic import List

import json


# ============================================================
# NDEV TOOLS - CUSTOM TITLE BAR AND HELP
# UI only. The V8 viewport placement logic below is unchanged.
# pyRevit / IronPython 2.7 / Revit 2022-2027
# ============================================================

import System
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import (Window, WindowStyle, WindowState, ResizeMode,
                            Thickness, CornerRadius, WindowStartupLocation,
                            TextWrapping, FontWeights, VerticalAlignment,
                            HorizontalAlignment, TextTrimming)
from System.Windows.Controls import (DockPanel, Dock, Grid, ColumnDefinition,
                                     StackPanel, Border, Button, TextBlock,
                                     ScrollViewer, Orientation)
from System.Windows.Media import Color, SolidColorBrush, Brushes
from System.Windows.Shell import WindowChrome

NDEV_TOOL_TITLE = 'Ndev Tools - Place Views on Sheet'
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
        add_action('? Help', 78, 'Instructions, GitHub and LinkedIn',
                   lambda sender, args: ndev_show_help(window), cyan)

    add_action('-', 40, 'Minimize',
               lambda sender, args: setattr(window, 'WindowState',
                                            WindowState.Minimized))

    def maximize_or_restore(sender, args):
        if window.WindowState == WindowState.Maximized:
            window.WindowState = WindowState.Normal
        else:
            window.WindowState = WindowState.Maximized

    add_action('[]', 40, 'Maximize / Restore', maximize_or_restore)
    add_action('X', 40, 'Close', lambda sender, args: window.Close())

    def move_window(sender, args):
        # Buttons must remain clickable; only the unused caption area drags.
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

    # Detach from the old window BEFORE reparenting a live WPF control.
    # Otherwise WPF reports: already the logical child of another element.
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

    # Account for the new caption without resizing the original content.
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
        ndev_alert('Unable to open the browser.\n\n{}\n\n{}'.format(
                   url, error), title='Help - Browser')


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
    heading.Text = 'NDEV TOOLS | PLACE VIEWS ON SHEET'
    heading.FontWeight = FontWeights.Bold
    heading.Margin = Thickness(0, 0, 0, 12)
    panel.Children.Add(heading)

    instructions = TextBlock()
    instructions.Text = (
        '1. Save sheet X/Y positions using Viewport Position Manager.\n'
        '2. Select one or more currently unplaced views.\n'
        '3. Choose the destination sheet and viewport type.\n'
        '4. Assign a unique saved position to each chosen view.\n'
        '5. Confirm placement, then review the results.\n\n'
        'V8 safety: original model/annotation/import/analytical category '
        'visibility and Revit Link visibility are saved, temporarily hidden '
        'during placement, and restored afterward. Failed placements are '
        'rolled back. No final recentering is performed after restoration.\n\n'
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
               exitscript=False, **kwargs):
    """Informational and YES/NO alerts, preserving pyRevit return semantics."""
    window = Window()
    window.Title = ndev_window_title(title)
    window.Width = 600
    lines = len(str(message).splitlines())
    window.Height = min(690, max(255, 170 + 18 * lines))
    window.MinWidth = 440
    window.MinHeight = 220
    window.ResizeMode = ResizeMode.CanResize
    window.ShowInTaskbar = False
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen

    content = DockPanel()
    content.Margin = Thickness(16)

    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    actions.HorizontalAlignment = HorizontalAlignment.Right
    actions.Margin = Thickness(0, 12, 0, 0)
    DockPanel.SetDock(actions, Dock.Bottom)
    content.Children.Add(actions)

    def make_choice(caption, result, default=False, cancel=False):
        button = Button()
        button.Content = caption
        button.Width = 95
        button.Height = 32
        button.Margin = Thickness(8, 0, 0, 0)
        button.IsDefault = default
        button.IsCancel = cancel
        button.Click += lambda sender, args: setattr(window, 'DialogResult', result)
        actions.Children.Add(button)

    if yes and no:
        make_choice('Yes', True, default=True)
        make_choice('No', False, cancel=True)
    else:
        make_choice('OK', True, default=True, cancel=True)

    scroll = ScrollViewer()
    content_text = TextBlock()
    content_text.Text = str(message)
    content_text.TextWrapping = TextWrapping.Wrap
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


# ============================================================
# DOCUMENT
# ============================================================

doc = revit.doc


# ============================================================
# REVIT VERSION
# ============================================================

REVIT_VERSION = str(
    doc.Application.VersionNumber
)


SUPPORTED_VERSIONS = [
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027"
]


# ============================================================
# SAVED POSITION CONFIG
# ============================================================

VIEWPORT_POSITION_CONFIG = (
    "NDEV_VIEWPORT_POSITION_MANAGER_{}"
    .format(
        REVIT_VERSION
    )
)


CROP_POSITION_CONFIG = (
    "NDEV_CROP_POSITION_MANAGER_{}"
    .format(
        REVIT_VERSION
    )
)


POSITIONS_KEY = "positions_json"


# ============================================================
# ELEMENT ID VALUE
# ============================================================

def id_value(element_id):

    try:

        return element_id.IntegerValue

    except:

        try:

            return element_id.Value

        except:

            return str(
                element_id
            )


# ============================================================
# GET CONFIG VALUE
# ============================================================

def get_config_value(
        cfg,
        option_name,
        default_value
):

    # --------------------------------------------------------
    # ATTRIBUTE
    # --------------------------------------------------------

    try:

        value = getattr(
            cfg,
            option_name
        )

        if value is not None:

            return value

    except:

        pass


    # --------------------------------------------------------
    # GET OPTION
    # --------------------------------------------------------

    try:

        value = cfg.get_option(
            option_name,
            default_value
        )

        if value is not None:

            return value

    except:

        pass


    return default_value


# ============================================================
# NORMALIZE ONE SAVED POSITION
# ============================================================

def normalize_position(
        position,
        fallback_name
):

    if not isinstance(
        position,
        dict
    ):

        return None


    name = position.get(
        "name",
        fallback_name
    )


    # --------------------------------------------------------
    # FIND X
    # --------------------------------------------------------

    x_value = None


    for key in [
        "x",
        "X",
        "pos_x",
        "sheet_x"
    ]:

        if key in position:

            x_value = (
                position[key]
            )

            break


    # --------------------------------------------------------
    # FIND Y
    # --------------------------------------------------------

    y_value = None


    for key in [
        "y",
        "Y",
        "pos_y",
        "sheet_y"
    ]:

        if key in position:

            y_value = (
                position[key]
            )

            break


    if (
        x_value is None
        or
        y_value is None
    ):

        return None


    try:

        x_value = float(
            x_value
        )

        y_value = float(
            y_value
        )

    except:

        return None


    result = dict(
        position
    )


    result["name"] = str(
        name
    )

    result["x"] = (
        x_value
    )

    result["y"] = (
        y_value
    )


    return result


# ============================================================
# PARSE POSITION DATA
# ============================================================

def parse_position_data(
        raw_data
):

    data = raw_data


    # --------------------------------------------------------
    # JSON STRING
    # --------------------------------------------------------

    if isinstance(
        raw_data,
        basestring
    ):

        try:

            data = json.loads(
                raw_data
            )

        except:

            return []


    result = []


    # --------------------------------------------------------
    # LIST FORMAT
    # --------------------------------------------------------

    if isinstance(
        data,
        list
    ):

        for index, item in enumerate(
            data
        ):

            position = (
                normalize_position(
                    item,
                    "Position {}".format(
                        index + 1
                    )
                )
            )


            if position:

                result.append(
                    position
                )


        return result


    # --------------------------------------------------------
    # DICTIONARY FORMAT
    # --------------------------------------------------------

    if isinstance(
        data,
        dict
    ):

        for key in data:

            value = (
                data[key]
            )


            # ------------------------------------------------
            # DICTIONARY VALUE
            # ------------------------------------------------

            if isinstance(
                value,
                dict
            ):

                temp = dict(
                    value
                )


                if "name" not in temp:

                    temp["name"] = (
                        str(
                            key
                        )
                    )


                position = (
                    normalize_position(
                        temp,
                        str(
                            key
                        )
                    )
                )


                if position:

                    result.append(
                        position
                    )


            # ------------------------------------------------
            # LIST / TUPLE VALUE
            # ------------------------------------------------

            elif isinstance(
                value,
                (list, tuple)
            ):

                if len(
                    value
                ) >= 2:

                    try:

                        result.append(
                            {
                                "name": str(
                                    key
                                ),
                                "x": float(
                                    value[0]
                                ),
                                "y": float(
                                    value[1]
                                )
                            }
                        )

                    except:

                        pass


        return result


    return []


# ============================================================
# LOAD POSITIONS FROM CONFIG
# ============================================================

def load_positions_from_config(
        config_section
):

    try:

        cfg = (
            script.get_config(
                config_section
            )
        )

    except:

        return []


    raw_data = (
        get_config_value(
            cfg,
            POSITIONS_KEY,
            "[]"
        )
    )


    return (
        parse_position_data(
            raw_data
        )
    )


# ============================================================
# LOAD SAVED POSITIONS
# ============================================================

def load_saved_positions():

    # --------------------------------------------------------
    # VIEWPORT POSITION MANAGER
    # --------------------------------------------------------

    positions = (
        load_positions_from_config(
            VIEWPORT_POSITION_CONFIG
        )
    )


    if positions:

        return positions


    # --------------------------------------------------------
    # CROP POSITION MANAGER FALLBACK
    # --------------------------------------------------------

    positions = (
        load_positions_from_config(
            CROP_POSITION_CONFIG
        )
    )


    return positions


# ============================================================
# GET VIEW TYPE NAME
# ============================================================

def get_view_type_name(
        view
):

    try:

        return (
            view.ViewType.ToString()
        )

    except:

        try:

            return str(
                view.ViewType
            )

        except:

            return "View"


# ============================================================
# CHECK SUPPORTED VIEW
# ============================================================

def is_supported_view(
        view
):

    if view is None:

        return False


    # --------------------------------------------------------
    # TEMPLATE
    # --------------------------------------------------------

    try:

        if view.IsTemplate:

            return False

    except:

        pass


    view_type_name = (
        get_view_type_name(
            view
        )
    )


    excluded_types = [

        "DrawingSheet",

        "Schedule",

        "ColumnSchedule",

        "PanelSchedule",

        "ProjectBrowser",

        "SystemBrowser",

        "Report",

        "CostReport",

        "LoadsReport",

        "Internal",

        "Undefined"

    ]


    if (
        view_type_name
        in
        excluded_types
    ):

        return False


    return True


# ============================================================
# GET VIEWS ALREADY PLACED
# ============================================================

def get_placed_view_ids():

    result = (
        set()
    )


    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    for viewport in viewports:

        try:

            result.add(
                id_value(
                    viewport.ViewId
                )
            )

        except:

            pass


    return result


# ============================================================
# GET UNPLACED VIEWS
# ============================================================

def get_unplaced_views():

    placed_ids = (
        get_placed_view_ids()
    )


    views = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.View)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    result = []


    for view in views:

        if not is_supported_view(
            view
        ):

            continue


        try:

            view_id = (
                id_value(
                    view.Id
                )
            )

        except:

            continue


        if view_id in placed_ids:

            continue


        result.append(
            view
        )


    return result


# ============================================================
# VIEW DISPLAY NAME
# ============================================================

def view_display_name(
        view
):

    view_type = (
        get_view_type_name(
            view
        )
    )


    scale_text = ""


    try:

        if view.Scale > 0:

            scale_text = (
                " | Scale 1:{}"
                .format(
                    view.Scale
                )
            )

    except:

        pass


    return (
        "{} | {}{} | ID {}"
        .format(
            view.Name,
            view_type,
            scale_text,
            id_value(
                view.Id
            )
        )
    )


# ============================================================
# SELECT UNPLACED VIEWS
# ============================================================

def select_unplaced_views():

    views = (
        get_unplaced_views()
    )


    if not views:

        ndev_alert(
            (
                "No unplaced views were found.\n\n"
                "All compatible views appear to "
                "already be placed on sheets."
            ),
            title="Place Views on Sheet"
        )

        return []


    try:

        views = sorted(
            views,
            key=lambda x:
                x.Name.lower()
        )

    except:

        pass


    items = []

    lookup = {}


    for view in views:

        display = (
            view_display_name(
                view
            )
        )


        items.append(
            display
        )


        lookup[
            display
        ] = view


    selected = (
        NdevSelectFromList.show(
            items,
            title="Select Unplaced Views",
            button_name="Select Views",
            multiselect=True
        )
    )


    if not selected:

        return []


    return [
        lookup[item]
        for item in selected
    ]


# ============================================================
# GET SHEETS
# ============================================================

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


        result.append(
            sheet
        )


    return result


# ============================================================
# SELECT TARGET SHEET
# ============================================================

def select_target_sheet():

    sheets = (
        get_sheets()
    )


    if not sheets:

        ndev_alert(
            "No sheets were found.",
            title="Place Views on Sheet"
        )

        return None


    try:

        sheets = sorted(
            sheets,
            key=lambda x:
                x.SheetNumber.lower()
        )

    except:

        pass


    items = []

    lookup = {}


    for sheet in sheets:

        display = (
            "{} | {} | ID {}"
            .format(
                sheet.SheetNumber,
                sheet.Name,
                id_value(
                    sheet.Id
                )
            )
        )


        items.append(
            display
        )


        lookup[
            display
        ] = sheet


    selected = (
        NdevSelectFromList.show(
            items,
            title="Select Target Sheet",
            button_name="Select Sheet",
            multiselect=False
        )
    )


    if not selected:

        return None


    return (
        lookup[
            selected
        ]
    )


# ============================================================
# GET ELEMENT TYPE NAME
# ============================================================

def get_element_type_name(
        element_type
):

    # --------------------------------------------------------
    # NAME PROPERTY
    # --------------------------------------------------------

    try:

        value = (
            element_type.Name
        )


        if value:

            return value

    except:

        pass


    # --------------------------------------------------------
    # SYMBOL NAME
    # --------------------------------------------------------

    try:

        parameter = (
            element_type.get_Parameter(
                DB.BuiltInParameter.SYMBOL_NAME_PARAM
            )
        )


        if parameter:

            value = (
                parameter.AsString()
            )


            if value:

                return value

    except:

        pass


    # --------------------------------------------------------
    # TYPE NAME
    # --------------------------------------------------------

    try:

        parameter = (
            element_type.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
            )
        )


        if parameter:

            value = (
                parameter.AsString()
            )


            if value:

                return value

    except:

        pass


    return (
        "Viewport Type {}".format(
            id_value(
                element_type.Id
            )
        )
    )


# ============================================================
# GET VIEWPORT FAMILY NAME
# ============================================================

def get_viewport_family_name(
        element_type
):

    try:

        family_name = (
            element_type.FamilyName
        )


        if family_name:

            return family_name

    except:

        pass


    try:

        parameter = (
            element_type.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME
            )
        )


        if parameter:

            value = (
                parameter.AsString()
            )


            if value:

                return value

    except:

        pass


    return "Viewport"


# ============================================================
# ADD VIEWPORT TYPE
# ============================================================

def add_viewport_type(
        result,
        seen_ids,
        element_type
):

    if element_type is None:

        return


    try:

        type_id = (
            id_value(
                element_type.Id
            )
        )

    except:

        return


    if type_id in seen_ids:

        return


    seen_ids.add(
        type_id
    )


    result.append(
        element_type
    )


# ============================================================
# GET VIEWPORT TYPES
# ============================================================

def get_viewport_types():

    result = []

    seen_ids = (
        set()
    )


    # ========================================================
    # EXISTING VIEWPORTS
    # ========================================================

    viewports = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    # ========================================================
    # METHOD 1
    # GETVALIDTYPES
    # ========================================================

    for viewport in viewports:

        try:

            valid_type_ids = (
                viewport.GetValidTypes()
            )


            for type_id in valid_type_ids:

                element_type = (
                    doc.GetElement(
                        type_id
                    )
                )


                add_viewport_type(
                    result,
                    seen_ids,
                    element_type
                )

        except:

            pass


    # ========================================================
    # METHOD 2
    # CURRENT VIEWPORT TYPES
    # ========================================================

    for viewport in viewports:

        try:

            element_type = (
                doc.GetElement(
                    viewport.GetTypeId()
                )
            )


            add_viewport_type(
                result,
                seen_ids,
                element_type
            )

        except:

            pass


    # ========================================================
    # METHOD 3
    # SEARCH ALL ELEMENT TYPES
    # ========================================================

    try:

        viewport_category = (
            DB.Category.GetCategory(
                doc,
                DB.BuiltInCategory.OST_Viewports
            )
        )


        if viewport_category:

            viewport_category_id = (
                id_value(
                    viewport_category.Id
                )
            )


            element_types = (
                DB.FilteredElementCollector(doc)
                .WhereElementIsElementType()
                .ToElements()
            )


            for element_type in element_types:

                try:

                    category = (
                        element_type.Category
                    )


                    if category is None:

                        continue


                    if (
                        id_value(
                            category.Id
                        )
                        !=
                        viewport_category_id
                    ):

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


    # ========================================================
    # SORT
    # ========================================================

    try:

        result = sorted(
            result,
            key=lambda x:
                get_element_type_name(
                    x
                ).lower()
        )

    except:

        pass


    return result


# ============================================================
# SELECT VIEWPORT TYPE
# ============================================================

def select_viewport_type():

    viewport_types = (
        get_viewport_types()
    )


    if not viewport_types:

        ndev_alert(
            (
                "No viewport types could be found.\n\n"
                "Make sure the project contains at least "
                "one normal viewport on a sheet."
            ),
            title="Place Views on Sheet"
        )

        return None


    items = []

    lookup = {}


    for viewport_type in viewport_types:

        family_name = (
            get_viewport_family_name(
                viewport_type
            )
        )


        type_name = (
            get_element_type_name(
                viewport_type
            )
        )


        display = (
            "{} : {} | ID {}"
            .format(
                family_name,
                type_name,
                id_value(
                    viewport_type.Id
                )
            )
        )


        if display in lookup:

            display = (
                "{} | {}"
                .format(
                    display,
                    id_value(
                        viewport_type.Id
                    )
                )
            )


        items.append(
            display
        )


        lookup[
            display
        ] = viewport_type


    items.sort()


    selected = (
        NdevSelectFromList.show(
            items,
            title="Select Viewport Type",
            button_name="Use Viewport Type",
            multiselect=False
        )
    )


    if not selected:

        return None


    return (
        lookup[
            selected
        ]
    )


# ============================================================
# CAN PLACE VIEW
# ============================================================

def can_place_view(
        sheet,
        view
):

    try:

        return (
            DB.Viewport.CanAddViewToSheet(
                doc,
                sheet.Id,
                view.Id
            )
        )

    except:

        return False


# ============================================================
# FILTER PLACEABLE VIEWS
# ============================================================

def filter_placeable_views(
        views,
        sheet
):

    valid = []

    invalid = []


    for view in views:

        if can_place_view(
            sheet,
            view
        ):

            valid.append(
                view
            )

        else:

            invalid.append(
                view
            )


    if invalid:

        message = (
            "These views cannot be placed "
            "on the selected sheet:\n\n"
        )


        for view in invalid:

            message += (
                "- {}\n"
                .format(
                    view.Name
                )
            )


        if valid:

            message += (
                "\n{} other view(s) can still be placed."
                .format(
                    len(
                        valid
                    )
                )
            )


        ndev_alert(
            message,
            title="Place Views on Sheet"
        )


    return valid


# ============================================================
# POSITION DISPLAY NAME
# ============================================================

def position_display_name(
        position,
        index
):

    name = (
        position.get(
            "name",
            "Position {}".format(
                index + 1
            )
        )
    )


    return (
        "{} | X: {:.4f} | Y: {:.4f}"
        .format(
            name,
            position["x"],
            position["y"]
        )
    )


# ============================================================
# CHOOSE POSITION
# ============================================================

def choose_position(
        available_positions,
        view
):

    items = []

    lookup = {}


    for index, position in enumerate(
        available_positions
    ):

        display = (
            position_display_name(
                position,
                index
            )
        )


        unique_display = (
            "{} | #{}"
            .format(
                display,
                index + 1
            )
        )


        items.append(
            unique_display
        )


        lookup[
            unique_display
        ] = position


    selected = (
        NdevSelectFromList.show(
            items,
            title=(
                "Select Saved Position\n\n"
                "View: {}"
            ).format(
                view.Name
            ),
            button_name="Use Position",
            multiselect=False
        )
    )


    if not selected:

        return None


    return (
        lookup[
            selected
        ]
    )


# ============================================================
# ASSIGN POSITIONS
# ============================================================

def assign_positions(
        views,
        saved_positions
):

    if (
        len(
            views
        )
        >
        len(
            saved_positions
        )
    ):

        ndev_alert(
            (
                "You selected {} views, but only {} "
                "saved positions are available.\n\n"
                "Each selected view needs its own "
                "saved position.\n\n"
                "Save more positions or select fewer views."
            ).format(
                len(
                    views
                ),
                len(
                    saved_positions
                )
            ),
            title="Place Views on Sheet"
        )

        return []


    available_positions = (
        list(
            saved_positions
        )
    )


    assignments = []


    for view in views:

        position = (
            choose_position(
                available_positions,
                view
            )
        )


        if position is None:

            return []


        assignments.append(
            (
                view,
                position
            )
        )


        try:

            available_positions.remove(
                position
            )

        except:

            pass


    return assignments


# ============================================================
# TEMPORARY V/G: SAVE, HIDE, AND RESTORE (ADDED)
# ============================================================
# The four V/G class flags and each individually hideable category are
# handled separately. All edits are rolled back if a view fails.

_VG_CLASS_FLAGS = (
    'AreModelCategoriesHidden',
    'AreAnnotationCategoriesHidden',
    'AreAnalyticalModelCategoriesHidden',
    'AreImportCategoriesHidden',
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

    # CAD imports may have dynamic categories not listed in the base map.
    try:
        for imported in (DB.FilteredElementCollector(doc)
                         .OfClass(DB.ImportInstance)
                         .WhereElementIsNotElementType()
                         .ToElements()):
            visit(imported.Category)
    except Exception:
        pass

    try:
        visit(DB.Category.GetCategory(doc, DB.BuiltInCategory.OST_RvtLinks))
    except Exception:
        pass

    return result


# V8: exact visibility-group switches (no per-category overrides).
_V8_VISIBILITY_FLAGS = (
    'AreModelCategoriesHidden',
    'AreAnnotationCategoriesHidden',
    'AreImportCategoriesHidden',
    'AreAnalyticalModelCategoriesHidden',
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


def save_and_hide_view_for_placement(view):
    """MUST run inside Transaction 1, before creating the viewport.

    Read ORIGINAL visibility first. Hide exactly the four category GROUPS and
    all Revit links. Any unsupported operation raises an error; transaction
    group rollback will prevent a viewport from being placed half-configured.
    """
    state = {
        'template_id': view.ViewTemplateId,
        'class_flags': {},
        'link_ids_newly_hidden': [],
        'link_strategy': None,
    }

    # Important: capture flags BEFORE detaching the view template.
    for flag in _V8_VISIBILITY_FLAGS:
        try:
            state['class_flags'][flag] = bool(getattr(view, flag))
        except Exception as error:
            raise Exception(
                'Cannot capture original visibility {}: {}'.format(flag, error)
            )

    # Capture the originally hidden BY-ELEMENT condition for every link.
    links = _v8_link_instances()
    to_hide = []
    for link in links:
        try:
            if not bool(link.IsHidden(view)):
                to_hide.append(link)
        except Exception as error:
            raise Exception(
                'Cannot read original Revit-link visibility {}: {}'.format(
                    id_value(link.Id), error
                )
            )

    # View templates may control V/G. Detach temporarily, restore last.
    if state['template_id'] != DB.ElementId.InvalidElementId:
        view.ViewTemplateId = DB.ElementId.InvalidElementId
        if view.ViewTemplateId != DB.ElementId.InvalidElementId:
            raise Exception('Unable to detach source view template.')
        doc.Regenerate()

    # Turn off ALL FOUR V/G CATEGORY GROUPS, not hundreds of independent
    # subcategories. Existing per-category hidden/visible states are untouched.
    for flag in _V8_VISIBILITY_FLAGS:
        try:
            setattr(view, flag, True)
            if not bool(getattr(view, flag)):
                raise Exception('Revit left the category group visible')
        except Exception as error:
            raise Exception(
                'Unable to switch off {}: {}'.format(flag, error)
            )
    doc.Regenerate()

    # Hide each previously visible link. A failed hide MUST stop placement.
    # The Revit Links tab is not a normal category in some Revit versions;
    # simply changing OST_RvtLinks would not verify that the link disappeared.
    state['link_strategy'] = 'element' if to_hide else 'none_needed'
    for link in to_hide:
        try:
            if not link.CanBeHidden(view):
                raise Exception('Revit does not allow hiding this link here')
            view.HideElements(_v8_one_element_id(link.Id))
            if not bool(link.IsHidden(view)):
                raise Exception('Link did not become hidden')
            state['link_ids_newly_hidden'].append(link.Id)
        except Exception as error:
            raise Exception(
                'Cannot hide Revit link {}: {}; no viewport placed'.format(
                    id_value(link.Id), error
                )
            )

    doc.Regenerate()
    return state


def restore_view_after_placement(view, state):
    """MUST run inside Transaction 3. Restore originals; template LAST.

    Never unhide links which were already hidden before script started.
    Never touch any original per-category hidden/visible override.
    """
    # Reverse only link visibility CHANGES the script actually made.
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
                'Cannot restore Revit link {}: {}'.format(id_value(link_id), error)
            )

    # Restore exactly TRUE/FALSE values captured before temporary changes.
    for flag in _V8_VISIBILITY_FLAGS:
        original = state['class_flags'][flag]
        try:
            setattr(view, flag, original)
            if bool(getattr(view, flag)) != original:
                raise Exception('Revit did not restore original value')
        except Exception as error:
            raise Exception(
                'Cannot restore category group {}: {}'.format(flag, error)
            )

    # Reapply template LAST so its controlled visibility is original again.
    if view.ViewTemplateId != state['template_id']:
        view.ViewTemplateId = state['template_id']
    if view.ViewTemplateId != state['template_id']:
        raise Exception('Cannot restore original view template.')
    doc.Regenerate()

    # Confirm original flags; never declare success if restoration diverged.
    for flag in _V8_VISIBILITY_FLAGS:
        if bool(getattr(view, flag)) != state['class_flags'][flag]:
            raise Exception(
                'Original {} was not restored after template reapplication'.format(flag)
            )


def _begin_transaction(name):
    tx = DB.Transaction(doc, name)
    if tx.Start() != DB.TransactionStatus.Started:
        raise Exception('Could not start transaction: {}'.format(name))
    return tx


def _finish_transaction(tx, stage):
    if tx.Commit() != DB.TransactionStatus.Committed:
        raise Exception('Could not commit: {}'.format(stage))


# ============================================================
# PLACE ONE VIEW
# ============================================================

def place_one_view(
        sheet,
        view,
        viewport_type,
        position
):

    x_value = float(
        position["x"]
    )


    y_value = float(
        position["y"]
    )


    insertion_point = (
        DB.XYZ(
            x_value,
            y_value,
            0.0
        )
    )


    # --------------------------------------------------------
    # CREATE VIEWPORT
    # --------------------------------------------------------

    viewport = (
        DB.Viewport.Create(
            doc,
            sheet.Id,
            view.Id,
            insertion_point
        )
    )


    if viewport is None:

        raise Exception(
            "Viewport.Create returned None."
        )


    # --------------------------------------------------------
    # APPLY VIEWPORT TYPE
    # --------------------------------------------------------

    try:

        if (
            viewport.GetTypeId()
            !=
            viewport_type.Id
        ):

            viewport.ChangeTypeId(
                viewport_type.Id
            )

    except Exception as error:

        raise Exception(
            (
                "Viewport created, but selected "
                "viewport type could not be applied: {}"
            ).format(
                error
            )
        )


    # --------------------------------------------------------
    # EXACT SAVED POSITION
    # --------------------------------------------------------

    current_center = (
        viewport.GetBoxCenter()
    )


    exact_center = (
        DB.XYZ(
            x_value,
            y_value,
            current_center.Z
        )
    )


    viewport.SetBoxCenter(
        exact_center
    )


    return viewport


# ============================================================
# BUILD CONFIRMATION
# ============================================================

def build_confirmation(
        sheet,
        viewport_type,
        assignments
):

    message = (
        "PLACE VIEWS ON SHEET\n\n"
        "TARGET SHEET:\n"
        "{} - {}\n\n"
        "VIEWPORT TYPE:\n"
        "{}\n\n"
        "VIEW / POSITION:\n"
    ).format(
        sheet.SheetNumber,
        sheet.Name,
        get_element_type_name(
            viewport_type
        )
    )


    for view, position in assignments:

        message += (
            "\n{}  ->  {}"
            .format(
                view.Name,
                position.get(
                    "name",
                    "Saved Position"
                )
            )
        )


    message += (
        "\n\nPlace {} view(s)?"
        .format(
            len(
                assignments
            )
        )
    )


    return message


# ============================================================
# PROCESS ALL VIEWS
# ============================================================

def process_views(sheet, viewport_type, assignments):
    """Drop-in replacement for original v7 process_views().

    Sequence per source view:
       Transaction 1: record + hide -> COMMIT
       Transaction 2: place/position WHILE HIDDEN -> COMMIT
       Transaction 3: restore EXACT original visibility -> COMMIT
       Assimilate group; any exception rolls back entire group.

    IMPORTANT: No SetBoxCenter() after restore. The viewport box can grow
    when links/categories return; recentering then shifts the actual view.
    """
    successful, failed = [], []
    for source_view, position in assignments:
        group = DB.TransactionGroup(
            doc,
            'Place View (V8 exact visibility) - {}'.format(source_view.Name)
        )
        group_active = False
        tx = None
        stage = 'Starting view placement'
        try:
            if group.Start() != DB.TransactionStatus.Started:
                raise Exception('Unable to start rollback group')
            group_active = True

            stage = 'Saving original visibility and hiding categories/links'
            tx = _begin_transaction('V8 hide before viewport placement')
            state = save_and_hide_view_for_placement(source_view)
            _finish_transaction(tx, stage)
            tx = None

            stage = 'Placing at saved position while visibility is OFF'
            tx = _begin_transaction('V8 place viewport at saved position')
            viewport = place_one_view(
                sheet, source_view, viewport_type, position
            )
            if viewport is None:
                raise Exception('Viewport was not created')
            _finish_transaction(tx, stage)
            tx = None

            stage = 'Restoring original view settings'
            tx = _begin_transaction('V8 restore source view visibility')
            restore_view_after_placement(source_view, state)
            # NO REPOSITIONING HERE. Restoring links changes box extents.
            _finish_transaction(tx, stage)
            tx = None

            stage = 'Saving placement'
            if group.Assimilate() != DB.TransactionStatus.Committed:
                raise Exception('Unable to finish grouped placement')
            group_active = False
            successful.append((
                source_view.Name,
                position.get('name', 'Saved Position')
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
    return successful, failed


# ============================================================
# SHOW RESULTS
# ============================================================

def show_results(
        sheet,
        successful,
        failed
):

    message = (
        "PLACE VIEWS COMPLETE\n\n"
        "SHEET:\n"
        "{} - {}\n\n"
        "PLACED: {}\n"
        "FAILED / SKIPPED: {}"
    ).format(
        sheet.SheetNumber,
        sheet.Name,
        len(
            successful
        ),
        len(
            failed
        )
    )


    if successful:

        message += (
            "\n\nPLACED:\n"
        )


        for view_name, position_name in successful:

            message += (
                "\n{} -> {}"
                .format(
                    view_name,
                    position_name
                )
            )


    if failed:

        message += (
            "\n\nFAILED / SKIPPED:\n"
        )


        for view_name, error in failed:

            message += (
                "\n{}: {}"
                .format(
                    view_name,
                    error
                )
            )


    ndev_alert(
        message,
        title="Place Views on Sheet"
    )


# ============================================================
# MAIN WORKFLOW
# ============================================================

def main():

    # ========================================================
    # CHECK REVIT VERSION
    # ========================================================

    if (
        REVIT_VERSION
        not in
        SUPPORTED_VERSIONS
    ):

        ndev_alert(
            (
                "This tool supports Revit 2022 - 2027.\n\n"
                "Current Version: {}"
            ).format(
                REVIT_VERSION
            ),
            title="Place Views on Sheet"
        )

        return False


    # ========================================================
    # STEP 0
    # LOAD SAVED POSITIONS
    # ========================================================

    saved_positions = (
        load_saved_positions()
    )


    if not saved_positions:

        ndev_alert(
            (
                "No saved viewport positions were found "
                "for Revit {}.\n\n"
                "Please use the Viewport Position Manager "
                "or Crop Position Manager to save at least "
                "one position first.\n\n"
                "Then run this tool again."
            ).format(
                REVIT_VERSION
            ),
            title="No Saved Positions"
        )

        return False


    # ========================================================
    # STEP 1
    # SELECT UNPLACED VIEWS
    # ========================================================

    selected_views = (
        select_unplaced_views()
    )


    if not selected_views:

        return False


    # ========================================================
    # STEP 2
    # SELECT TARGET SHEET
    # ========================================================

    target_sheet = (
        select_target_sheet()
    )


    if target_sheet is None:

        return False


    # ========================================================
    # FILTER PLACEABLE VIEWS
    # ========================================================

    selected_views = (
        filter_placeable_views(
            selected_views,
            target_sheet
        )
    )


    if not selected_views:

        ndev_alert(
            (
                "None of the selected views can "
                "be placed on this sheet."
            ),
            title="Place Views on Sheet"
        )

        return False


    # ========================================================
    # STEP 3
    # SELECT VIEWPORT TYPE
    # ========================================================

    viewport_type = (
        select_viewport_type()
    )


    if viewport_type is None:

        return False


    # ========================================================
    # STEP 4
    # ASSIGN SAVED POSITIONS
    # ========================================================

    assignments = (
        assign_positions(
            selected_views,
            saved_positions
        )
    )


    if not assignments:

        return False


    # ========================================================
    # STEP 5
    # CONFIRM
    # ========================================================

    confirmation = (
        ndev_alert(
            build_confirmation(
                target_sheet,
                viewport_type,
                assignments
            ),
            title="Place Views on Sheet",
            yes=True,
            no=True
        )
    )


    if not confirmation:

        return False


    # ========================================================
    # STEP 6
    # PLACE VIEWS
    # ========================================================

    successful, failed = (
        process_views(
            target_sheet,
            viewport_type,
            assignments
        )
    )


    # ========================================================
    # STEP 7
    # SHOW RESULTS
    # ========================================================

    show_results(
        target_sheet,
        successful,
        failed
    )


    # ========================================================
    # COMPLETE
    #
    # TRUE TELLS THE OUTER LOOP THAT THE WORKFLOW FINISHED.
    # ========================================================

    return True


# ============================================================
# RUN
# REPEAT WORKFLOW UNTIL USER SAYS NO
# ============================================================

try:

    while True:

        # ----------------------------------------------------
        # RUN COMPLETE WORKFLOW
        # ----------------------------------------------------

        completed = (
            main()
        )


        # ----------------------------------------------------
        # USER CANCELLED / WORKFLOW DID NOT COMPLETE
        # ----------------------------------------------------

        if not completed:

            break


        # ----------------------------------------------------
        # ASK WHETHER TO REPEAT
        # ----------------------------------------------------

        repeat_process = (
            ndev_alert(
                (
                    "VIEW PLACEMENT COMPLETE\n\n"
                    "Do you want to place more views "
                    "on another sheet?\n\n"
                    "YES = Repeat the process\n"
                    "NO = Close the tool"
                ),
                title="Place More Views?",
                yes=True,
                no=True
            )
        )


        # ----------------------------------------------------
        # NO
        # CLOSE
        # ----------------------------------------------------

        if not repeat_process:

            break


        # ----------------------------------------------------
        # YES
        #
        # LOOP STARTS AGAIN AUTOMATICALLY.
        #
        # The views placed during the previous run will no
        # longer appear because get_unplaced_views() is run
        # again from Revit.
        # ----------------------------------------------------


except Exception as error:

    ndev_alert(
        (
            "Place Views on Sheet Error:\n\n{}"
        ).format(
            error
        ),
        title="Place Views on Sheet"
    )
