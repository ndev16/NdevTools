# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms, script
from System.Collections.Generic import List
from System.Windows import (Thickness, VerticalAlignment, FontWeights,
                            Window, WindowStartupLocation, ResizeMode,
                            TextWrapping, WindowStyle, WindowState, TextTrimming,
                            HorizontalAlignment, CornerRadius)
from System.Windows.Controls import (DockPanel, Dock, StackPanel,
                                     Button, TextBlock, Border)
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows.Media import Color, SolidColorBrush, Brushes
from System.Windows.Shell import WindowChrome
from System.Windows.Controls import Orientation, ScrollViewer, ScrollBarVisibility
import json


# ============================================================
# VIEWPORT POSITION MANAGER
#
# REVIT 2022 - 2027
# IronPython / Python 2.7 Compatible
#
#
# WORKFLOW
# ------------------------------------------------------------
#
# MAIN MENU:
#
# 1. Apply Saved Position
# 2. Save New Position
# 3. Capture New Position + Apply
# 4. Rename Saved Position
# 5. Overwrite Saved Position
# 6. Delete Saved Position
# 7. Show Saved Positions
#
#
# SAVE NEW POSITION:
#
#   Select reference viewport from views ALREADY ON SHEETS
#       ↓
#   Read exact viewport X/Y
#       ↓
#   Ask for position name
#       ↓
#   Save
#
#
# APPLY SAVED POSITION:
#
#   Choose saved position
#       ↓
#   Select MULTIPLE target viewports already on sheets
#       ↓
#   Apply same X/Y to all
#
#
# Maximum:
#
#   10 positions PER REVIT VERSION
#
# Revit 2022 has separate memory
# Revit 2023 has separate memory
# ...
# Revit 2027 has separate memory
#
# ============================================================


doc = revit.doc
uidoc = revit.uidoc


# ============================================================
# SETTINGS
# ============================================================

MAX_POSITIONS = 10


SUPPORTED_VERSIONS = [
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027"
]


# ============================================================
# CURRENT REVIT VERSION
# ============================================================

REVIT_VERSION = str(
    doc.Application.VersionNumber
)


# ============================================================
# VERSION-SPECIFIC MEMORY
# ============================================================

CONFIG_SECTION = (
    "NDEV_VIEWPORT_POSITION_MANAGER_{}"
    .format(
        REVIT_VERSION
    )
)


# ============================================================
# ELEMENT ID VALUE
#
# Works with old and newer Revit APIs.
# ============================================================

def id_value(element_id):

    try:

        return element_id.IntegerValue

    except:

        return element_id.Value


# ============================================================
# LOAD SAVED POSITIONS
# ============================================================

def load_positions():

    cfg = script.get_config(
        CONFIG_SECTION
    )

    try:

        raw_data = cfg.get_option(
            "positions_json",
            "[]"
        )

        positions = json.loads(
            raw_data
        )

        if not isinstance(
            positions,
            list
        ):

            positions = []

    except:

        positions = []


    return positions[
        :MAX_POSITIONS
    ]


# ============================================================
# SAVE POSITIONS
# ============================================================

def save_positions(
        positions
):

    cfg = script.get_config(
        CONFIG_SECTION
    )

    cfg.positions_json = json.dumps(
        positions[
            :MAX_POSITIONS
        ]
    )

    script.save_config()


# ============================================================
# CHECK DUPLICATE NAME
# ============================================================

def name_exists(
        positions,
        name,
        ignore_index=None
):

    check_name = (
        name
        .strip()
        .lower()
    )


    for index, position in enumerate(
            positions
    ):

        if (
            ignore_index is not None
            and
            index == ignore_index
        ):

            continue


        existing_name = (
            position
            .get(
                "name",
                ""
            )
            .strip()
            .lower()
        )


        if existing_name == check_name:

            return True


    return False


# ============================================================
# GET ALL VIEWPORTS THAT ARE ACTUALLY ON SHEETS
# ============================================================

def get_placed_viewports():

    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    result = []


    for viewport in viewports:

        try:

            sheet = doc.GetElement(
                viewport.OwnerViewId
            )


            view = doc.GetElement(
                viewport.ViewId
            )


            if sheet is None:
                continue


            if view is None:
                continue


            if not isinstance(
                sheet,
                DB.ViewSheet
            ):

                continue


            result.append(
                {
                    "viewport":
                        viewport,

                    "view":
                        view,

                    "sheet":
                        sheet
                }
            )


        except:

            pass


    return result


# ============================================================
# CREATE DISPLAY NAME
# ============================================================

def viewport_display_name(
        viewport_data
):

    viewport = viewport_data[
        "viewport"
    ]

    view = viewport_data[
        "view"
    ]

    sheet = viewport_data[
        "sheet"
    ]


    return (
        "{} | {} | {} | Scale 1:{} | VP ID {}"
        .format(
            sheet.SheetNumber,
            sheet.Name,
            view.Name,
            view.Scale,
            id_value(
                viewport.Id
            )
        )
    )


# ============================================================
# SELECT ONE REFERENCE VIEWPORT
# ============================================================

