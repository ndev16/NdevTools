# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List
import math


# ============================================================
# NDEV TOOLS - CUSTOM TITLE BAR + HELP
# Same title-bar layout as the working Auto Detail Generator.
# Every list and result window uses Ndev Tools branding.
# Revit's native PickObject prompts remain unchanged.
# ============================================================

from pyrevit import script
import System
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import (Window, WindowStyle, WindowState, ResizeMode,
                            Thickness, CornerRadius, WindowStartupLocation,
                            TextWrapping, FontWeights, VerticalAlignment)
from System.Windows.Controls import (DockPanel, Dock, Grid, ColumnDefinition,
                                     StackPanel, Border, Button, TextBlock,
                                     ScrollViewer, Orientation)
from System.Windows.Media import Color, SolidColorBrush, Brushes
from System.Windows.Shell import WindowChrome

NDEV_TITLE = 'Ndev Tools - Deck Filled Region'
NDEV_GITHUB = 'https://github.com/ndev16'
NDEV_LINKEDIN = 'https://www.linkedin.com/in/nataraj016/'


def ndev_title(text):
    title = str(text) if text else 'Deck Filled Region'
    if title.lower().startswith('ndev tools'):
        return title
    return 'Ndev Tools - ' + title


def ndev_open_link(url):
    try:
        start = ProcessStartInfo(url)
        start.UseShellExecute = True
        Process.Start(start)
    except Exception as error:
        # Standard fallback: this error is outside the drawing transaction.
        ndev_alert('Unable to launch browser.\n\n{}\n\n{}'.format(url, error),
                    title=NDEV_TITLE + ' - Help')


def ndev_show_help(owner=None):
    """Reference instructions and clickable professional profile links."""
    window = Window()
    window.Title = NDEV_TITLE + ' - Help'
    window.Width = 530
    window.Height = 440
    window.MinWidth = 470
    window.ResizeMode = ResizeMode.NoResize
    window.ShowInTaskbar = False
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    if owner is not None:
        window.Owner = owner
        window.WindowStartupLocation = WindowStartupLocation.CenterOwner

    body = StackPanel()
    body.Margin = Thickness(20)
    heading = TextBlock()
    heading.Text = 'NDEV TOOLS | VULCRAFT DECK FILLED REGION'
    heading.FontWeight = FontWeights.Bold
    heading.Margin = Thickness(0, 0, 0, 12)
    body.Children.Add(heading)

    instructions = TextBlock()
    instructions.Text = (
        '1. Open a Section view in Revit.\n'
        '2. Select the structural deck floor.\n'
        '3. Choose a Vulcraft deck profile and its gage.\n'
        '4. Pick the LEFT END of a LOWER FLAT on the actual deck.\n'
        '5. Choose a filled-region type to create the profile.\n\n'
        'The clicked deck anchor determines horizontal phase and '
        'vertical position. The generated profile uses the existing '
        'deck dimensions; gage selection does not change that geometry.\n\n'
        'Supported profiles: 1.5C-36, 2C-36, 3C-36.'
    )
    instructions.TextWrapping = TextWrapping.Wrap
    instructions.Margin = Thickness(0, 0, 0, 16)
    body.Children.Add(instructions)

    github = Button()
    github.Content = 'GitHub  |  github.com/ndev16'
    github.Height = 34
    github.Margin = Thickness(0, 0, 0, 9)
    github.Click += lambda sender, args: ndev_open_link(NDEV_GITHUB)
    body.Children.Add(github)

    linkedin = Button()
    linkedin.Content = 'LinkedIn  |  linkedin.com/in/nataraj016'
    linkedin.Height = 34
    linkedin.Click += lambda sender, args: ndev_open_link(NDEV_LINKEDIN)
    body.Children.Add(linkedin)

    scroll = ScrollViewer()
    scroll.Content = body
    window.Content = scroll
    window.ShowDialog()


