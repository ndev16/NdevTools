# -*- coding: utf-8 -*-

from ndev_i18n import show_localized_dialog as _ndev_show_localized_dialog

from pyrevit import revit, DB, forms

# ============================================================
# NDEV TOOLS - CUSTOM TITLE BAR + HELP
# UI only. Existing Match Crop Regions algorithms are untouched.
# Compatible with pyRevit IronPython 2.7 / Revit 2022-2027.
# ============================================================

from pyrevit import script
import System
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import (Window, WindowState, WindowStyle,
                            ResizeMode, WindowStartupLocation,
                            Thickness, CornerRadius, FontWeights,
                            TextWrapping, VerticalAlignment,
                            HorizontalAlignment)
from System.Windows.Controls import (DockPanel, Dock, Grid, ColumnDefinition,
                                     StackPanel, Border, Button, TextBlock,
                                     ScrollViewer, Orientation)
from System.Windows.Media import Color, SolidColorBrush, Brushes
from System.Windows.Shell import WindowChrome

NDEV_TITLE = 'Ndev Tools - Match Crop Regions'
NDEV_GITHUB = 'https://github.com/ndev16'
NDEV_LINKEDIN = 'https://www.linkedin.com/in/nataraj016/'


def ndev_title(title):
    """Apply consistent branding; keep multi-line selectors to one caption."""
    text = str(title or 'Match Crop Regions')
    text = ' | '.join(part.strip() for part in text.splitlines() if part.strip())
    if text.lower().startswith('ndev tools'):
        return text
    return 'Ndev Tools - ' + text


def ndev_open_link(url):
    try:
        info = ProcessStartInfo(url)
        info.UseShellExecute = True
        Process.Start(info)
    except Exception as error:
        ndev_alert('Cannot open the browser.\n\nURL: {}\n\n{}'.format(url, error),
                   title='Help - Browser Error')


def ndev_attach_titlebar(window, include_help=True):
    """Place Help next to minimize/restore/close in the TITLE BAR.

    Preserve the existing WPF content (including pyRevit list-selection UI).
    A 2-pixel black frame encloses the entire dialog.
    """
    original_content = window.Content
    if original_content is None:
        return

    window.Title = ndev_title(window.Title)
    navy = SolidColorBrush(Color.FromRgb(28, 42, 61))
    cyan = SolidColorBrush(Color.FromRgb(0, 165, 194))

    header_grid = Grid()
    header_grid.ColumnDefinitions.Add(ColumnDefinition())
    button_column = ColumnDefinition()
    button_column.Width = System.Windows.GridLength.Auto
    header_grid.ColumnDefinitions.Add(button_column)

    title_label = TextBlock()
    title_label.Text = window.Title
    title_label.Foreground = Brushes.White
    title_label.FontWeight = FontWeights.SemiBold
    title_label.VerticalAlignment = VerticalAlignment.Center
    title_label.Margin = Thickness(12, 0, 4, 0)
    Grid.SetColumn(title_label, 0)
    header_grid.Children.Add(title_label)

    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    Grid.SetColumn(actions, 1)
    header_grid.Children.Add(actions)

    def title_button(caption, width, tooltip, callback, background=None):
        button = Button()
        button.Content = caption
        button.Width = width
        button.Height = 30
        button.Margin = Thickness(2, 4, 2, 4)
        button.Padding = Thickness(4, 0, 4, 0)
        button.ToolTip = tooltip
        button.Background = background if background is not None else navy
        button.Foreground = Brushes.White
        button.BorderThickness = Thickness(0)
        button.Click += callback
        actions.Children.Add(button)
        return button

    if include_help:
        title_button('? Help', 78, 'Instructions, GitHub and LinkedIn',
                     lambda sender, args: ndev_show_help(window), cyan)

    title_button('-', 42, 'Minimize',
                 lambda sender, args: setattr(window, 'WindowState',
                                              WindowState.Minimized))

    def toggle_maximize(sender, args):
        window.WindowState = (WindowState.Normal
                              if window.WindowState == WindowState.Maximized
                              else WindowState.Maximized)

    maximize_button = title_button('[]', 42, 'Maximize / Restore', toggle_maximize)
    title_button('X', 42, 'Close', lambda sender, args: window.Close())

    def sync_maximize(sender, args):
        if window.WindowState == WindowState.Maximized:
            maximize_button.Content = 'Restore'
            maximize_button.Width = 62
        else:
            maximize_button.Content = '[]'
            maximize_button.Width = 42

    window.StateChanged += sync_maximize

    titlebar = Border()
    titlebar.Background = navy
    titlebar.Height = 38
    titlebar.Child = header_grid

    def drag_title(sender, args):
        # Clickable child buttons retain their native mouse handling.
        if args.ClickCount == 2:
            toggle_maximize(None, None)
            args.Handled = True
        else:
            try:
                window.DragMove()
            except Exception:
                pass

    titlebar.MouseLeftButtonDown += drag_title

    content_root = DockPanel()
    content_root.LastChildFill = True
    DockPanel.SetDock(titlebar, Dock.Top)

    # WPF elements may only have one parent at a time.
    window.Content = None
    content_root.Children.Add(titlebar)
    content_root.Children.Add(original_content)

    black_frame = Border()
    black_frame.BorderBrush = Brushes.Black
    black_frame.BorderThickness = Thickness(2)
    black_frame.SnapsToDevicePixels = True
    black_frame.Child = content_root
    window.Content = black_frame

    window.WindowStyle = getattr(WindowStyle, 'None')
    chrome = WindowChrome()
    chrome.CaptionHeight = 0.0
    chrome.ResizeBorderThickness = Thickness(6)
    chrome.GlassFrameThickness = Thickness(0)
    chrome.CornerRadius = CornerRadius(0)
    WindowChrome.SetWindowChrome(window, chrome)

    try:
        if not System.Double.IsNaN(window.Height):
            window.Height += 38
    except Exception:
        pass