def select_reference_viewport():

    placed_viewports = (
        get_placed_viewports()
    )


    if not placed_viewports:

        forms.alert(
            "No views are currently placed on sheets.",
            title="Viewport Position Manager"
        )

        return None


    display_items = []
    lookup = {}


    for viewport_data in placed_viewports:

        display_name = (
            viewport_display_name(
                viewport_data
            )
        )


        display_items.append(
            display_name
        )


        lookup[
            display_name
        ] = viewport_data


    display_items.sort()


    selected = forms.SelectFromList.show(
        display_items,
        title="Select Reference Viewport",
        button_name="Acquire Position",
        multiselect=False
    )


    if not selected:

        return None


    return lookup[
        selected
    ]


# ============================================================
# SELECT MULTIPLE TARGET VIEWPORTS
# ============================================================

def select_target_viewports(
        exclude_viewport_id=None
):

    placed_viewports = (
        get_placed_viewports()
    )


    display_items = []
    lookup = {}


    for viewport_data in placed_viewports:

        viewport = viewport_data[
            "viewport"
        ]


        if exclude_viewport_id is not None:

            if (
                id_value(
                    viewport.Id
                )
                ==
                exclude_viewport_id
            ):

                continue


        display_name = (
            viewport_display_name(
                viewport_data
            )
        )


        display_items.append(
            display_name
        )


        lookup[
            display_name
        ] = viewport_data


    display_items.sort()


    if not display_items:

        forms.alert(
            "No target viewports were found.",
            title="Viewport Position Manager"
        )

        return []


    selected_items = (
        forms.SelectFromList.show(
            display_items,
            title="Select Target Viewports",
            button_name="Apply Position",
            multiselect=True
        )
    )


    if not selected_items:

        return []


    return [
        lookup[item]
        for item in selected_items
    ]


# ============================================================
# READ VIEWPORT POSITION
# ============================================================

def get_viewport_position(
        viewport
):

    center = (
        viewport.GetBoxCenter()
    )


    return DB.XYZ(
        center.X,
        center.Y,
        0.0
    )


# ============================================================
# NDEV TOOLS - SHARED TITLE BAR + HELP
# ============================================================
# The original pyRevit list/search, command selector, and value input are
# retained. This wraps their existing WPF content with a custom title bar.
# Help sits in the SAME BAR as Minimize, Maximize, and Close.
# The viewport storage, transactions, and seven actions below are unchanged.

_NATIVE_FORMS = forms
_NATIVE_SELECT = forms.SelectFromList
_NATIVE_SWITCH = forms.CommandSwitchWindow
_NATIVE_VALUE = forms.GetValueWindow

NDEV_GITHUB = 'https://github.com/ndev16'
NDEV_LINKEDIN = 'https://www.linkedin.com/in/nataraj016/'


def _ndev_title(title):
    if not title:
        return 'Ndev Tools - Viewport Position Manager'
    value = str(title)
    if value.lower().startswith('ndev tools'):
        return value
    return 'Ndev Tools - ' + value


def _ndev_open_url(url):
    try:
        launch = ProcessStartInfo(url)
        launch.UseShellExecute = True
        Process.Start(launch)
    except Exception as error:
        _NATIVE_FORMS.alert(
            'Could not open the browser automatically.\n\n'
            'Please open this link:\n{}\n\n{}'.format(url, error),
            title='Ndev Tools - Link'
        )


def _ndev_show_help(owner):
    """Help content and profile links from the existing working tool."""
    help_window = Window()
    help_window.Title = 'Ndev Tools - Viewport Position Manager - Help'
    help_window.Width = 500
    help_window.Height = 355
    help_window.ResizeMode = ResizeMode.NoResize
    help_window.WindowStartupLocation = WindowStartupLocation.CenterOwner
    help_window.ShowInTaskbar = False
    help_window.Owner = owner

    content = StackPanel()
    content.Margin = Thickness(18, 14, 18, 14)

    heading = TextBlock()
    heading.Text = 'NDEV TOOLS | VIEWPORT POSITION MANAGER'
    heading.FontWeight = FontWeights.Bold
    heading.Margin = Thickness(0, 0, 0, 12)
    content.Children.Add(heading)

    info = TextBlock()
    info.Text = (
        'Apply Saved Position: select saved X/Y coordinates and choose '
        'one or more viewports.\n\n'
        'Save New Position: record a reference viewport location.\n'
        'Capture New Position + Apply: use a reference immediately.\n'
        'Show, Rename, Overwrite, Delete: manage up to 10 positions.\n\n'
        'When capturing or applying X/Y, Ndev Tools temporarily hides the '
        'Model, Annotation, Analytical, Imported categories and Revit Links. '
        'Original visibility and view templates are restored afterward.'
    )
    info.TextWrapping = TextWrapping.Wrap
    info.Margin = Thickness(0, 0, 0, 14)
    content.Children.Add(info)

    github = Button()
    github.Content = 'GitHub  -  github.com/ndev16'
    github.Height = 32
    github.Margin = Thickness(0, 0, 0, 6)
    github.Click += lambda sender, args: _ndev_open_url(NDEV_GITHUB)
    content.Children.Add(github)

    linkedin = Button()
    linkedin.Content = 'LinkedIn  -  linkedin.com/in/nataraj016'
    linkedin.Height = 32
    linkedin.Click += lambda sender, args: _ndev_open_url(NDEV_LINKEDIN)
    content.Children.Add(linkedin)

    help_window.Content = content
    help_window.ShowDialog()