def ndev_attach_titlebar(window):
    """Add Help beside custom minimize, maximize, and close controls."""
    original = window.Content
    if original is None:
        return
    window.Title = ndev_title(window.Title)
    navy = SolidColorBrush(Color.FromRgb(28, 42, 61))
    accent = SolidColorBrush(Color.FromRgb(0, 165, 194))

    root = DockPanel()
    root.LastChildFill = True
    bar = Border()
    bar.Height = 38
    bar.Background = navy
    header = Grid()
    title_column = ColumnDefinition()
    header.ColumnDefinitions.Add(title_column)
    buttons_column = ColumnDefinition()
    buttons_column.Width = System.Windows.GridLength.Auto
    header.ColumnDefinitions.Add(buttons_column)

    label = TextBlock()
    label.Text = window.Title
    label.Foreground = Brushes.White
    label.FontWeight = FontWeights.SemiBold
    label.VerticalAlignment = VerticalAlignment.Center
    label.Margin = Thickness(12, 0, 0, 0)
    Grid.SetColumn(label, 0)
    header.Children.Add(label)

    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    Grid.SetColumn(actions, 1)
    header.Children.Add(actions)

    def add_button(label_text, width, tooltip, callback, background=None):
        button = Button()
        button.Content = label_text
        button.Width = width
        button.Height = 30
        button.Margin = Thickness(2, 4, 2, 4)
        button.Padding = Thickness(4, 0, 4, 0)
        button.ToolTip = tooltip
        button.BorderThickness = Thickness(0)
        button.Background = background if background else navy
        button.Foreground = Brushes.White
        button.Click += callback
        actions.Children.Add(button)
        return button

    add_button('? Help', 80, 'Help, GitHub, and LinkedIn',
               lambda sender, args: ndev_show_help(window), accent)
    add_button('-', 42, 'Minimize',
               lambda sender, args: setattr(window, 'WindowState', WindowState.Minimized))

    def toggle_maximize(sender, args):
        window.WindowState = (WindowState.Normal if window.WindowState == WindowState.Maximized
                              else WindowState.Maximized)

    add_button('[]', 42, 'Maximize / Restore', toggle_maximize)
    add_button('X', 42, 'Close', lambda sender, args: window.Close())

    def drag_bar(sender, args):
        if args.ClickCount == 2:
            toggle_maximize(None, None)
            args.Handled = True
        else:
            try:
                window.DragMove()
            except Exception:
                pass

    bar.MouseLeftButtonDown += drag_bar
    bar.Child = header
    DockPanel.SetDock(bar, Dock.Top)
    window.Content = None
    root.Children.Add(bar)
    root.Children.Add(original)
    window.Content = root

    window.WindowStyle = getattr(WindowStyle, 'None')
    # Original selector remains resizable with a custom but normal-feeling frame.
    chrome = WindowChrome()
    chrome.CaptionHeight = 0.0
    chrome.ResizeBorderThickness = Thickness(6)
    chrome.GlassFrameThickness = Thickness(0)
    chrome.CornerRadius = CornerRadius(0)
    WindowChrome.SetWindowChrome(window, chrome)
    window.Height = window.Height + 38


class NdevSelectFromList(forms.SelectFromList):
    """Original pyRevit single-select UI; title bar and Help added."""
    def _setup(self, **kwargs):
        forms.SelectFromList._setup(self, **kwargs)
        ndev_attach_titlebar(self)


def ndev_alert(message, title=None, exitscript=False, **kwargs):
    """Original informational/exit alerts with an Ndev Tools Help title bar."""
    window = Window()
    window.Title = ndev_title(title)
    window.Width = 580
    line_count = len(str(message).splitlines())
    window.Height = min(660, max(245, 165 + 19 * line_count))
    window.MinWidth = 440
    window.MinHeight = 220
    window.ResizeMode = ResizeMode.CanResize
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    window.ShowInTaskbar = False

    body = DockPanel()
    body.Margin = Thickness(16)
    scroll = ScrollViewer()
    text = TextBlock()
    text.Text = str(message)
    text.TextWrapping = TextWrapping.Wrap
    scroll.Content = text
    body.Children.Add(scroll)
    ok = Button()
    ok.Content = 'OK'
    ok.Width = 90
    ok.Height = 30
    ok.Margin = Thickness(0, 12, 0, 0)
    ok.HorizontalAlignment = System.Windows.HorizontalAlignment.Right
    ok.Click += lambda sender, args: window.Close()
    DockPanel.SetDock(ok, Dock.Bottom)
    # DockPanel's last-child fill remains the scroller.
    body.Children.Remove(scroll)
    body.Children.Add(ok)
    body.Children.Add(scroll)
    window.Content = body
    ndev_attach_titlebar(window)
    window.ShowDialog()
    if exitscript:
        script.exit()
    return None