class NdevSelectFromList(forms.SelectFromList):
    """Retain pyRevit's native selection workflow; brand its title bar."""
    def _setup(self, **kwargs):
        forms.SelectFromList._setup(self, **kwargs)
        ndev_attach_titlebar(self)


def ndev_show_help(owner=None):
    """Usage instructions with the same GitHub/LinkedIn links."""
    help_window = Window()
    help_window.Title = NDEV_TITLE + ' - Help'
    help_window.Width = 570
    help_window.Height = 410
    help_window.MinWidth = 480
    help_window.ResizeMode = ResizeMode.CanResize
    help_window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    help_window.ShowInTaskbar = False
    if owner is not None:
        help_window.Owner = owner
        help_window.WindowStartupLocation = WindowStartupLocation.CenterOwner

    stack = StackPanel()
    stack.Margin = Thickness(18)

    heading = TextBlock()
    heading.Text = 'NDEV TOOLS | MATCH CROP REGIONS'
    heading.FontWeight = FontWeights.Bold
    heading.Margin = Thickness(0, 0, 0, 12)
    stack.Children.Add(heading)

    steps = TextBlock()
    steps.Text = (
        '1. Choose the reference plan view.\n'
        '2. Select one or more target plan views.\n'
        '3. Choose Yes to copy the reference scale, or No to keep target scales.\n'
        '4. Confirm to apply the reference crop to the target views.\n\n'
        'The tool transfers the model crop boundary in model coordinates. '
        'Target views controlled by a scope box are skipped. '
        'If configured, it also copies crop visibility and annotation crop offsets. '
        'Each target view uses its own Revit transaction.'
    )
    steps.TextWrapping = TextWrapping.Wrap
    steps.Margin = Thickness(0, 0, 0, 18)
    stack.Children.Add(steps)

    github = Button()
    github.Content = 'GitHub  |  github.com/ndev16'
    github.Height = 34
    github.Margin = Thickness(0, 0, 0, 9)
    github.Click += lambda sender, args: ndev_open_link(NDEV_GITHUB)
    stack.Children.Add(github)

    linkedin = Button()
    linkedin.Content = 'LinkedIn  |  linkedin.com/in/nataraj016'
    linkedin.Height = 34
    linkedin.Click += lambda sender, args: ndev_open_link(NDEV_LINKEDIN)
    stack.Children.Add(linkedin)

    scroll = ScrollViewer()
    scroll.Content = stack
    help_window.Content = scroll
    ndev_attach_titlebar(help_window, include_help=False)
    _ndev_show_localized_dialog(help_window)