def _ndev_attach_header(window, callback):
    """Custom title bar: title | ? Help | - | maximize | X.

    Keep the original pyRevit window content and its keyboard handling.
    A two-pixel black client-area border remains visible without native chrome.
    """
    original_content = window.Content
    if original_content is None:
        return

    window.Title = _ndev_title(window.Title)
    navy = SolidColorBrush(Color.FromRgb(28, 42, 61))
    cyan = SolidColorBrush(Color.FromRgb(0, 165, 194))

    wrapper = DockPanel()
    wrapper.LastChildFill = True

    titlebar = Border()
    titlebar.Height = 38
    titlebar.Background = navy
    bar_content = DockPanel()
    bar_content.LastChildFill = True

    # Right-hand controls appear in one row INSIDE the custom title bar.
    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    DockPanel.SetDock(actions, Dock.Right)
    bar_content.Children.Add(actions)

    def add_button(text, width, tooltip, handler, background=None):
        button = Button()
        button.Content = text
        button.Width = width
        button.Height = 30
        button.Margin = Thickness(2, 4, 2, 4)
        button.Padding = Thickness(4, 0, 4, 0)
        button.ToolTip = tooltip
        button.Background = background if background is not None else navy
        button.Foreground = Brushes.White
        button.BorderThickness = Thickness(0)
        button.Click += handler
        actions.Children.Add(button)
        return button

    add_button('? Help', 82, 'Instructions, GitHub, LinkedIn', callback, cyan)
    add_button('-', 42, 'Minimize',
               lambda sender, args: setattr(window, 'WindowState', WindowState.Minimized))

    def toggle_maximize(sender, args):
        if window.WindowState == WindowState.Maximized:
            window.WindowState = WindowState.Normal
        else:
            window.WindowState = WindowState.Maximized

    max_button = add_button('[]', 42, 'Maximize', toggle_maximize)
    add_button('X', 42, 'Close', lambda sender, args: window.Close())

    def on_window_state_changed(sender, args):
        if window.WindowState == WindowState.Maximized:
            max_button.Content = '[]'
            max_button.ToolTip = 'Restore'
        else:
            max_button.Content = '[]'
            max_button.ToolTip = 'Maximize'

    window.StateChanged += on_window_state_changed

    caption = TextBlock()
    caption.Text = window.Title.replace('\r', ' ').replace('\n', ' | ')
    caption.Foreground = Brushes.White
    caption.FontWeight = FontWeights.SemiBold
    caption.VerticalAlignment = VerticalAlignment.Center
    caption.Margin = Thickness(12, 0, 8, 0)
    caption.TextTrimming = TextTrimming.CharacterEllipsis
    bar_content.Children.Add(caption)

    def drag_title(sender, args):
        if args.ClickCount == 2:
            toggle_maximize(None, None)
            args.Handled = True
        else:
            try:
                window.DragMove()
            except Exception:
                pass

    titlebar.MouseLeftButtonDown += drag_title
    titlebar.Child = bar_content
    DockPanel.SetDock(titlebar, Dock.Top)

    # Preserve the original input/tab/list content and its Namescope.
    window.Content = None
    wrapper.Children.Add(titlebar)
    wrapper.Children.Add(original_content)

    border = Border()
    border.BorderBrush = Brushes.Black
    border.BorderThickness = Thickness(2)
    border.SnapsToDevicePixels = True
    border.Child = wrapper
    window.Content = border

    window.WindowStyle = getattr(WindowStyle, 'None')
    chrome = WindowChrome()
    chrome.CaptionHeight = 0.0  # Buttons remain clickable in the custom caption.
    chrome.ResizeBorderThickness = Thickness(6)
    chrome.GlassFrameThickness = Thickness(0)
    chrome.CornerRadius = CornerRadius(0)
    WindowChrome.SetWindowChrome(window, chrome)

    # Some pyRevit dialogs size to content (Height can be NaN).
    # They grow automatically; dialogs with an explicit height get the 38px bar.
    try:
        from System import Double
        if not Double.IsNaN(window.Height):
            window.Height += 38
    except Exception:
        pass


class NdevSavedPositionSelector(_NATIVE_SELECT):
    """Retains pyRevit's original list, filtering and Select buttons."""

    def _setup(self, **kwargs):
        _NATIVE_SELECT._setup(self, **kwargs)
        _ndev_attach_header(self, self._show_ndev_help)

    def _show_ndev_help(self, sender, args):
        _ndev_show_help(self)

    @classmethod
    def show(cls, *args, **kwargs):
        kwargs['title'] = _ndev_title(kwargs.get('title'))
        return super(NdevSavedPositionSelector, cls).show(*args, **kwargs)


class NdevMainMenu(_NATIVE_SWITCH):
    """Native pyRevit seven-option command menu plus Ndev Help header."""

    def _setup(self, **kwargs):
        _NATIVE_SWITCH._setup(self, **kwargs)
        _ndev_attach_header(self, self._show_ndev_help)

    def _show_ndev_help(self, sender, args):
        _ndev_show_help(self)

    @classmethod
    def show(cls, *args, **kwargs):
        kwargs['title'] = _ndev_title(kwargs.get('title'))
        return super(NdevMainMenu, cls).show(*args, **kwargs)