doc = revit.doc
uidoc = revit.uidoc
view = revit.active_view


# ============================================================
# VULCRAFT DECK -> CONCRETE FILLED REGION
#
# IMPORTANT:
#
# After selecting the floor, the script asks you to click:
#
#     LEFT END OF A LOWER FLAT
#
# on the REAL Revit deck profile.
#
# That point controls:
#   1. Horizontal phase
#   2. Vertical position
#
# This fixes the shifting problem.
# ============================================================


# ============================================================
# DECK LIBRARY
#
# Dimensions are inches.
#
# bottom_flat = lower horizontal portion
# top_flat    = upper horizontal portion
# ============================================================

DECK_LIBRARY = {

    "1.5C-36": {

        "depth": 1.5,
        "pitch": 6.0,

        # IMPORTANT CORRECTION
        "bottom_flat": 3.375,   # 3 3/8"
        "top_flat": 1.625,      # 1 5/8"

        "gages": [
            "24",
            "22",
            "20",
            "18"
        ]
    },


    "2C-36": {

        "depth": 2.0,
        "pitch": 12.0,

        "bottom_flat": 5.0,
        "top_flat": 5.0,

        "gages": [
            "22",
            "20",
            "18",
            "16"
        ]
    },


    "3C-36": {

        "depth": 3.0,
        "pitch": 12.0,

        "bottom_flat": 4.75,
        "top_flat": 4.75,

        "gages": [
            "22",
            "20",
            "18",
            "16"
        ]
    }
}


# ============================================================
# REVIT TOLERANCES
# ============================================================

SHORT_CURVE_TOL = doc.Application.ShortCurveTolerance

TOL = SHORT_CURVE_TOL * 1.25

FACE_ALIGNMENT = 0.999


# ============================================================
# CONVERT INCH -> REVIT INTERNAL FEET
# ============================================================

def inch(value):

    return float(value) / 12.0


# ============================================================
# CREATE SAFE REVIT LINE
# ============================================================

def safe_line(point1, point2):

    if point1 is None or point2 is None:
        return None

    try:

        if point1.DistanceTo(point2) <= TOL:
            return None

        return DB.Line.CreateBound(
            point1,
            point2
        )

    except:
        return None


# ============================================================
# CHECK VIEW
# ============================================================

if view.ViewType != DB.ViewType.Section:

    ndev_alert(
        "Please open a Section view first.",
        title="Deck Filled Region",
        exitscript=True
    )


# ============================================================
# SELECT FLOOR
# ============================================================

try:

    floor_reference = uidoc.Selection.PickObject(
        ObjectType.Element,
        "Select the structural deck floor"
    )

    floor = doc.GetElement(
        floor_reference.ElementId
    )

except:

    ndev_alert(
        "Selection cancelled.",
        title="Deck Filled Region",
        exitscript=True
    )


# ============================================================
# VERIFY FLOOR
# ============================================================

if floor.Category is None:

    ndev_alert(
        "Selected element has no category.",
        exitscript=True
    )


if floor.Category.Id.IntegerValue != int(
        DB.BuiltInCategory.OST_Floors
):

    ndev_alert(
        "Selected element is not a Floor.",
        exitscript=True
    )


# ============================================================
# SELECT DECK TYPE
# ============================================================

selected_deck = NdevSelectFromList.show(

    sorted(
        DECK_LIBRARY.keys()
    ),

    title="Select Vulcraft Deck Type",

    button_name="Select",

    multiselect=False
)


if not selected_deck:

    ndev_alert(
        "No deck selected.",
        exitscript=True
    )


deck_data = DECK_LIBRARY[
    selected_deck
]


# ============================================================
# SELECT GAGE
# ============================================================

selected_gage = NdevSelectFromList.show(

    deck_data["gages"],

    title="Select {} Gage".format(
        selected_deck
    ),

    button_name="Select",

    multiselect=False
)


if not selected_gage:

    ndev_alert(
        "No gage selected.",
        exitscript=True
    )