def ndev_alert(message, title=None, exitscript=False,
               yes=False, no=False, **kwargs):
    """Ndev-branded modal alerts; Yes/No behavior preserved exactly.

    On a closed or cancelled Yes/No dialog, answer defaults to False (No).
    An exitscript alert terminates just as pyRevit forms.alert did.
    """
    window = Window()
    window.Title = ndev_title(title)
    window.Width = 580
    line_count = len(str(message).splitlines())
    window.Height = min(660, max(250, 172 + 20 * line_count))
    window.MinWidth = 450
    window.MinHeight = 240
    window.ResizeMode = ResizeMode.CanResize
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    window.ShowInTaskbar = False

    body = DockPanel()
    body.Margin = Thickness(16)

    scroller = ScrollViewer()
    message_text = TextBlock()
    message_text.Text = str(message)
    message_text.TextWrapping = TextWrapping.Wrap
    scroller.Content = message_text

    answer = {'value': False}
    button_row = StackPanel()
    button_row.Orientation = Orientation.Horizontal
    button_row.HorizontalAlignment = HorizontalAlignment.Right
    button_row.Margin = Thickness(0, 12, 0, 0)

    def add_action(label, result, is_default=False, is_cancel=False):
        button = Button()
        button.Content = label
        button.Width = 96
        button.Height = 32
        button.Margin = Thickness(5, 0, 0, 0)
        button.IsDefault = is_default
        button.IsCancel = is_cancel
        def clicked(sender, args):
            answer['value'] = result
            window.Close()
        button.Click += clicked
        button_row.Children.Add(button)

    if yes or no:
        if no:
            add_action('No', False, is_cancel=True)
        if yes:
            add_action('Yes', True, is_default=True)
    else:
        add_action('OK', True, is_default=True, is_cancel=True)

    DockPanel.SetDock(button_row, Dock.Bottom)
    body.Children.Add(button_row)
    body.Children.Add(scroller)
    window.Content = body
    ndev_attach_titlebar(window)
    _ndev_show_localized_dialog(window)

    if exitscript:
        script.exit()
    if yes or no:
        return answer['value']
    return None


doc = revit.doc


# ============================================================
# MATCH CROP REGIONS
#
# WORKFLOW:
#
# 1. Select REFERENCE VIEW from list.
# 2. Select MULTIPLE TARGET VIEWS.
# 3. Prompt:
#       Apply same scale?
#
#       YES = Source scale is applied to all target views.
#       NO  = Target view scales remain unchanged.
#
# 4. Apply same model crop region to all selected views.
#
# Python 2.7 / IronPython compatible
# ============================================================


COPY_CROP_VISIBILITY = True
COPY_ANNOTATION_CROP_OFFSETS = True
REMOVE_TARGET_SPLIT_CROPS = True


# ============================================================
# ELEMENT ID VALUE
# ============================================================

def id_value(element_id):
    try:
        return element_id.IntegerValue
    except:
        return element_id.Value


# ============================================================
# CHECK VALID PLAN VIEW
# ============================================================

def is_valid_plan_view(view):

    if view is None:
        return False

    if view.IsTemplate:
        return False

    if not isinstance(view, DB.ViewPlan):
        return False

    try:
        crop_box = view.CropBox

        if crop_box is None:
            return False

    except:
        return False

    return True


# ============================================================
# GET SCOPE BOX NAME
# ============================================================

def get_scope_box_name(view):

    try:

        parameter = view.get_Parameter(
            DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP
        )

        if parameter is None:
            return None

        scope_id = parameter.AsElementId()

        if (
            scope_id is None
            or scope_id == DB.ElementId.InvalidElementId
        ):
            return None

        scope_box = doc.GetElement(scope_id)

        if scope_box is None:
            return None

        return scope_box.Name

    except:
        return None


# ============================================================
# BUILD VIEW -> SHEET MAP
# ============================================================

def build_view_sheet_map():

    result = {}

    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .ToElements()
    )

    for viewport in viewports:

        try:

            view_id = id_value(
                viewport.ViewId
            )

            sheet = doc.GetElement(
                viewport.OwnerViewId
            )

            if not isinstance(
                sheet,
                DB.ViewSheet
            ):
                continue

            result[view_id] = sheet

        except:
            pass

    return result


# ============================================================
# CREATE DISPLAY NAME
# ============================================================

def create_view_display_name(
        view,
        sheet_map
):

    view_id = id_value(
        view.Id
    )

    sheet = sheet_map.get(
        view_id
    )

    if sheet:

        location_text = "{} - {}".format(
            sheet.SheetNumber,
            sheet.Name
        )

    else:

        location_text = "UNPLACED"

    scale_text = "1:{}".format(
        view.Scale
    )

    scope_box_name = get_scope_box_name(
        view
    )

    scope_text = ""

    if scope_box_name:

        scope_text = " | Scope Box: {}".format(
            scope_box_name
        )

    return (
        "{} | {} | {}{} | ID {}"
        .format(
            location_text,
            view.Name,
            scale_text,
            scope_text,
            view_id
        )
    )