class NdevStringInput(_NATIVE_VALUE):
    """Native pyRevit input/validation with same Ndev title and Help."""

    def _setup(self, **kwargs):
        _NATIVE_VALUE._setup(self, **kwargs)
        _ndev_attach_header(self, self._show_ndev_help)

    def _show_ndev_help(self, sender, args):
        _ndev_show_help(self)


def _ndev_ask_for_string(default=None, prompt=None, title=None, **kwargs):
    # Same standard pyRevit GetValueWindow used by forms.ask_for_string().
    return NdevStringInput.show(
        None,
        value_type='string',
        default=default,
        prompt=prompt,
        title=_ndev_title(title),
        **kwargs
    )


# Native TaskDialogs do not have a customizable upper-right header. For
# confirmations and information windows use a simple WPF equivalent with
# the SAME Yes/No/OK return behavior, and the same Help UI as above.


class NdevMessageWindow(Window):
    def __init__(self, message, title, yes=False, no=False):
        Window.__init__(self)
        self.Title = _ndev_title(title)
        self.Width = 570
        self.Height = min(620, max(235, 150 + len(str(message).splitlines()) * 18))
        self.MinHeight = 225
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.ShowInTaskbar = False
        self.answer = False

        root = DockPanel()
        root.Margin = Thickness(10, 6, 10, 12)

        actions = StackPanel()
        actions.Orientation = Orientation.Horizontal
        actions.HorizontalAlignment = HorizontalAlignment.Right
        actions.Margin = Thickness(6, 8, 8, 3)
        DockPanel.SetDock(actions, Dock.Bottom)

        if yes or no:
            positive = Button()
            positive.Content = 'Yes'
            positive.Width = 86
            positive.Height = 30
            positive.Margin = Thickness(6, 0, 0, 0)
            positive.Click += self._accept
            actions.Children.Add(positive)

            negative = Button()
            negative.Content = 'No'
            negative.Width = 86
            negative.Height = 30
            negative.Margin = Thickness(6, 0, 0, 0)
            negative.Click += self._decline
            actions.Children.Add(negative)
        else:
            okay = Button()
            okay.Content = 'OK'
            okay.Width = 86
            okay.Height = 30
            okay.Margin = Thickness(6, 0, 0, 0)
            okay.Click += self._accept
            actions.Children.Add(okay)

        root.Children.Add(actions)
        scroll = ScrollViewer()
        scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        scroll.Margin = Thickness(12, 6, 12, 2)
        body = TextBlock()
        body.Text = str(message)
        body.TextWrapping = TextWrapping.Wrap
        scroll.Content = body
        root.Children.Add(scroll)
        self.Content = root
        _ndev_attach_header(self, self._show_ndev_help)

    def _accept(self, sender, args):
        self.answer = True
        self.Close()

    def _decline(self, sender, args):
        self.answer = False
        self.Close()

    def _show_ndev_help(self, sender, args):
        _ndev_show_help(self)


def _ndev_alert(message, **kwargs):
    title = _ndev_title(kwargs.pop('title', None))
    win = NdevMessageWindow(
        message,
        title,
        yes=kwargs.get('yes', False),
        no=kwargs.get('no', False)
    )
    win.ShowDialog()
    if kwargs.get('exitscript', False):
        script.exit()
    return win.answer


class _NdevFormsAdapter(object):
    """Route ONLY this script's windows, without changing logic or pyRevit."""
    SelectFromList = NdevSavedPositionSelector
    CommandSwitchWindow = NdevMainMenu
    alert = staticmethod(_ndev_alert)
    ask_for_string = staticmethod(_ndev_ask_for_string)

    def __getattr__(self, name):
        return getattr(_NATIVE_FORMS, name)


# The existing functions below continue to call forms.* without rewriting.
forms = _NdevFormsAdapter()


if REVIT_VERSION not in SUPPORTED_VERSIONS:

    forms.alert(
        "This tool supports:\n\n"
        "Revit 2022\n"
        "Revit 2023\n"
        "Revit 2024\n"
        "Revit 2025\n"
        "Revit 2026\n"
        "Revit 2027\n\n"
        "Current Version: {}".format(
            REVIT_VERSION
        ),
        title="Ndev Tools - Viewport Position Manager",
        exitscript=True
    )




# ============================================================
# CHOOSE SAVED POSITION
# ============================================================