# ============================================================
# IMPORTANT
#
# PICK A REAL DECK ANCHOR
#
# Pick:
#
#        LEFT END
#        OF A LOWER FLAT
#
#
# Example:
#
#
#                  _______
#                 /       \
#                /         \
#
#      X________/           \_____
#
#      ^
#      CLICK HERE
#
#
# X becomes profile coordinate 0,0.
#
# ============================================================

try:

    anchor_reference = uidoc.Selection.PickObject(

        ObjectType.PointOnElement,

        "Pick LEFT END of a LOWER FLAT on the REAL deck profile"

    )


    anchor_point = anchor_reference.GlobalPoint


except:

    ndev_alert(
        "Deck anchor selection cancelled.",
        title="Deck Filled Region",
        exitscript=True
    )


if anchor_point is None:

    ndev_alert(
        "Revit could not read the clicked deck point.",
        title="Deck Filled Region",
        exitscript=True
    )


# ============================================================
# FILLED REGION TYPES
# ============================================================

region_types = (

    DB.FilteredElementCollector(doc)

    .OfClass(
        DB.FilledRegionType
    )

    .ToElements()
)


region_dictionary = {}


for region_type in region_types:

    try:

        parameter = region_type.get_Parameter(
            DB.BuiltInParameter.SYMBOL_NAME_PARAM
        )

        if parameter:

            region_name = parameter.AsString()

            if region_name:

                region_dictionary[
                    region_name
                ] = region_type

    except:
        pass


if not region_dictionary:

    ndev_alert(
        "No Filled Region Types found.",
        exitscript=True
    )


selected_region_name = NdevSelectFromList.show(

    sorted(
        region_dictionary.keys()
    ),

    title="Select Filled Region Type",

    button_name="Create",

    multiselect=False
)


if not selected_region_name:

    ndev_alert(
        "No Filled Region selected.",
        exitscript=True
    )


filled_region_type = region_dictionary[
    selected_region_name
]


# ============================================================
# DECK DIMENSIONS
# ============================================================

deck_depth = inch(
    deck_data["depth"]
)


deck_pitch = inch(
    deck_data["pitch"]
)


bottom_flat = inch(
    deck_data["bottom_flat"]
)


top_flat = inch(
    deck_data["top_flat"]
)


# ============================================================
# SLOPED WEB HORIZONTAL RUN
# ============================================================

side_run = (

    deck_pitch
    - bottom_flat
    - top_flat

) / 2.0


if side_run <= 0:

    ndev_alert(
        "Invalid deck profile dimensions.",
        exitscript=True
    )


# ============================================================
# ONE DECK REPEAT
#
#
#                     TOP FLAT
#                   ___________
#                  /           \
#                 /             \
#  ______________/               \______________
#
#   BOTTOM FLAT
#
#
# Coordinate 0,0:
#
# LEFT END OF LOWER FLAT
#
# Profile goes UP into slab.
# ============================================================

PROFILE = [

    (
        0.0,
        0.0
    ),

    (
        bottom_flat,
        0.0
    ),

    (
        bottom_flat + side_run,
        deck_depth
    ),

    (
        bottom_flat
        + side_run
        + top_flat,
        deck_depth
    ),

    (
        deck_pitch,
        0.0
    )
]


# ============================================================
# VIEW COORDINATE SYSTEM
# ============================================================

view_origin = view.Origin


view_direction = (
    view.ViewDirection.Normalize()
)


right_direction = (
    view.RightDirection.Normalize()
)


up_direction = (
    view.UpDirection.Normalize()
)


# ============================================================
# MODEL XYZ -> VIEW U/V
# ============================================================

def xyz_to_uv(point):

    vector = (
        point
        - view_origin
    )


    horizontal = vector.DotProduct(
        right_direction
    )


    vertical = vector.DotProduct(
        up_direction
    )


    return (
        horizontal,
        vertical
    )


# ============================================================
# VIEW U/V -> MODEL XYZ
# ============================================================

def uv_to_xyz(horizontal, vertical):

    return (

        view_origin

        + right_direction.Multiply(
            horizontal
        )

        + up_direction.Multiply(
            vertical
        )

    )


# ============================================================
# CONVERT CLICKED DECK POINT
# ============================================================

anchor_u, anchor_v = xyz_to_uv(
    anchor_point
)