# ============================================================
# GET ALL VALID PLAN VIEWS
# ============================================================

def get_all_plan_views():

    views = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewPlan)
        .ToElements()
    )

    valid_views = []

    for view in views:

        if is_valid_plan_view(view):

            valid_views.append(
                view
            )

    return valid_views


# ============================================================
# SELECT REFERENCE VIEW
# ============================================================

def select_reference_view():

    sheet_map = build_view_sheet_map()

    views = get_all_plan_views()

    display_items = []
    lookup = {}

    for view in views:

        display_name = (
            create_view_display_name(
                view,
                sheet_map
            )
        )

        display_items.append(
            display_name
        )

        lookup[
            display_name
        ] = view

    display_items.sort()

    if not display_items:

        ndev_alert(
            "No compatible plan views were found.",
            title="Match Crop Regions",
            exitscript=True
        )

    selected = NdevSelectFromList.show(
        display_items,
        title="Select Reference View",
        button_name="Use as Reference",
        multiselect=False
    )

    if not selected:
        return None

    return lookup[selected]


# ============================================================
# SELECT TARGET VIEWS
# ============================================================

def select_target_views(
        reference_view
):

    sheet_map = build_view_sheet_map()

    views = get_all_plan_views()

    display_items = []
    lookup = {}

    for view in views:

        if view.Id == reference_view.Id:
            continue

        display_name = (
            create_view_display_name(
                view,
                sheet_map
            )
        )

        display_items.append(
            display_name
        )

        lookup[
            display_name
        ] = view

    display_items.sort()

    if not display_items:

        ndev_alert(
            "No target plan views were found.",
            title="Match Crop Regions",
            exitscript=True
        )

    selected_items = (
        NdevSelectFromList.show(
            display_items,
            title=(
                "Select Target Views\n"
                "Reference: {}"
                .format(
                    reference_view.Name
                )
            ),
            button_name="Select Target Views",
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
# SOURCE VIEW COORDINATE
# TO MODEL COORDINATE
# ============================================================

def source_view_point_to_model(
        source_view,
        point
):

    origin = source_view.Origin

    right = (
        source_view
        .RightDirection
        .Normalize()
    )

    up = (
        source_view
        .UpDirection
        .Normalize()
    )

    direction = (
        source_view
        .ViewDirection
        .Normalize()
    )

    model_point = (
        origin
        + right.Multiply(
            point.X
        )
        + up.Multiply(
            point.Y
        )
        + direction.Multiply(
            point.Z
        )
    )

    return model_point


# ============================================================
# MODEL COORDINATE
# TO TARGET VIEW COORDINATE
# ============================================================

def model_point_to_target_view(
        target_view,
        model_point
):

    origin = target_view.Origin

    right = (
        target_view
        .RightDirection
        .Normalize()
    )

    up = (
        target_view
        .UpDirection
        .Normalize()
    )

    vector = (
        model_point
        - origin
    )

    x_value = (
        vector.DotProduct(
            right
        )
    )

    y_value = (
        vector.DotProduct(
            up
        )
    )

    return DB.XYZ(
        x_value,
        y_value,
        0.0
    )


# ============================================================
# TRANSFORM SOURCE CROP POINT
# INTO TARGET VIEW
# ============================================================

def transform_crop_point(
        source_view,
        target_view,
        source_point
):

    model_point = (
        source_view_point_to_model(
            source_view,
            source_point
        )
    )

    return (
        model_point_to_target_view(
            target_view,
            model_point
        )
    )


# ============================================================
# CREATE TARGET CROP LOOP
# ============================================================

def create_target_crop_loop(
        source_view,
        target_view,
        source_loop
):

    target_loop = DB.CurveLoop()

    short_tolerance = (
        doc.Application.ShortCurveTolerance
    )

    for curve in source_loop:

        # ----------------------------------------------------
        # STRAIGHT LINE
        # ----------------------------------------------------

        if isinstance(
            curve,
            DB.Line
        ):

            source_start = (
                curve.GetEndPoint(0)
            )

            source_end = (
                curve.GetEndPoint(1)
            )

            target_start = (
                transform_crop_point(
                    source_view,
                    target_view,
                    source_start
                )
            )

            target_end = (
                transform_crop_point(
                    source_view,
                    target_view,
                    source_end
                )
            )

            if (
                target_start.DistanceTo(
                    target_end
                )
                <= short_tolerance
            ):

                raise Exception(
                    "Crop boundary contains "
                    "a very short line."
                )

            target_loop.Append(
                DB.Line.CreateBound(
                    target_start,
                    target_end
                )
            )

        # ----------------------------------------------------
        # FALLBACK FOR OTHER CURVES
        # ----------------------------------------------------

        else:

            points = list(
                curve.Tessellate()
            )

            if len(points) < 2:
                continue

            for index in range(
                len(points) - 1
            ):

                target_start = (
                    transform_crop_point(
                        source_view,
                        target_view,
                        points[index]
                    )
                )

                target_end = (
                    transform_crop_point(
                        source_view,
                        target_view,
                        points[index + 1]
                    )
                )

                if (
                    target_start.DistanceTo(
                        target_end
                    )
                    <= short_tolerance
                ):
                    continue

                target_loop.Append(
                    DB.Line.CreateBound(
                        target_start,
                        target_end
                    )
                )

    return target_loop


# ============================================================
# COPY ANNOTATION CROP OFFSETS
# ============================================================

def copy_annotation_offsets(
        source_manager,
        target_manager
):

    if not COPY_ANNOTATION_CROP_OFFSETS:
        return

    try:

        if not source_manager.CanHaveAnnotationCrop:
            return

        if not target_manager.CanHaveAnnotationCrop:
            return

        target_manager.LeftAnnotationCropOffset = (
            source_manager.LeftAnnotationCropOffset
        )

        target_manager.RightAnnotationCropOffset = (
            source_manager.RightAnnotationCropOffset
        )

        target_manager.TopAnnotationCropOffset = (
            source_manager.TopAnnotationCropOffset
        )

        target_manager.BottomAnnotationCropOffset = (
            source_manager.BottomAnnotationCropOffset
        )

    except:
        pass


# ============================================================
# APPLY CROP TO TARGET VIEW
# ============================================================

def apply_crop_to_target(
        source_view,
        source_loop,
        source_manager,
        target_view,
        copy_scale
):

    # --------------------------------------------------------
    # TARGET SCOPE BOX CHECK
    # --------------------------------------------------------

    scope_box_name = (
        get_scope_box_name(
            target_view
        )
    )

    if scope_box_name:

        raise Exception(
            "Crop is controlled by Scope Box '{}'."
            .format(
                scope_box_name
            )
        )

    target_manager = (
        target_view
        .GetCropRegionShapeManager()
    )

    # --------------------------------------------------------
    # COPY SCALE
    # --------------------------------------------------------

    if copy_scale:

        target_view.Scale = (
            source_view.Scale
        )

    # --------------------------------------------------------
    # REMOVE TARGET SPLIT CROP
    # --------------------------------------------------------

    if REMOVE_TARGET_SPLIT_CROPS:

        try:

            if (
                target_manager.NumberOfSplitRegions
                > 1
            ):

                target_manager.RemoveSplit()

        except:
            pass

    # --------------------------------------------------------
    # ACTIVATE TARGET CROP
    # --------------------------------------------------------

    target_view.CropBoxActive = True

    # --------------------------------------------------------
    # CREATE TARGET CROP
    # --------------------------------------------------------

    target_loop = (
        create_target_crop_loop(
            source_view,
            target_view,
            source_loop
        )
    )

    # --------------------------------------------------------
    # VALIDATE CROP
    # --------------------------------------------------------

    try:

        valid_crop = (
            target_manager
            .IsCropRegionShapeValid(
                target_loop
            )
        )

        if not valid_crop:

            raise Exception(
                "Converted crop region "
                "is not valid for this view."
            )

    except AttributeError:
        pass

    # --------------------------------------------------------
    # APPLY CROP
    # --------------------------------------------------------

    target_manager.SetCropShape(
        target_loop
    )

    # --------------------------------------------------------
    # COPY CROP VISIBILITY
    # --------------------------------------------------------

    if COPY_CROP_VISIBILITY:

        try:

            target_view.CropBoxVisible = (
                source_view.CropBoxVisible
            )

        except:
            pass

    # --------------------------------------------------------
    # COPY ANNOTATION CROP
    # --------------------------------------------------------

    copy_annotation_offsets(
        source_manager,
        target_manager
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # STEP 1
    # SELECT REFERENCE VIEW
    # ========================================================

    reference_view = (
        select_reference_view()
    )

    if reference_view is None:
        return


    # ========================================================
    # CHECK REFERENCE CROP
    # ========================================================

    try:

        if not reference_view.CropBoxActive:

            ndev_alert(
                "The selected reference view "
                "does not have Crop View enabled.\n\n"
                "Turn Crop View ON and run the tool again.",
                title="Match Crop Regions",
                exitscript=True
            )

    except:

        ndev_alert(
            "The selected reference view "
            "does not support crop regions.",
            title="Match Crop Regions",
            exitscript=True
        )


    source_manager = (
        reference_view
        .GetCropRegionShapeManager()
    )


    # ========================================================
    # CHECK SOURCE SPLIT CROP
    # ========================================================

    try:

        if (
            source_manager.NumberOfSplitRegions
            > 1
        ):

            ndev_alert(
                "The reference view uses "
                "a SPLIT crop region.\n\n"
                "This version supports "
                "one crop region only.",
                title="Match Crop Regions",
                exitscript=True
            )

    except:
        pass


    # ========================================================
    # GET SOURCE CROP
    # ========================================================

    source_loops = list(
        source_manager.GetCropShape()
    )

    if len(source_loops) != 1:

        ndev_alert(
            "Could not acquire one crop region "
            "from the reference view.",
            title="Match Crop Regions",
            exitscript=True
        )

    source_loop = (
        source_loops[0]
    )


    # ========================================================
    # STEP 2
    # SELECT TARGET VIEWS
    # ========================================================

    target_views = (
        select_target_views(
            reference_view
        )
    )

    if not target_views:
        return


    # ========================================================
    # STEP 3
    # ASK WHETHER SCALE SHOULD ALSO BE COPIED
    # ========================================================

    copy_scale = ndev_alert(
        (
            "REFERENCE VIEW:\n"
            "{}\n\n"
            "Reference Scale: 1:{}\n\n"
            "Do you want to apply the SAME SCALE "
            "to all selected target views?\n\n"
            "YES = Crop + Scale\n"
            "NO = Crop only"
        ).format(
            reference_view.Name,
            reference_view.Scale
        ),
        title="Apply Same Scale?",
        yes=True,
        no=True
    )


    # ========================================================
    # FINAL CONFIRMATION
    # ========================================================

    if copy_scale:

        scale_status = (
            "YES - Apply 1:{} to targets"
            .format(
                reference_view.Scale
            )
        )

    else:

        scale_status = (
            "NO - Keep existing target scales"
        )


    confirmation = ndev_alert(
        (
            "REFERENCE VIEW:\n"
            "{}\n\n"
            "TARGET VIEWS:\n"
            "{}\n\n"
            "COPY SCALE:\n"
            "{}\n\n"
            "Apply the reference crop "
            "to all selected target views?"
        ).format(
            reference_view.Name,
            len(target_views),
            scale_status
        ),
        title="Match Crop Regions",
        yes=True,
        no=True
    )

    if not confirmation:
        return


    # ========================================================
    # PROCESS VIEWS
    # ========================================================

    successful = []
    failed = []


    for target_view in target_views:

        transaction = DB.Transaction(
            doc,
            "Match Crop - {}".format(
                target_view.Name
            )
        )

        try:

            transaction.Start()

            apply_crop_to_target(
                reference_view,
                source_loop,
                source_manager,
                target_view,
                copy_scale
            )

            transaction.Commit()

            successful.append(
                target_view.Name
            )

        except Exception as error:

            try:
                transaction.RollBack()
            except:
                pass

            failed.append(
                "{}: {}".format(
                    target_view.Name,
                    error
                )
            )


    # ========================================================
    # RESULT
    # ========================================================

    message = (
        "MATCH CROP COMPLETE\n\n"
        "Reference View:\n"
        "{}\n\n"
        "Reference Scale:\n"
        "1:{}\n\n"
        "Selected Targets: {}\n"
        "Successfully Updated: {}\n"
        "Failed / Skipped: {}\n\n"
        "Scale Applied: {}"
    ).format(
        reference_view.Name,
        reference_view.Scale,
        len(target_views),
        len(successful),
        len(failed),
        "YES" if copy_scale else "NO"
    )


    if failed:

        message += (
            "\n\nFAILED / SKIPPED:\n"
            + "\n".join(
                failed
            )
        )


    ndev_alert(
        message,
        title="Match Crop Regions"
    )


# ============================================================
# RUN
# ============================================================

try:

    main()

except Exception as error:

    ndev_alert(
        "An error occurred:\n\n{}".format(
            error
        ),
        title="Match Crop Regions"
    )