def choose_saved_position(
        positions,
        title="Select Saved Position"
):

    if not positions:

        forms.alert(
            "No saved positions exist for Revit {}."
            .format(
                REVIT_VERSION
            ),
            title="Viewport Position Manager"
        )

        return None


    display_items = []
    lookup = {}


    for index, position in enumerate(
            positions
    ):

        name = position.get(
            "name",
            "Position {}".format(
                index + 1
            )
        )


        x = float(
            position.get(
                "x",
                0.0
            )
        )


        y = float(
            position.get(
                "y",
                0.0
            )
        )


        source_sheet = (
            position.get(
                "source_sheet_number",
                ""
            )
        )


        display_name = (
            "{} | X: {:.4f} | Y: {:.4f}"
            .format(
                name,
                x,
                y
            )
        )


        if source_sheet:

            display_name += (
                " | Source: {}"
                .format(
                    source_sheet
                )
            )


        display_items.append(
            display_name
        )


        lookup[
            display_name
        ] = index


    selected = NdevSavedPositionSelector.show(
        display_items,
        title="Ndev Tools - {}".format(title),
        button_name="Use Position",
        multiselect=False
    )


    if not selected:

        return None


    return lookup[
        selected
    ]


# ============================================================
# CAPTURE REFERENCE POSITION
# ============================================================

def capture_reference_position():

    viewport_data = (
        select_reference_viewport()
    )


    if viewport_data is None:

        return None


    viewport = viewport_data[
        "viewport"
    ]

    view = viewport_data[
        "view"
    ]

    sheet = viewport_data[
        "sheet"
    ]


    # Match the same hidden-visibility reference used when APPLYING X/Y.
    # Otherwise saved coordinates include visible annotations/links while
    # target viewport coordinates are measured with those elements hidden.
    center = capture_viewport_position_with_hidden_v8(viewport, view)
    if center is None:
        return None


    return {
        "x":
            center.X,

        "y":
            center.Y,

        "viewport_id":
            id_value(
                viewport.Id
            ),

        "view_name":
            view.Name,

        "sheet_number":
            sheet.SheetNumber,

        "sheet_name":
            sheet.Name
    }


# ============================================================
# SAVE NEW POSITION
# ============================================================