# ============================================================
# GET FLOOR GEOMETRY
# ============================================================

options = DB.Options()

options.ComputeReferences = True

options.IncludeNonVisibleObjects = True

options.View = view


geometry = floor.get_Geometry(
    options
)


if geometry is None:

    ndev_alert(
        "Could not read Floor geometry.",
        exitscript=True
    )


# ============================================================
# COLLECT SOLIDS
# ============================================================

solids = []


def collect_solids(
        geometry_element
):

    for obj in geometry_element:

        if isinstance(
            obj,
            DB.Solid
        ):

            try:

                if obj.Faces.Size > 0:

                    solids.append(
                        obj
                    )

            except:
                pass


        elif isinstance(
            obj,
            DB.GeometryInstance
        ):

            try:

                collect_solids(
                    obj.GetInstanceGeometry()
                )

            except:
                pass


collect_solids(
    geometry
)


if not solids:

    ndev_alert(
        "No Floor solid geometry found.",
        exitscript=True
    )


# ============================================================
# DISTANCE TO SECTION PLANE
# ============================================================

def section_distance(point):

    vector = (
        point
        - view_origin
    )

    return abs(
        vector.DotProduct(
            view_direction
        )
    )


# ============================================================
# FIND SECTION CUT FACE
# ============================================================

candidate_faces = []


for solid in solids:

    for face in solid.Faces:

        if not isinstance(
            face,
            DB.PlanarFace
        ):

            continue


        try:

            normal = (
                face.FaceNormal.Normalize()
            )


            alignment = abs(
                normal.DotProduct(
                    view_direction
                )
            )


            if alignment >= FACE_ALIGNMENT:

                candidate_faces.append(

                    (

                        section_distance(
                            face.Origin
                        ),

                        face.Area,

                        face

                    )

                )

        except:
            pass


if not candidate_faces:

    ndev_alert(
        "Could not find Floor cut face.",
        exitscript=True
    )


candidate_faces.sort(

    key=lambda item: (

        item[0],

        -item[1]

    )
)


cut_face = candidate_faces[0][2]


# ============================================================
# FLOOR BOUNDARY LOOPS
# ============================================================

try:

    loops = list(
        cut_face.GetEdgesAsCurveLoops()
    )

except:

    loops = []


if not loops:

    ndev_alert(
        "No Floor boundary found.",
        exitscript=True
    )


# ============================================================
# FIND LARGEST FLOOR LOOP
# ============================================================

largest_loop = None

largest_length = 0.0


for loop in loops:

    length = 0.0


    try:

        for curve in loop:

            length += curve.Length

    except:
        continue


    if length > largest_length:

        largest_length = length

        largest_loop = loop


if largest_loop is None:

    ndev_alert(
        "Could not determine Floor perimeter.",
        exitscript=True
    )


# ============================================================
# GET FLOOR POINTS
# ============================================================

floor_points = []


for curve in largest_loop:

    try:

        floor_points.append(
            curve.GetEndPoint(0)
        )

        floor_points.append(
            curve.GetEndPoint(1)
        )

    except:
        pass


if not floor_points:

    ndev_alert(
        "Could not read Floor boundary.",
        exitscript=True
    )


floor_uv_points = [

    xyz_to_uv(point)

    for point in floor_points

]


# ============================================================
# FLOOR EXTENTS
# ============================================================

floor_left = min(

    [
        point[0]
        for point in floor_uv_points
    ]

)


floor_right = max(

    [
        point[0]
        for point in floor_uv_points
    ]

)


floor_top = max(

    [
        point[1]
        for point in floor_uv_points
    ]

)


floor_width = (
    floor_right
    - floor_left
)


if floor_width <= TOL:

    ndev_alert(
        "Floor width could not be determined.",
        exitscript=True
    )


# ============================================================
# IMPORTANT
#
# Vertical deck baseline comes from USER CLICK.
#
# We no longer guess floor_bottom.
#
# This makes the generated profile line up vertically with
# the real Revit deck.
# ============================================================

deck_baseline = anchor_v


# ============================================================
# APPEND UNIQUE UV POINT
# ============================================================