def save_new_position():

    positions = (
        load_positions()
    )


    # --------------------------------------------------------
    # MAX 10
    # --------------------------------------------------------

    if len(positions) >= MAX_POSITIONS:

        forms.alert(
            "You already have {} saved positions "
            "for Revit {}.\n\n"
            "Delete or overwrite an existing position first."
            .format(
                MAX_POSITIONS,
                REVIT_VERSION
            ),
            title="Maximum Positions Reached"
        )

        return


    # --------------------------------------------------------
    # ONLY NOW ASK FOR REFERENCE VIEWPORT
    # --------------------------------------------------------

    captured = (
        capture_reference_position()
    )


    if captured is None:

        return


    # --------------------------------------------------------
    # SHOW ACQUIRED POSITION
    # --------------------------------------------------------

    continue_save = forms.alert(
        (
            "POSITION ACQUIRED\n\n"
            "View:\n{}\n\n"
            "Sheet:\n{} - {}\n\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Save this position?"
        ).format(
            captured["view_name"],
            captured["sheet_number"],
            captured["sheet_name"],
            captured["x"],
            captured["y"]
        ),
        title="Save Viewport Position",
        yes=True,
        no=True
    )


    if not continue_save:

        return


    # --------------------------------------------------------
    # ASK NAME
    # --------------------------------------------------------

    name = forms.ask_for_string(
        prompt=(
            "Enter a name for this viewport position.\n\n"
            "Examples:\n"
            "PLAN - CENTER\n"
            "PLAN - LEFT\n"
            "PLAN - RIGHT\n"
            "SECTION - TOP\n"
            "DETAIL - LOWER RIGHT"
        ),
        title="Position Name"
    )


    if not name:

        return


    name = name.strip()


    if not name:

        return


    # --------------------------------------------------------
    # DUPLICATE NAME CHECK
    # --------------------------------------------------------

    if name_exists(
            positions,
            name
    ):

        forms.alert(
            "A saved position named '{}' already exists."
            .format(
                name
            ),
            title="Duplicate Position Name"
        )

        return


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    position_record = {

        "name":
            name,

        "x":
            captured["x"],

        "y":
            captured["y"],

        "revit_version":
            REVIT_VERSION,

        "source_view_name":
            captured["view_name"],

        "source_sheet_number":
            captured["sheet_number"],

        "source_sheet_name":
            captured["sheet_name"]
    }


    positions.append(
        position_record
    )


    save_positions(
        positions
    )


    forms.alert(
        (
            "POSITION SAVED\n\n"
            "Name: {}\n"
            "Revit: {}\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Saved Positions: {} / {}"
        ).format(
            name,
            REVIT_VERSION,
            captured["x"],
            captured["y"],
            len(positions),
            MAX_POSITIONS
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# APPLY POSITION TO TARGET VIEWPORTS
# ============================================================

# ============================================================
# V8 VISIBILITY: USED WHILE READING AND MOVING VIEWPORT COORDINATES
# Capturing and applying saved X/Y now use the same hidden-state basis.
# ============================================================

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
# CAPTURE SAVED X/Y WITH THE SAME V8 VISIBILITY AS APPLY
# ============================================================

def capture_viewport_position_with_hidden_v8(viewport, view):
    """Read the reference viewport center with all V8 groups/links hidden.

    Used by Save New, Overwrite, and Capture + Apply. A separate transaction
    group ensures original visibility/template are restored and prevents
    partial edits if the capture fails. This function does NOT move viewport.
    """
    group = DB.TransactionGroup(doc, 'Capture Viewport Position - V8 - {}'.format(view.Name))
    group_active = False
    tx = None
    stage = 'Starting reference capture'
    try:
        if group.Start() != DB.TransactionStatus.Started:
            raise Exception('Cannot start reference capture transaction group')
        group_active = True

        stage = 'Temporarily hiding V/G categories and Revit links'
        tx = _begin_transaction('1 - Hide V/G and links for reference capture')
        state = save_and_hide_view_for_placement(view)
        _finish_transaction(tx, stage)
        tx = None

        stage = 'Reading viewport X/Y with visibility hidden'
        tx = _begin_transaction('2 - Read hidden-visibility viewport center')
        doc.Regenerate()
        center = get_viewport_position(viewport)
        _finish_transaction(tx, stage)
        tx = None

        stage = 'Restoring original V/G, links, and view template'
        tx = _begin_transaction('3 - Restore view after reference capture')
        restore_view_after_placement(view, state)
        _finish_transaction(tx, stage)
        tx = None

        stage = 'Finishing reference capture'
        if group.Assimilate() != DB.TransactionStatus.Committed:
            raise Exception('Could not complete reference capture transaction group')
        group_active = False
        return center

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
                error = '{}; IMPORTANT: rollback failed: {}'.format(error, rollback_error)
        forms.alert(
            'Reference viewport position was NOT captured.\n\n'
            'Stage: {}\n\n{}'.format(stage, error),
            title='Viewport Position Manager - Capture Error'
        )
        return None


def apply_position_to_targets(x, y, position_name, exclude_viewport_id=None):
    """Apply X/Y WHILE V/G + Revit Links are hidden, then restore V/G.

    Used by both Apply Saved Position and Capture New Position + Apply.
    Does not touch any of the other saved-position/menu functions.
    """
    target_data = select_target_viewports(exclude_viewport_id)
    if not target_data:
        return

    confirm = forms.alert(
        ("POSITION:\n{}\n\nX: {:.4f}\nY: {:.4f}\n\n"
         "TARGET VIEWPORTS: {}\n\n"
         "Apply this position to all selected viewports?").format(
             position_name, x, y, len(target_data)),
        title="Apply Viewport Position", yes=True, no=True
    )
    if not confirm:
        return

    successful = []
    failed = []

    for data in target_data:
        viewport = data['viewport']
        view = data['view']
        sheet = data['sheet']
        group = DB.TransactionGroup(
            doc, 'Apply Viewport Position with Original VG - {}'.format(view.Name)
        )
        group_active = False
        transaction = None
        stage = 'Starting viewport repositioning'
        try:
            if group.Start() != DB.TransactionStatus.Started:
                raise Exception('Cannot start transaction group')
            group_active = True

            # 1. SAVE TEMPLATE/ORIGINAL VISIBILITY; HIDE ALL FOUR GROUPS + LINKS.
            stage = 'Saving and temporarily hiding V/G and Revit Links'
            transaction = _begin_transaction('1 - Hide V/G before moving viewport')
            visibility = save_and_hide_view_for_placement(view)
            _finish_transaction(transaction, stage)
            transaction = None

            # 2. MOVE USING THE HIDDEN VIEW'S BOUNDING BOX.
            stage = 'Applying exact saved X/Y while visibility is hidden'
            transaction = _begin_transaction('2 - Apply exact viewport position')
            was_pinned = bool(viewport.Pinned)
            if was_pinned:
                viewport.Pinned = False

            doc.Regenerate()
            current_center = viewport.GetBoxCenter()
            target_center = DB.XYZ(float(x), float(y), current_center.Z)
            viewport.SetBoxCenter(target_center)

            # Restore original pin state, BEFORE visibility returns.
            if was_pinned:
                viewport.Pinned = True
            _finish_transaction(transaction, stage)
            transaction = None

            # 3. RESTORE THE ORIGINAL CATEGORY FLAGS, LINKS AND VIEW TEMPLATE.
            # DO NOT reposition after restore: visible links change box extents.
            stage = 'Restoring previous V/G and original view template'
            transaction = _begin_transaction('3 - Restore original view graphics')
            restore_view_after_placement(view, visibility)
            _finish_transaction(transaction, stage)
            transaction = None

            stage = 'Finalizing viewport position'
            if group.Assimilate() != DB.TransactionStatus.Committed:
                raise Exception('Cannot finalize transaction group')
            group_active = False
            successful.append('{} | {} | {}'.format(
                sheet.SheetNumber, sheet.Name, view.Name))

        except Exception as error:
            if transaction is not None:
                try:
                    if transaction.GetStatus() == DB.TransactionStatus.Started:
                        transaction.RollBack()
                except Exception:
                    pass
            if group_active:
                try:
                    if group.GetStatus() == DB.TransactionStatus.Started:
                        group.RollBack()
                except Exception as rollback_error:
                    error = '{} | IMPORTANT: rollback failed: {}'.format(
                        error, rollback_error)
            failed.append('{} | {} | {}: {}'.format(
                sheet.SheetNumber, view.Name, stage, error))

    message = (
        'VIEWPORT POSITION COMPLETE\n\n'
        'Position: {}\nX: {:.4f}\nY: {:.4f}\n\n'
        'Selected: {}\nUpdated: {}\nFailed: {}'
    ).format(position_name, x, y,
             len(target_data), len(successful), len(failed))
    if failed:
        message += '\n\nFAILED:\n' + '\n'.join(failed)
    forms.alert(message, title='Viewport Position Manager')



# ============================================================
# APPLY SAVED POSITION
# ============================================================

def apply_saved_position():

    positions = (
        load_positions()
    )


    if not positions:

        forms.alert(
            (
                "No positions are saved for Revit {}.\n\n"
                "Use 'Save New Position' first."
            ).format(
                REVIT_VERSION
            ),
            title="Viewport Position Manager"
        )

        return


    # --------------------------------------------------------
    # GO STRAIGHT TO SAVED LIST
    #
    # DO NOT ask for a new viewport here.
    # --------------------------------------------------------

    index = (
        choose_saved_position(
            positions,
            "Select Saved Position - Revit {}".format(
                REVIT_VERSION
            )
        )
    )


    if index is None:

        return


    position = (
        positions[index]
    )


    x = float(
        position["x"]
    )


    y = float(
        position["y"]
    )


    name = position[
        "name"
    ]


    apply_position_to_targets(
        x,
        y,
        name
    )


# ============================================================
# CAPTURE NEW POSITION AND APPLY IMMEDIATELY
#
# Does NOT save unless user wants to.
# ============================================================

def capture_and_apply():

    captured = (
        capture_reference_position()
    )


    if captured is None:

        return


    # --------------------------------------------------------
    # ASK WHETHER TO SAVE
    # --------------------------------------------------------

    should_save = forms.alert(
        (
            "REFERENCE POSITION ACQUIRED\n\n"
            "View: {}\n"
            "Sheet: {}\n\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Do you also want to save this position "
            "for future use?"
        ).format(
            captured["view_name"],
            captured["sheet_number"],
            captured["x"],
            captured["y"]
        ),
        title="Save Position?",
        yes=True,
        no=True
    )


    position_name = (
        "Temporary Position"
    )


    # --------------------------------------------------------
    # SAVE IF YES
    # --------------------------------------------------------

    if should_save:

        positions = (
            load_positions()
        )


        if len(positions) >= MAX_POSITIONS:

            forms.alert(
                (
                    "The position will still be applied, "
                    "but it cannot be saved because Revit {} "
                    "already has {} saved positions."
                ).format(
                    REVIT_VERSION,
                    MAX_POSITIONS
                ),
                title="Position Memory Full"
            )


        else:

            name = forms.ask_for_string(
                prompt="Enter a name for this position:",
                title="Position Name"
            )


            if name:

                name = name.strip()


                if name:

                    if name_exists(
                            positions,
                            name
                    ):

                        forms.alert(
                            (
                                "A position named '{}' already exists.\n\n"
                                "The acquired position will still be applied "
                                "but will not be saved."
                            ).format(
                                name
                            ),
                            title="Duplicate Position Name"
                        )


                    else:

                        position_name = name


                        positions.append(
                            {
                                "name":
                                    name,

                                "x":
                                    captured["x"],

                                "y":
                                    captured["y"],

                                "revit_version":
                                    REVIT_VERSION,

                                "source_view_name":
                                    captured["view_name"],

                                "source_sheet_number":
                                    captured["sheet_number"],

                                "source_sheet_name":
                                    captured["sheet_name"]
                            }
                        )


                        save_positions(
                            positions
                        )


    # --------------------------------------------------------
    # APPLY
    # --------------------------------------------------------

    if position_name == "Temporary Position":

        position_name = (
            "From {} / {}".format(
                captured["sheet_number"],
                captured["view_name"]
            )
        )


    apply_position_to_targets(
        captured["x"],
        captured["y"],
        position_name,
        exclude_viewport_id=captured[
            "viewport_id"
        ]
    )


# ============================================================
# RENAME SAVED POSITION
# ============================================================

def rename_saved_position():

    positions = (
        load_positions()
    )


    index = (
        choose_saved_position(
            positions,
            "Select Position to Rename"
        )
    )


    if index is None:

        return


    old_name = (
        positions[index][
            "name"
        ]
    )


    new_name = forms.ask_for_string(
        default=old_name,
        prompt="Enter the new position name:",
        title="Rename Position"
    )


    if not new_name:

        return


    new_name = (
        new_name.strip()
    )


    if not new_name:

        return


    if name_exists(
            positions,
            new_name,
            ignore_index=index
    ):

        forms.alert(
            "A position named '{}' already exists."
            .format(
                new_name
            ),
            title="Duplicate Name"
        )

        return


    positions[
        index
    ]["name"] = new_name


    save_positions(
        positions
    )


    forms.alert(
        "'{}' renamed to '{}'."
        .format(
            old_name,
            new_name
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# OVERWRITE SAVED POSITION
# ============================================================

def overwrite_saved_position():

    positions = (
        load_positions()
    )


    index = (
        choose_saved_position(
            positions,
            "Select Position to Overwrite"
        )
    )


    if index is None:

        return


    old_position = (
        positions[index]
    )


    # --------------------------------------------------------
    # NOW SELECT NEW REFERENCE
    # --------------------------------------------------------

    captured = (
        capture_reference_position()
    )


    if captured is None:

        return


    confirm = forms.alert(
        (
            "OVERWRITE POSITION\n\n"
            "{}\n\n"
            "Old:\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "New:\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Continue?"
        ).format(
            old_position["name"],
            float(
                old_position["x"]
            ),
            float(
                old_position["y"]
            ),
            captured["x"],
            captured["y"]
        ),
        title="Overwrite Position",
        yes=True,
        no=True
    )


    if not confirm:

        return


    old_position[
        "x"
    ] = captured["x"]


    old_position[
        "y"
    ] = captured["y"]


    old_position[
        "source_view_name"
    ] = captured["view_name"]


    old_position[
        "source_sheet_number"
    ] = captured["sheet_number"]


    old_position[
        "source_sheet_name"
    ] = captured["sheet_name"]


    old_position[
        "revit_version"
    ] = REVIT_VERSION


    save_positions(
        positions
    )


    forms.alert(
        (
            "'{}' has been overwritten successfully."
        ).format(
            old_position["name"]
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# DELETE SAVED POSITION
# ============================================================

def delete_saved_position():

    positions = (
        load_positions()
    )


    index = (
        choose_saved_position(
            positions,
            "Select Position to Delete"
        )
    )


    if index is None:

        return


    name = (
        positions[index][
            "name"
        ]
    )


    confirm = forms.alert(
        "Delete saved position '{}'?"
        .format(
            name
        ),
        title="Delete Position",
        yes=True,
        no=True
    )


    if not confirm:

        return


    del positions[
        index
    ]


    save_positions(
        positions
    )


    forms.alert(
        (
            "'{}' deleted.\n\n"
            "Saved Positions: {} / {}"
        ).format(
            name,
            len(positions),
            MAX_POSITIONS
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# SHOW SAVED POSITIONS
# ============================================================

def show_saved_positions():

    positions = (
        load_positions()
    )


    if not positions:

        forms.alert(
            (
                "No saved positions exist for Revit {}."
            ).format(
                REVIT_VERSION
            ),
            title="Saved Positions"
        )

        return


    message = (
        "REVIT {}\n\n"
        "SAVED VIEWPORT POSITIONS\n"
        "--------------------------------\n\n"
    ).format(
        REVIT_VERSION
    )


    for index, position in enumerate(
            positions
    ):

        message += (
            "{}. {}\n"
            "   X: {:.4f}\n"
            "   Y: {:.4f}\n"
            "   Source Sheet: {}\n"
            "   Source View: {}\n\n"
        ).format(
            index + 1,
            position.get(
                "name",
                ""
            ),
            float(
                position.get(
                    "x",
                    0.0
                )
            ),
            float(
                position.get(
                    "y",
                    0.0
                )
            ),
            position.get(
                "source_sheet_number",
                "Unknown"
            ),
            position.get(
                "source_view_name",
                "Unknown"
            )
        )


    forms.alert(
        message,
        title="Saved Positions - Revit {}".format(
            REVIT_VERSION
        )
    )


# ============================================================
# MAIN MENU
# ============================================================

def main():

    positions = (
        load_positions()
    )


    menu_items = [
        "Apply Saved Position",
        "Save New Position",
        "Capture New Position + Apply",
        "Show Saved Positions",
        "Rename Saved Position",
        "Overwrite Saved Position",
        "Delete Saved Position"
    ]


    action = (
        forms.CommandSwitchWindow.show(
            menu_items,
            title=(
                "Ndev Tools - Viewport Position Manager - Revit {}"
                .format(
                    REVIT_VERSION
                )
            ),
            message=(
                "Saved Positions: {} / {}\n\n"
                "Apply = use an existing saved position.\n"
                "Save New = acquire a position from a viewport.\n"
                "Capture + Apply = use a new viewport position immediately."
                .format(
                    len(positions),
                    MAX_POSITIONS
                )
            )
        )
    )


    if not action:

        return


    # ========================================================
    # APPLY SAVED
    # ========================================================

    if action == "Apply Saved Position":

        apply_saved_position()


    # ========================================================
    # SAVE NEW
    # ========================================================

    elif action == "Save New Position":

        save_new_position()


    # ========================================================
    # CAPTURE AND APPLY
    # ========================================================

    elif action == "Capture New Position + Apply":

        capture_and_apply()


    # ========================================================
    # SHOW
    # ========================================================

    elif action == "Show Saved Positions":

        show_saved_positions()


    # ========================================================
    # RENAME
    # ========================================================

    elif action == "Rename Saved Position":

        rename_saved_position()


    # ========================================================
    # OVERWRITE
    # ========================================================

    elif action == "Overwrite Saved Position":

        overwrite_saved_position()


    # ========================================================
    # DELETE
    # ========================================================

    elif action == "Delete Saved Position":

        delete_saved_position()


# ============================================================
# RUN
# ============================================================

try:

    main()


except Exception as error:

    forms.alert(
        (
            "An error occurred.\n\n"
            "Revit Version: {}\n\n"
            "{}"
        ).format(
            REVIT_VERSION,
            error
        ),
        title="Viewport Position Manager - Error"
    )