def append_point(
        collection,
        point
):

    if not collection:

        collection.append(
            point
        )

        return


    previous = collection[-1]


    dx = (
        point[0]
        - previous[0]
    )


    dy = (
        point[1]
        - previous[1]
    )


    distance = math.sqrt(
        dx * dx
        + dy * dy
    )


    if distance > TOL:

        collection.append(
            point
        )


# ============================================================
# CLIP A PROFILE SEGMENT TO FLOOR LEFT/RIGHT
#
# Segment coordinates are monotonically increasing in X.
# ============================================================

def clip_segment(
        point1,
        point2,
        left_limit,
        right_limit
):

    x1 = point1[0]
    y1 = point1[1]

    x2 = point2[0]
    y2 = point2[1]


    # completely left
    if x2 < left_limit - TOL:
        return None


    # completely right
    if x1 > right_limit + TOL:
        return None


    clipped_x1 = x1
    clipped_y1 = y1

    clipped_x2 = x2
    clipped_y2 = y2


    # --------------------------------------------------------
    # CLIP LEFT
    # --------------------------------------------------------

    if x1 < left_limit:

        if abs(x2 - x1) <= TOL:
            return None


        ratio = (
            (left_limit - x1)
            /
            (x2 - x1)
        )


        clipped_x1 = left_limit


        clipped_y1 = (

            y1

            + ratio
            * (y2 - y1)

        )


    # --------------------------------------------------------
    # CLIP RIGHT
    # --------------------------------------------------------

    if x2 > right_limit:

        if abs(x2 - x1) <= TOL:
            return None


        ratio = (
            (right_limit - x1)
            /
            (x2 - x1)
        )


        clipped_x2 = right_limit


        clipped_y2 = (

            y1

            + ratio
            * (y2 - y1)

        )


    return (

        (
            clipped_x1,
            clipped_y1
        ),

        (
            clipped_x2,
            clipped_y2
        )

    )


# ============================================================
# DETERMINE FIRST PROFILE REPEAT
#
# anchor_u represents x=0 of one real deck repeat.
#
# We work backwards by whole pitches until we're left
# of the Floor boundary.
# ============================================================

repeat_number = int(
    math.floor(
        (
            floor_left
            - anchor_u
        )
        /
        deck_pitch
    )
)


first_repeat = (

    anchor_u

    + repeat_number
    * deck_pitch

)


# Start one repeat earlier for safe clipping
first_repeat -= deck_pitch


# ============================================================
# GENERATE DECK PROFILE
# ============================================================

deck_points = []


repeat_start = first_repeat


while repeat_start <= floor_right + deck_pitch:


    for index in range(
        len(PROFILE) - 1
    ):


        local_point1 = PROFILE[
            index
        ]


        local_point2 = PROFILE[
            index + 1
        ]


        global_point1 = (

            repeat_start
            + local_point1[0],

            deck_baseline
            + local_point1[1]

        )


        global_point2 = (

            repeat_start
            + local_point2[0],

            deck_baseline
            + local_point2[1]

        )


        clipped = clip_segment(

            global_point1,

            global_point2,

            floor_left,

            floor_right

        )


        if clipped is None:

            continue


        clipped1 = clipped[0]
        clipped2 = clipped[1]


        append_point(
            deck_points,
            clipped1
        )


        append_point(
            deck_points,
            clipped2
        )


    repeat_start += deck_pitch


# ============================================================
# CHECK PROFILE
# ============================================================

if len(deck_points) < 2:

    ndev_alert(
        "Deck profile could not be generated.",
        exitscript=True
    )


# ============================================================
# SORT PROFILE LEFT -> RIGHT
#
# Normally already ordered, but this guarantees it.
# ============================================================

deck_points.sort(
    key=lambda item: item[0]
)


# ============================================================
# CLEAN DUPLICATE POINTS AGAIN
# ============================================================

clean_points = []


for point in deck_points:

    append_point(
        clean_points,
        point
    )


deck_points = clean_points


# ============================================================
# FORCE EXACT LEFT/RIGHT
# ============================================================

if abs(
    deck_points[0][0]
    - floor_left
) > TOL:

    deck_points.insert(
        0,
        (
            floor_left,
            deck_points[0][1]
        )
    )


if abs(
    deck_points[-1][0]
    - floor_right
) > TOL:

    deck_points.append(
        (
            floor_right,
            deck_points[-1][1]
        )
    )


# ============================================================
# CREATE FILLED REGION BOUNDARY
# ============================================================

boundary_curves = []


top_left = uv_to_xyz(
    floor_left,
    floor_top
)


top_right = uv_to_xyz(
    floor_right,
    floor_top
)


deck_left = uv_to_xyz(

    deck_points[0][0],

    deck_points[0][1]

)


deck_right = uv_to_xyz(

    deck_points[-1][0],

    deck_points[-1][1]

)


# ============================================================
# TOP EDGE
# ============================================================

line = safe_line(
    top_left,
    top_right
)


if line:

    boundary_curves.append(
        line
    )


# ============================================================
# RIGHT SIDE
# ============================================================

line = safe_line(
    top_right,
    deck_right
)


if line:

    boundary_curves.append(
        line
    )


# ============================================================
# DECK PROFILE
#
# Travel RIGHT -> LEFT
# ============================================================

reverse_points = list(
    reversed(
        deck_points
    )
)


for index in range(
    len(reverse_points) - 1
):


    uv1 = reverse_points[
        index
    ]


    uv2 = reverse_points[
        index + 1
    ]


    point1 = uv_to_xyz(

        uv1[0],

        uv1[1]

    )


    point2 = uv_to_xyz(

        uv2[0],

        uv2[1]

    )


    line = safe_line(
        point1,
        point2
    )


    if line:

        boundary_curves.append(
            line
        )


# ============================================================
# LEFT SIDE
# ============================================================

line = safe_line(
    deck_left,
    top_left
)


if line:

    boundary_curves.append(
        line
    )


# ============================================================
# CHECK
# ============================================================

if len(boundary_curves) < 4:

    ndev_alert(
        "Not enough Filled Region boundary curves.",
        exitscript=True
    )


# ============================================================
# CREATE CURVE LOOP
# ============================================================

curve_loop = DB.CurveLoop()


try:

    for curve in boundary_curves:

        curve_loop.Append(
            curve
        )


except Exception as error:

    ndev_alert(

        "Boundary creation failed.\n\n{}".format(
            error
        ),

        title="Deck Filled Region",

        exitscript=True
    )


# ============================================================
# CURVE LOOP COLLECTION
# ============================================================

boundaries = List[
    DB.CurveLoop
]()


boundaries.Add(
    curve_loop
)


# ============================================================
# CREATE FILLED REGION
# ============================================================

transaction = DB.Transaction(

    doc,

    "Aligned Deck Filled Region"

)


region = None


try:

    transaction.Start()


    region = DB.FilledRegion.Create(

        doc,

        filled_region_type.Id,

        view.Id,

        boundaries

    )


    transaction.Commit()


except Exception as error:

    try:

        transaction.RollBack()

    except:
        pass


    ndev_alert(

        "Filled Region could not be created.\n\n"
        "{}\n\n"
        "Deck: {}\n"
        "Gage: {}\n"
        "Depth: {} in\n"
        "Pitch: {} in\n"
        "Profile points: {}"
        .format(

            error,

            selected_deck,

            selected_gage,

            deck_data["depth"],

            deck_data["pitch"],

            len(deck_points)

        ),

        title="Deck Filled Region",

        exitscript=True
    )


# ============================================================
# SELECT NEW FILLED REGION
# ============================================================

if region:

    try:

        selected_ids = List[
            DB.ElementId
        ]()


        selected_ids.Add(
            region.Id
        )


        uidoc.Selection.SetElementIds(
            selected_ids
        )

    except:
        pass


# ============================================================
# SUCCESS
# ============================================================

ndev_alert(

    "DECK FILLED REGION CREATED\n\n"
    "Deck: {}\n"
    "Gage: {}\n"
    "Depth: {} in\n"
    "Pitch: {} in\n"
    "Bottom Flat: {} in\n"
    "Top Flat: {} in\n"
    "Profile Direction: UP\n"
    "Alignment: REAL DECK ANCHOR\n"
    "Filled Region: {}"
    .format(

        selected_deck,

        selected_gage,

        deck_data["depth"],

        deck_data["pitch"],

        deck_data["bottom_flat"],

        deck_data["top_flat"],

        selected_region_name

    ),

    title="Deck Filled Region"
)
