# -*- coding: utf-8 -*-

from ndev_i18n import show_localized_dialog as _ndev_show_localized_dialog

from pyrevit import revit, DB, forms

import clr
import re
import uuid


# ============================================================
# .NET REFERENCES
# ============================================================

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")


from System.Windows.Forms import (
    Form,
    TabControl,
    TabPage,
    TextBox,
    Button,
    Label,
    ComboBox,
    ComboBoxStyle,
    ScrollBars,
    MessageBox,
    MessageBoxButtons,
    MessageBoxIcon,
    FormStartPosition,
    DockStyle,
    AnchorStyles,
    TableLayoutPanel,
    FlowLayoutPanel,
    RowStyle,
    ColumnStyle,
    SizeType,
    Padding,
    AutoScaleMode,
    FlowDirection
)

from System.Drawing import (
    Size,
    Font
)



# ============================================================
# NDEV TOOLS - CUSTOM TITLE BAR (IRONPYTHON 2.7)
# Shared Help, minimize/maximize/close, black border.
# This code changes dialog presentation only.
# ============================================================

import System
from System import IntPtr
from System.Diagnostics import Process, ProcessStartInfo
from System.Drawing import Color, Point, Rectangle
from System.Windows.Forms import (
    Panel, FlatStyle, FormBorderStyle, FormWindowState,
    MouseButtons, Cursor, Screen, DialogResult
)

NDEV_TITLE = "Ndev Tools - Sheet Manager"
NDEV_GITHUB = "https://github.com/ndev16"
NDEV_LINKEDIN = "https://www.linkedin.com/in/nataraj016/"


def ndev_caption(title):
    label = str(title) if title else "Sheet Manager"
    if label.lower().startswith("ndev tools"):
        return label
    return "Ndev Tools - " + label


def ndev_open_link(url):
    try:
        start = ProcessStartInfo(url)
        start.UseShellExecute = True
        Process.Start(start)
    except Exception as error:
        # Never call this function recursively when the browser fails.
        MessageBox.Show(
            "Open this URL manually:\n{}\n\n{}".format(url, error),
            NDEV_TITLE + " - Help",
            MessageBoxButtons.OK,
            MessageBoxIcon.Warning
        )


def ndev_install_titlebar(window, caption=None, show_help=True,
                           allow_maximize=True):
    """Build a WinForms title bar around existing controls.

    Keeping the existing controls in a Fill panel preserves Create/Rename tabs.
    Black border is two pixels, matching the other Ndev Tools dialogs.
    """
    window.SuspendLayout()
    if caption is not None:
        window.Text = ndev_caption(caption)
    else:
        window.Text = ndev_caption(window.Text)
    original_controls = list(window.Controls)
    for item in original_controls:
        window.Controls.Remove(item)

    window.FormBorderStyle = getattr(FormBorderStyle, 'None')
    window.BackColor = Color.Black
    window.Padding = Padding(2)

    shell = Panel()
    shell.Dock = DockStyle.Fill
    shell.BackColor = Color.White

    body = Panel()
    body.Dock = DockStyle.Fill
    body.BackColor = Color.White
    body.Padding = Padding(8)
    for item in original_controls:
        body.Controls.Add(item)

    caption_panel = Panel()
    caption_panel.Dock = DockStyle.Top
    caption_panel.Height = 38
    caption_panel.BackColor = Color.FromArgb(28, 42, 61)

    caption_layout = TableLayoutPanel()
    caption_layout.Dock = DockStyle.Fill
    caption_layout.ColumnCount = 5
    caption_layout.RowCount = 1
    caption_layout.Margin = Padding(0)
    caption_layout.Padding = Padding(0)
    caption_layout.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
    for pixels in (82, 42, 42, 44):
        caption_layout.ColumnStyles.Add(ColumnStyle(SizeType.Absolute, pixels))
    caption_layout.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))

    caption_label = Label()
    caption_label.Text = window.Text
    caption_label.ForeColor = Color.White
    caption_label.Font = Font("Segoe UI", 9)
    caption_label.Dock = DockStyle.Fill
    caption_label.TextAlign = System.Drawing.ContentAlignment.MiddleLeft
    caption_label.Padding = Padding(10, 0, 0, 0)
    caption_layout.Controls.Add(caption_label, 0, 0)

    def caption_button(label, column, action, accent=False):
        btn = Button()
        btn.Text = label
        btn.Dock = DockStyle.Fill
        btn.Margin = Padding(2, 3, 2, 3)
        btn.FlatStyle = FlatStyle.Flat
        btn.FlatAppearance.BorderSize = 0
        btn.ForeColor = Color.White
        btn.BackColor = (Color.FromArgb(0, 165, 194) if accent
                         else Color.FromArgb(28, 42, 61))
        btn.Click += action
        caption_layout.Controls.Add(btn, column, 0)
        return btn

    help_button = caption_button(
        "? Help", 1, lambda sender, event: ndev_show_help(), True)
    help_button.Visible = show_help
    caption_button("-", 2, lambda sender, event: setattr(
        window, "WindowState", FormWindowState.Minimized))

    def toggle_maximize(sender, event):
        if not allow_maximize:
            return
        if window.WindowState == FormWindowState.Maximized:
            window.WindowState = FormWindowState.Normal
        else:
            window.MaximizedBounds = Screen.FromControl(window).WorkingArea
            window.WindowState = FormWindowState.Maximized

    max_button = caption_button("[]", 3, toggle_maximize)
    max_button.Enabled = allow_maximize
    caption_button("X", 4, lambda sender, event: window.Close())

    def window_state_changed(sender, event):
        if window.WindowState == FormWindowState.Maximized:
            max_button.Text = "Restore"
        else:
            max_button.Text = "[]"

    # Keep title-bar dragging away from the action buttons.
    drag = {'active': False, 'cursor': None, 'form': None}

    def begin_drag(sender, event):
        if event.Button != MouseButtons.Left:
            return
        if window.WindowState != FormWindowState.Normal:
            return
        drag['active'] = True
        drag['cursor'] = Cursor.Position
        drag['form'] = window.Location

    def move_drag(sender, event):
        if drag['active']:
            location = Cursor.Position
            window.Location = Point(
                drag['form'].X + location.X - drag['cursor'].X,
                drag['form'].Y + location.Y - drag['cursor'].Y
            )

    def stop_drag(sender, event):
        drag['active'] = False

    def title_double_click(sender, event):
        if allow_maximize:
            toggle_maximize(None, None)

    for control in (caption_panel, caption_layout, caption_label):
        control.MouseDown += begin_drag
        control.MouseMove += move_drag
        control.MouseUp += stop_drag
        control.MouseDoubleClick += title_double_click

    window.SizeChanged += window_state_changed
    caption_panel.Controls.Add(caption_layout)
    # Bottom/Fill first, then Top, so the title remains at the top.
    shell.Controls.Add(body)
    shell.Controls.Add(caption_panel)
    window.Controls.Add(shell)
    # Preserve the original area of the sheet tabs beneath the new bar.
    window.Height = window.Height + 38
    if allow_maximize:
        window.MinimumSize = Size(window.MinimumSize.Width,
                                  window.MinimumSize.Height + 38)
    window.ResumeLayout(True)


def ndev_show_help():
    """Show actionable help plus the original Ndev Tools profile links."""
    help_form = Form()
    help_form.Text = NDEV_TITLE + " - Help"
    help_form.Size = Size(590, 435)
    help_form.MinimumSize = Size(500, 370)
    help_form.StartPosition = FormStartPosition.CenterScreen
    help_form.Font = Font("Segoe UI", 9)

    panel = TableLayoutPanel()
    panel.Dock = DockStyle.Fill
    panel.Padding = Padding(16)
    panel.ColumnCount = 1
    panel.RowCount = 4
    for pixels in (40, 215, 40, 40):
        panel.RowStyles.Add(RowStyle(SizeType.Absolute, pixels))

    heading = Label()
    heading.Text = "NDEV TOOLS | SHEET MANAGER"
    heading.Font = Font("Segoe UI", 11, System.Drawing.FontStyle.Bold)
    heading.Dock = DockStyle.Fill
    panel.Controls.Add(heading, 0, 0)

    guide = TextBox()
    guide.Multiline = True
    guide.ReadOnly = True
    guide.BorderStyle = getattr(System.Windows.Forms.BorderStyle, 'None')
    guide.ScrollBars = ScrollBars.Vertical
    guide.Dock = DockStyle.Fill
    guide.Text = (
        "CREATE SHEETS\r\n"
        "1. Open the Create Sheets tab.\r\n"
        "2. Choose a Title Block Type.\r\n"
        "3. Enter each sheet on a new line, for example:\r\n"
        "   S1.1 - FOUNDATION SLAB PLAN\r\n"
        "4. Click Create Sheets and confirm.\r\n\r\n"
        "RENAME SHEETS\r\n"
        "1. Open the Rename Sheets tab.\r\n"
        "2. Click Select Sheets to Rename and choose sheets.\r\n"
        "3. Edit the sheet number and/or name, one per line.\r\n"
        "4. Click Apply Rename and confirm.\r\n\r\n"
        "Duplicate sheet numbers are checked before changes are committed."
    )
    panel.Controls.Add(guide, 0, 1)

    github = Button()
    github.Text = "GitHub  |  github.com/ndev16"
    github.Dock = DockStyle.Fill
    github.Click += lambda sender, event: ndev_open_link(NDEV_GITHUB)
    panel.Controls.Add(github, 0, 2)

    linkedin = Button()
    linkedin.Text = "LinkedIn  |  linkedin.com/in/nataraj016"
    linkedin.Dock = DockStyle.Fill
    linkedin.Click += lambda sender, event: ndev_open_link(NDEV_LINKEDIN)
    panel.Controls.Add(linkedin, 0, 3)

    help_form.Controls.Add(panel)
    ndev_install_titlebar(help_form, show_help=False,
                          allow_maximize=False)
    _ndev_show_localized_dialog(help_form)


def ndev_message(text, title="Sheet Manager",
                 buttons=MessageBoxButtons.OK,
                 icon=MessageBoxIcon.Information):
    """Same OK/Yes/No responses, but with a branded Help title bar."""
    dialog = Form()
    dialog.Text = ndev_caption(title)
    dialog.Size = Size(570, 360)
    dialog.MinimumSize = Size(420, 250)
    dialog.StartPosition = FormStartPosition.CenterScreen
    dialog.Font = Font("Segoe UI", 9)

    layout = TableLayoutPanel()
    layout.Dock = DockStyle.Fill
    layout.Padding = Padding(14)
    layout.ColumnCount = 1
    layout.RowCount = 2
    layout.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
    layout.RowStyles.Add(RowStyle(SizeType.Absolute, 45.0))

    description = TextBox()
    description.Multiline = True
    description.ReadOnly = True
    description.ScrollBars = ScrollBars.Vertical
    description.Dock = DockStyle.Fill
    description.Text = str(text)
    layout.Controls.Add(description, 0, 0)

    footer = FlowLayoutPanel()
    footer.Dock = DockStyle.Fill
    footer.FlowDirection = FlowDirection.RightToLeft

    def add_choice(label, result):
        choice = Button()
        choice.Text = label
        choice.Size = Size(90, 30)
        choice.DialogResult = result
        footer.Controls.Add(choice)

    if buttons == MessageBoxButtons.YesNo:
        add_choice("No", DialogResult.No)
        add_choice("Yes", DialogResult.Yes)
    else:
        add_choice("OK", DialogResult.OK)

    layout.Controls.Add(footer, 0, 1)
    dialog.Controls.Add(layout)
    ndev_install_titlebar(dialog)
    result = _ndev_show_localized_dialog(dialog)
    return result


# pyRevit selection window is WPF, so use the same custom title-bar
# approach as the working Ndev Tools Auto Detail Generator.

def ndev_add_selection_titlebar(window):
    from System.Windows import (Thickness as WpfThickness,
                               WindowStyle as WpfWindowStyle,
                               CornerRadius as WpfCornerRadius)
    from System.Windows.Controls import (DockPanel as WpfDockPanel,
                                         Border as WpfBorder,
                                         Grid as WpfGrid,
                                         ColumnDefinition as WpfColumnDefinition,
                                         TextBlock as WpfTextBlock,
                                         Button as WpfButton,
                                         StackPanel as WpfStackPanel,
                                         Orientation as WpfOrientation)
    from System.Windows.Media import (Brushes as WpfBrushes,
                                      Color as WpfColor,
                                      SolidColorBrush as WpfBrush)
    from System.Windows import (GridLength as WpfGridLength,
                               WindowState as WpfWindowState)
    from System.Windows.Shell import WindowChrome as WpfWindowChrome

    original = window.Content
    if original is None:
        return
    window.Title = ndev_caption(window.Title)
    navy = WpfBrush(WpfColor.FromRgb(28, 42, 61))
    cyan = WpfBrush(WpfColor.FromRgb(0, 165, 194))

    root = WpfDockPanel()
    root.LastChildFill = True
    bar = WpfBorder()
    bar.Height = 38
    bar.Background = navy
    header = WpfGrid()
    header.ColumnDefinitions.Add(WpfColumnDefinition())
    col = WpfColumnDefinition()
    col.Width = WpfGridLength.Auto
    header.ColumnDefinitions.Add(col)

    label = WpfTextBlock()
    label.Text = window.Title
    label.Foreground = WpfBrushes.White
    label.VerticalAlignment = System.Windows.VerticalAlignment.Center
    label.Margin = WpfThickness(12, 0, 0, 0)
    WpfGrid.SetColumn(label, 0)
    header.Children.Add(label)

    buttons = WpfStackPanel()
    buttons.Orientation = WpfOrientation.Horizontal
    WpfGrid.SetColumn(buttons, 1)
    header.Children.Add(buttons)

    def action(name, width, callback, background):
        button = WpfButton()
        button.Content = name
        button.Width = width
        button.Height = 30
        button.Margin = WpfThickness(2, 4, 2, 4)
        button.BorderThickness = WpfThickness(0)
        button.Background = background
        button.Foreground = WpfBrushes.White
        button.Click += callback
        buttons.Children.Add(button)
        return button

    action("? Help", 76, lambda sender, args: ndev_show_help(), cyan)
    action("-", 40, lambda sender, args: setattr(
        window, 'WindowState', WpfWindowState.Minimized), navy)

    def maximize(sender, args):
        window.WindowState = (WpfWindowState.Normal
                              if window.WindowState == WpfWindowState.Maximized
                              else WpfWindowState.Maximized)

    action("[]", 40, maximize, navy)
    action("X", 40, lambda sender, args: window.Close(), navy)

    def move_window(sender, args):
        if args.ClickCount == 2:
            maximize(None, None)
            args.Handled = True
        else:
            try:
                window.DragMove()
            except Exception:
                pass

    bar.MouseLeftButtonDown += move_window
    bar.Child = header
    WpfDockPanel.SetDock(bar, System.Windows.Controls.Dock.Top)
    window.Content = None
    root.Children.Add(bar)
    root.Children.Add(original)

    outline = WpfBorder()
    outline.BorderBrush = WpfBrushes.Black
    outline.BorderThickness = WpfThickness(2)
    outline.Child = root
    window.Content = outline
    window.WindowStyle = getattr(WpfWindowStyle, 'None')
    chrome = WpfWindowChrome()
    chrome.CaptionHeight = 0.0
    chrome.ResizeBorderThickness = WpfThickness(6)
    chrome.GlassFrameThickness = WpfThickness(0)
    chrome.CornerRadius = WpfCornerRadius(0)
    WpfWindowChrome.SetWindowChrome(window, chrome)
    window.Height = window.Height + 38


class NdevSelectFromList(forms.SelectFromList):
    """Keep native searchable pyRevit multi-select functionality."""
    def _setup(self, **kwargs):
        forms.SelectFromList._setup(self, **kwargs)
        ndev_add_selection_titlebar(self)


# ============================================================
# REVIT DOCUMENT
# ============================================================

doc = revit.doc


# ============================================================
# SHEET MANAGER
#
# FEATURES:
#
# CREATE SHEETS
# ------------------------------------------------------------
#
# Enter:
#
# S1.1 - FOUNDATION SLAB PLAN
# S1.2 - LEVEL 1 FRAMING PLAN
# S1.3 - ROOF FRAMING PLAN
#
# Then click CREATE SHEETS.
#
# All sheets are created at once.
#
#
# RENAME SHEETS
# ------------------------------------------------------------
#
# Select multiple existing sheets.
#
# They load like:
#
# S1.1 - FOUNDATION SLAB PLAN
# S1.2 - LEVEL 1 FRAMING PLAN
#
# Edit the lines.
#
# Click APPLY RENAME.
#
#
# Python 2.7 / IronPython compatible.
# Revit 2022 - 2027.
# ============================================================


# ============================================================
# ELEMENT ID VALUE
# ============================================================

def id_value(element_id):

    try:

        return element_id.IntegerValue

    except:

        return element_id.Value


# ============================================================
# PARSE SHEET LINE
#
# Preferred:
#
# S1.1 - FOUNDATION PLAN
#
# Sheet Number:
# S1.1
#
# Sheet Name:
# FOUNDATION PLAN
#
#
# Also supports:
#
# S-101 - FOUNDATION PLAN
#
# because it looks first for a dash with spaces around it.
# ============================================================

def parse_sheet_line(line):

    if line is None:

        return None


    line = line.strip()


    if not line:

        return None


    # --------------------------------------------------------
    # FIRST TRY:
    #
    # Number [space]-[space] Name
    #
    # Example:
    #
    # S-101 - FOUNDATION PLAN
    # --------------------------------------------------------

    match = re.match(
        r"^\s*(.*?)\s+-\s+(.*?)\s*$",
        line
    )


    if match:

        sheet_number = (
            match.group(1).strip()
        )

        sheet_name = (
            match.group(2).strip()
        )


    else:

        # ----------------------------------------------------
        # FALLBACK
        #
        # Example:
        #
        # S1.1-FOUNDATION PLAN
        # ----------------------------------------------------

        if "-" not in line:

            return None


        parts = line.split(
            "-",
            1
        )


        sheet_number = (
            parts[0].strip()
        )

        sheet_name = (
            parts[1].strip()
        )


    if not sheet_number:

        return None


    if not sheet_name:

        return None


    return (
        sheet_number,
        sheet_name
    )


# ============================================================
# GET ALL SHEETS
# ============================================================

def get_all_sheets():

    sheets = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    return list(
        sheets
    )


# ============================================================
# GET TITLE BLOCK TYPES
# ============================================================

def get_titleblock_types():

    titleblocks = list(
        DB.FilteredElementCollector(doc)
        .OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks
        )
        .WhereElementIsElementType()
        .ToElements()
    )


    result = []


    for titleblock in titleblocks:

        # ----------------------------------------------------
        # FAMILY NAME
        # ----------------------------------------------------

        try:

            family_name = (
                titleblock.Family.Name
            )

        except:

            family_name = (
                "Title Block"
            )


        # ----------------------------------------------------
        # TYPE NAME
        # ----------------------------------------------------

        try:

            type_name = (
                titleblock.Name
            )

        except:

            try:

                parameter = (
                    titleblock.get_Parameter(
                        DB.BuiltInParameter.SYMBOL_NAME_PARAM
                    )
                )


                type_name = (
                    parameter.AsString()
                )

            except:

                type_name = (
                    str(
                        id_value(
                            titleblock.Id
                        )
                    )
                )


        display_name = (
            "{} : {}"
            .format(
                family_name,
                type_name
            )
        )


        result.append(
            (
                display_name,
                titleblock
            )
        )


    result.sort(
        key=lambda item:
            item[0].lower()
    )


    return result


# ============================================================
# SHEET DISPLAY NAME
# ============================================================

def sheet_display_name(sheet):

    return (
        "{} - {}"
        .format(
            sheet.SheetNumber,
            sheet.Name
        )
    )


# ============================================================
# MESSAGE BOX
# ============================================================

def show_message(
        text,
        title="Sheet Manager",
        icon=MessageBoxIcon.Information
):

    ndev_message(
        text,
        title,
        MessageBoxButtons.OK,
        icon
    )


# ============================================================
# MAIN SHEET MANAGER WINDOW
# ============================================================

class SheetManagerForm(Form):


    # ========================================================
    # INITIALIZE
    # ========================================================

    def __init__(self):

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.Text = (
            "Ndev Tools - Sheet Manager"
        )


        self.Size = Size(
            900,
            700
        )


        self.MinimumSize = Size(
            800,
            600
        )


        self.StartPosition = (
            FormStartPosition.CenterScreen
        )


        # ----------------------------------------------------
        # DPI SCALING
        #
        # Fixes overlapping controls at
        # 125%, 150%, etc.
        # ----------------------------------------------------

        self.AutoScaleMode = (
            AutoScaleMode.Dpi
        )


        self.Font = Font(
            "Segoe UI",
            9
        )


        self.Padding = Padding(
            8
        )


        # ----------------------------------------------------
        # DATA
        # ----------------------------------------------------

        self.titleblock_items = (
            get_titleblock_types()
        )


        self.rename_sheets = []


        # ----------------------------------------------------
        # TAB CONTROL
        # ----------------------------------------------------

        self.tabs = (
            TabControl()
        )


        self.tabs.Dock = (
            DockStyle.Fill
        )


        # ----------------------------------------------------
        # CREATE TAB
        # ----------------------------------------------------

        self.create_tab = (
            TabPage(
                "Create Sheets"
            )
        )


        # ----------------------------------------------------
        # RENAME TAB
        # ----------------------------------------------------

        self.rename_tab = (
            TabPage(
                "Rename Sheets"
            )
        )


        self.tabs.TabPages.Add(
            self.create_tab
        )


        self.tabs.TabPages.Add(
            self.rename_tab
        )


        self.Controls.Add(
            self.tabs
        )


        # ----------------------------------------------------
        # BUILD UI
        # ----------------------------------------------------

        self.build_create_tab()

        self.build_rename_tab()

        # Add the custom Ndev Tools title bar after both original tabs exist.
        ndev_install_titlebar(self)



    # Native-edge resizing for a borderless Windows Forms caption.
    # WM_NCHITTEST returns the correct Windows resize cursors/handles.
    def WndProc(self, message):
        WM_NCHITTEST = 0x0084
        if (message.Msg == WM_NCHITTEST and
                self.WindowState == FormWindowState.Normal):
            encoded = message.LParam.ToInt64()
            sx = encoded & 0xFFFF
            sy = (encoded >> 16) & 0xFFFF
            if sx >= 0x8000:
                sx -= 0x10000
            if sy >= 0x8000:
                sy -= 0x10000
            point = self.PointToClient(Point(int(sx), int(sy)))
            edge = 6
            left = point.X < edge
            right = point.X >= self.ClientSize.Width - edge
            top = point.Y < edge
            bottom = point.Y >= self.ClientSize.Height - edge
            hit = None
            if top and left:
                hit = 13          # HTTOPLEFT
            elif top and right:
                hit = 14          # HTTOPRIGHT
            elif bottom and left:
                hit = 16          # HTBOTTOMLEFT
            elif bottom and right:
                hit = 17          # HTBOTTOMRIGHT
            elif left:
                hit = 10          # HTLEFT
            elif right:
                hit = 11          # HTRIGHT
            elif top:
                hit = 12          # HTTOP
            elif bottom:
                hit = 15          # HTBOTTOM
            if hit is not None:
                message.Result = IntPtr(hit)
                return
        Form.WndProc(self, message)

    # ========================================================
    # CREATE SHEETS TAB
    # ========================================================

    def build_create_tab(self):

        # ====================================================
        # MAIN TABLE LAYOUT
        # ====================================================

        layout = (
            TableLayoutPanel()
        )


        layout.Dock = (
            DockStyle.Fill
        )


        layout.Padding = Padding(
            15
        )


        layout.ColumnCount = 1

        layout.RowCount = 4


        # ----------------------------------------------------
        # TITLE BLOCK ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # INSTRUCTION ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # TEXT BOX ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.Percent,
                100
            )
        )


        # ----------------------------------------------------
        # BUTTON ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        self.create_tab.Controls.Add(
            layout
        )


        # ====================================================
        # TITLE BLOCK PANEL
        # ====================================================

        titleblock_panel = (
            TableLayoutPanel()
        )


        titleblock_panel.Dock = (
            DockStyle.Top
        )


        titleblock_panel.AutoSize = True

        titleblock_panel.ColumnCount = 2

        titleblock_panel.RowCount = 1


        titleblock_panel.ColumnStyles.Add(
            ColumnStyle(
                SizeType.AutoSize
            )
        )


        titleblock_panel.ColumnStyles.Add(
            ColumnStyle(
                SizeType.Percent,
                100
            )
        )


        # ----------------------------------------------------
        # TITLE BLOCK LABEL
        # ----------------------------------------------------

        titleblock_label = (
            Label()
        )


        titleblock_label.Text = (
            "Title Block Type:"
        )


        titleblock_label.AutoSize = True


        titleblock_label.Anchor = (
            AnchorStyles.Left
        )


        titleblock_label.Margin = Padding(
            0,
            7,
            10,
            7
        )


        # ----------------------------------------------------
        # TITLE BLOCK COMBOBOX
        # ----------------------------------------------------

        self.titleblock_combo = (
            ComboBox()
        )


        self.titleblock_combo.Dock = (
            DockStyle.Fill
        )


        self.titleblock_combo.DropDownStyle = (
            ComboBoxStyle.DropDownList
        )


        self.titleblock_combo.Margin = Padding(
            0,
            3,
            0,
            8
        )


        # ----------------------------------------------------
        # POPULATE TITLE BLOCKS
        # ----------------------------------------------------

        for (
            display_name,
            titleblock
        ) in self.titleblock_items:

            self.titleblock_combo.Items.Add(
                display_name
            )


        if (
            self.titleblock_combo
            .Items
            .Count
            > 0
        ):

            self.titleblock_combo.SelectedIndex = (
                0
            )


        titleblock_panel.Controls.Add(
            titleblock_label,
            0,
            0
        )


        titleblock_panel.Controls.Add(
            self.titleblock_combo,
            1,
            0
        )


        layout.Controls.Add(
            titleblock_panel,
            0,
            0
        )


        # ====================================================
        # CREATE INSTRUCTIONS
        # ====================================================

        create_label = (
            Label()
        )


        create_label.Text = (
            "Enter one sheet per line using:\n"
            "S1.1 - FOUNDATION SLAB PLAN\n\n"
            "Press Enter for the next sheet. "
            "You can paste as many sheets as needed."
        )


        create_label.AutoSize = True


        create_label.Dock = (
            DockStyle.Top
        )


        create_label.Margin = Padding(
            0,
            8,
            0,
            12
        )


        layout.Controls.Add(
            create_label,
            0,
            1
        )


        # ====================================================
        # CREATE TEXTBOX
        # ====================================================

        self.create_textbox = (
            TextBox()
        )


        self.create_textbox.Multiline = (
            True
        )


        self.create_textbox.AcceptsReturn = (
            True
        )


        self.create_textbox.AcceptsTab = (
            False
        )


        self.create_textbox.ScrollBars = (
            ScrollBars.Both
        )


        self.create_textbox.WordWrap = (
            False
        )


        self.create_textbox.Dock = (
            DockStyle.Fill
        )


        self.create_textbox.Margin = Padding(
            0,
            0,
            0,
            12
        )


        layout.Controls.Add(
            self.create_textbox,
            0,
            2
        )


        # ====================================================
        # CREATE BUTTON PANEL
        # ====================================================

        button_panel = (
            FlowLayoutPanel()
        )


        button_panel.Dock = (
            DockStyle.Fill
        )


        button_panel.AutoSize = (
            True
        )


        button_panel.FlowDirection = (
            FlowDirection.RightToLeft
        )


        # ----------------------------------------------------
        # CREATE BUTTON
        # ----------------------------------------------------

        self.create_button = (
            Button()
        )


        self.create_button.Text = (
            "Create Sheets"
        )


        self.create_button.Size = Size(
            160,
            38
        )


        self.create_button.Click += (
            self.create_sheets_click
        )


        button_panel.Controls.Add(
            self.create_button
        )


        layout.Controls.Add(
            button_panel,
            0,
            3
        )


    # ========================================================
    # RENAME SHEETS TAB
    # ========================================================

    def build_rename_tab(self):

        # ====================================================
        # MAIN TABLE LAYOUT
        # ====================================================

        layout = (
            TableLayoutPanel()
        )


        layout.Dock = (
            DockStyle.Fill
        )


        layout.Padding = Padding(
            15
        )


        layout.ColumnCount = 1

        layout.RowCount = 4


        # ----------------------------------------------------
        # INSTRUCTIONS
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # SELECT BUTTON
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # TEXTBOX
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.Percent,
                100
            )
        )


        # ----------------------------------------------------
        # APPLY BUTTON
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        self.rename_tab.Controls.Add(
            layout
        )


        # ====================================================
        # RENAME INSTRUCTIONS
        # ====================================================

        rename_label = (
            Label()
        )


        rename_label.Text = (
            "1. Click Select Sheets to Rename.\n"
            "2. Edit the sheet number and/or sheet name below.\n"
            "3. Keep one sheet per line.\n"
            "4. Click Apply Rename."
        )


        rename_label.AutoSize = True


        rename_label.Dock = (
            DockStyle.Top
        )


        rename_label.Margin = Padding(
            0,
            0,
            0,
            10
        )


        layout.Controls.Add(
            rename_label,
            0,
            0
        )


        # ====================================================
        # SELECT SHEETS PANEL
        # ====================================================

        select_panel = (
            FlowLayoutPanel()
        )


        select_panel.Dock = (
            DockStyle.Top
        )


        select_panel.AutoSize = (
            True
        )


        # ----------------------------------------------------
        # SELECT SHEETS BUTTON
        # ----------------------------------------------------

        self.select_rename_button = (
            Button()
        )


        self.select_rename_button.Text = (
            "Select Sheets to Rename"
        )


        self.select_rename_button.Size = Size(
            190,
            38
        )


        self.select_rename_button.Click += (
            self.select_rename_sheets_click
        )


        select_panel.Controls.Add(
            self.select_rename_button
        )


        layout.Controls.Add(
            select_panel,
            0,
            1
        )


        # ====================================================
        # RENAME TEXTBOX
        # ====================================================

        self.rename_textbox = (
            TextBox()
        )


        self.rename_textbox.Multiline = (
            True
        )


        self.rename_textbox.AcceptsReturn = (
            True
        )


        self.rename_textbox.AcceptsTab = (
            False
        )


        self.rename_textbox.ScrollBars = (
            ScrollBars.Both
        )


        self.rename_textbox.WordWrap = (
            False
        )


        self.rename_textbox.Dock = (
            DockStyle.Fill
        )


        self.rename_textbox.Margin = Padding(
            0,
            10,
            0,
            12
        )


        layout.Controls.Add(
            self.rename_textbox,
            0,
            2
        )


        # ====================================================
        # APPLY RENAME BUTTON PANEL
        # ====================================================

        rename_button_panel = (
            FlowLayoutPanel()
        )


        rename_button_panel.Dock = (
            DockStyle.Fill
        )


        rename_button_panel.AutoSize = (
            True
        )


        rename_button_panel.FlowDirection = (
            FlowDirection.RightToLeft
        )


        # ----------------------------------------------------
        # APPLY RENAME BUTTON
        # ----------------------------------------------------

        self.rename_button = (
            Button()
        )


        self.rename_button.Text = (
            "Apply Rename"
        )


        self.rename_button.Size = Size(
            160,
            38
        )


        self.rename_button.Click += (
            self.rename_sheets_click
        )


        rename_button_panel.Controls.Add(
            self.rename_button
        )


        layout.Controls.Add(
            rename_button_panel,
            0,
            3
        )


    # ========================================================
    # CREATE SHEETS CLICK
    # ========================================================

    def create_sheets_click(
            self,
            sender,
            event
    ):

        # ====================================================
        # CHECK TITLE BLOCK
        # ====================================================

        if (
            self.titleblock_combo
            .SelectedIndex
            < 0
        ):

            show_message(
                "Select a title block type first.",
                icon=MessageBoxIcon.Warning
            )

            return


        titleblock = (
            self.titleblock_items[
                self.titleblock_combo
                .SelectedIndex
            ][1]
        )


        # ====================================================
        # READ ENTERED LINES
        # ====================================================

        raw_lines = (
            self.create_textbox
            .Text
            .replace(
                "\r\n",
                "\n"
            )
            .replace(
                "\r",
                "\n"
            )
            .split(
                "\n"
            )
        )


        parsed_sheets = []

        invalid_lines = []


        for (
            line_number,
            line
        ) in enumerate(
            raw_lines,
            1
        ):

            # ------------------------------------------------
            # IGNORE EMPTY LINES
            # ------------------------------------------------

            if not line.strip():

                continue


            parsed = (
                parse_sheet_line(
                    line
                )
            )


            if parsed is None:

                invalid_lines.append(
                    "Line {}: {}".format(
                        line_number,
                        line
                    )
                )

                continue


            parsed_sheets.append(
                parsed
            )


        # ====================================================
        # NOTHING VALID
        # ====================================================

        if not parsed_sheets:

            show_message(
                (
                    "No valid sheets were entered.\n\n"
                    "Use this format:\n\n"
                    "S1.1 - FOUNDATION SLAB PLAN"
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # GET EXISTING SHEET NUMBERS
        # ====================================================

        existing_sheets = (
            get_all_sheets()
        )


        existing_numbers = (
            set()
        )


        for sheet in existing_sheets:

            existing_numbers.add(
                sheet.SheetNumber
                .strip()
                .lower()
            )


        # ====================================================
        # CHECK INPUT DUPLICATES
        # ====================================================

        seen_numbers = set()

        valid_sheets = []

        skipped = []


        for (
            sheet_number,
            sheet_name
        ) in parsed_sheets:

            normalized = (
                sheet_number
                .strip()
                .lower()
            )


            # ------------------------------------------------
            # ALREADY EXISTS IN REVIT
            # ------------------------------------------------

            if normalized in existing_numbers:

                skipped.append(
                    (
                        "{} - {} : "
                        "Sheet number already exists"
                    ).format(
                        sheet_number,
                        sheet_name
                    )
                )

                continue


            # ------------------------------------------------
            # DUPLICATE INSIDE INPUT
            # ------------------------------------------------

            if normalized in seen_numbers:

                skipped.append(
                    (
                        "{} - {} : "
                        "Duplicate number in input"
                    ).format(
                        sheet_number,
                        sheet_name
                    )
                )

                continue


            seen_numbers.add(
                normalized
            )


            valid_sheets.append(
                (
                    sheet_number,
                    sheet_name
                )
            )


        # ====================================================
        # NOTHING TO CREATE
        # ====================================================

        if not valid_sheets:

            message = (
                "No sheets can be created."
            )


            if skipped:

                message += (
                    "\n\nSkipped:\n"
                    +
                    "\n".join(
                        skipped
                    )
                )


            show_message(
                message,
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # CONFIRM
        # ====================================================

        confirmation = (
            ndev_message(
                (
                    "Create {} new sheet(s)?"
                ).format(
                    len(
                        valid_sheets
                    )
                ),
                "Create Sheets",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question
            )
        )


        if str(
            confirmation
        ) != "Yes":

            return


        # ====================================================
        # CREATE SHEETS
        # ====================================================

        transaction = (
            DB.Transaction(
                doc,
                "Batch Create Sheets"
            )
        )


        created = []

        failed = []


        try:

            transaction.Start()


            for (
                sheet_number,
                sheet_name
            ) in valid_sheets:

                try:

                    # ----------------------------------------
                    # CREATE SHEET
                    # ----------------------------------------

                    sheet = (
                        DB.ViewSheet.Create(
                            doc,
                            titleblock.Id
                        )
                    )


                    # ----------------------------------------
                    # SET NUMBER
                    # ----------------------------------------

                    sheet.SheetNumber = (
                        sheet_number
                    )


                    # ----------------------------------------
                    # SET NAME
                    # ----------------------------------------

                    sheet.Name = (
                        sheet_name
                    )


                    created.append(
                        "{} - {}".format(
                            sheet_number,
                            sheet_name
                        )
                    )


                except Exception as error:

                    failed.append(
                        (
                            "{} - {} : {}"
                        ).format(
                            sheet_number,
                            sheet_name,
                            error
                        )
                    )


            transaction.Commit()


        except Exception as error:

            try:

                transaction.RollBack()

            except:

                pass


            show_message(
                (
                    "Could not create sheets.\n\n{}"
                ).format(
                    error
                ),
                icon=MessageBoxIcon.Error
            )

            return


        # ====================================================
        # RESULT
        # ====================================================

        message = (
            "BATCH SHEET CREATION COMPLETE\n\n"
            "Created: {}\n"
            "Skipped: {}\n"
            "Failed: {}"
        ).format(
            len(
                created
            ),
            len(
                skipped
            ),
            len(
                failed
            )
        )


        # ----------------------------------------------------
        # INVALID FORMAT
        # ----------------------------------------------------

        if invalid_lines:

            message += (
                "\n\nINVALID FORMAT:\n"
                +
                "\n".join(
                    invalid_lines
                )
            )


        # ----------------------------------------------------
        # SKIPPED
        # ----------------------------------------------------

        if skipped:

            message += (
                "\n\nSKIPPED:\n"
                +
                "\n".join(
                    skipped
                )
            )


        # ----------------------------------------------------
        # FAILED
        # ----------------------------------------------------

        if failed:

            message += (
                "\n\nFAILED:\n"
                +
                "\n".join(
                    failed
                )
            )


        show_message(
            message
        )


        # ====================================================
        # CLEAR TEXT BOX IF SUCCESSFUL
        # ====================================================

        if (
            created
            and
            not failed
            and
            not invalid_lines
        ):

            self.create_textbox.Clear()


    # ========================================================
    # SELECT SHEETS TO RENAME
    # ========================================================

    def select_rename_sheets_click(
            self,
            sender,
            event
    ):

        # ====================================================
        # GET SHEETS
        # ====================================================

        sheets = (
            get_all_sheets()
        )


        if not sheets:

            show_message(
                "No sheets were found.",
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # SORT BY SHEET NUMBER
        # ====================================================

        sheets = sorted(
            sheets,
            key=lambda sheet:
                sheet.SheetNumber.lower()
        )


        display_items = []

        lookup = {}


        # ====================================================
        # BUILD SELECTION LIST
        # ====================================================

        for sheet in sheets:

            display_name = (
                sheet_display_name(
                    sheet
                )
            )


            unique_display = (
                "{} | ID {}"
                .format(
                    display_name,
                    id_value(
                        sheet.Id
                    )
                )
            )


            display_items.append(
                unique_display
            )


            lookup[
                unique_display
            ] = sheet


        # ====================================================
        # SHOW MULTISELECT WINDOW
        # ====================================================

        selected_items = (
            NdevSelectFromList.show(
                display_items,
                title="Select Sheets to Rename",
                button_name="Load Sheets",
                multiselect=True
            )
        )


        if not selected_items:

            return


        # ====================================================
        # PRESERVE SORTED DISPLAY ORDER
        # ====================================================

        selected_sheets = []


        for display_item in display_items:

            if display_item in selected_items:

                selected_sheets.append(
                    lookup[
                        display_item
                    ]
                )


        self.rename_sheets = (
            selected_sheets
        )


        # ====================================================
        # LOAD INTO TEXTBOX
        # ====================================================

        lines = []


        for sheet in (
            self.rename_sheets
        ):

            lines.append(
                "{} - {}".format(
                    sheet.SheetNumber,
                    sheet.Name
                )
            )


        self.rename_textbox.Text = (
            "\r\n".join(
                lines
            )
        )


    # ========================================================
    # APPLY RENAME
    # ========================================================

    def rename_sheets_click(
            self,
            sender,
            event
    ):

        # ====================================================
        # CHECK SELECTION
        # ====================================================

        if not self.rename_sheets:

            show_message(
                "Select sheets to rename first.",
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # READ TEXTBOX
        # ====================================================

        raw_lines = (
            self.rename_textbox
            .Text
            .replace(
                "\r\n",
                "\n"
            )
            .replace(
                "\r",
                "\n"
            )
            .split(
                "\n"
            )
        )


        lines = []


        for line in raw_lines:

            if line.strip():

                lines.append(
                    line
                )


        # ====================================================
        # NUMBER OF LINES MUST MATCH
        # ====================================================

        if (
            len(
                lines
            )
            !=
            len(
                self.rename_sheets
            )
        ):

            show_message(
                (
                    "The number of edited lines must match "
                    "the number of selected sheets.\n\n"
                    "Selected Sheets: {}\n"
                    "Edited Lines: {}"
                ).format(
                    len(
                        self.rename_sheets
                    ),
                    len(
                        lines
                    )
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # PARSE NEW VALUES
        # ====================================================

        new_values = []


        for (
            index,
            line
        ) in enumerate(
            lines
        ):

            parsed = (
                parse_sheet_line(
                    line
                )
            )


            if parsed is None:

                show_message(
                    (
                        "Invalid format on line {}:\n\n"
                        "{}\n\n"
                        "Use this format:\n\n"
                        "S1.1 - FOUNDATION SLAB PLAN"
                    ).format(
                        index + 1,
                        line
                    ),
                    icon=MessageBoxIcon.Warning
                )

                return


            new_values.append(
                parsed
            )


        # ====================================================
        # CHECK DUPLICATES INSIDE RENAME BATCH
        # ====================================================

        new_numbers = []


        for (
            sheet_number,
            sheet_name
        ) in new_values:

            new_numbers.append(
                sheet_number
                .strip()
                .lower()
            )


        if (
            len(
                new_numbers
            )
            !=
            len(
                set(
                    new_numbers
                )
            )
        ):

            show_message(
                (
                    "Two or more edited sheets have "
                    "the same Sheet Number.\n\n"
                    "Every Sheet Number must be unique."
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # IDS OF SHEETS BEING RENAMED
        # ====================================================

        selected_ids = set()


        for sheet in (
            self.rename_sheets
        ):

            selected_ids.add(
                id_value(
                    sheet.Id
                )
            )


        # ====================================================
        # GET NUMBERS USED BY SHEETS OUTSIDE THE SELECTION
        # ====================================================

        outside_numbers = set()


        for sheet in (
            get_all_sheets()
        ):

            if (
                id_value(
                    sheet.Id
                )
                in
                selected_ids
            ):

                continue


            outside_numbers.add(
                sheet.SheetNumber
                .strip()
                .lower()
            )


        # ====================================================
        # CHECK EXTERNAL CONFLICTS
        # ====================================================

        conflicts = []


        for (
            sheet_number,
            sheet_name
        ) in new_values:

            if (
                sheet_number
                .strip()
                .lower()
                in
                outside_numbers
            ):

                conflicts.append(
                    sheet_number
                )


        if conflicts:

            show_message(
                (
                    "These Sheet Numbers are already "
                    "used by other sheets:\n\n{}"
                ).format(
                    "\n".join(
                        conflicts
                    )
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # FIND CHANGED SHEETS
        # ====================================================

        changed_count = 0


        for (
            index,
            sheet
        ) in enumerate(
            self.rename_sheets
        ):

            new_number = (
                new_values[
                    index
                ][0]
            )


            new_name = (
                new_values[
                    index
                ][1]
            )


            if (
                sheet.SheetNumber
                !=
                new_number
                or
                sheet.Name
                !=
                new_name
            ):

                changed_count += 1


        # ====================================================
        # NOTHING CHANGED
        # ====================================================

        if changed_count == 0:

            show_message(
                "No sheet changes were detected."
            )

            return


        # ====================================================
        # CONFIRM
        # ====================================================

        confirmation = (
            ndev_message(
                (
                    "Apply changes to {} sheet(s)?"
                ).format(
                    changed_count
                ),
                "Rename Sheets",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question
            )
        )


        if str(
            confirmation
        ) != "Yes":

            return


        # ====================================================
        # TRANSACTION
        #
        # TEMPORARY SHEET NUMBERS ARE USED FIRST.
        #
        # THIS ALLOWS:
        #
        # S1.1 -> S1.2
        # S1.2 -> S1.1
        #
        # WITHOUT DUPLICATE NUMBER ERRORS.
        # ====================================================

        transaction = (
            DB.Transaction(
                doc,
                "Batch Rename Sheets"
            )
        )


        try:

            transaction.Start()


            # =================================================
            # GENERATE UNIQUE TEMP PREFIX
            # =================================================

            temporary_prefix = (
                "__NDEV_TMP_{}"
                .format(
                    str(
                        uuid.uuid4()
                    )
                    .replace(
                        "-",
                        ""
                    )[:8]
                )
            )


            # =================================================
            # TEMPORARILY RENUMBER ALL SELECTED SHEETS
            # =================================================

            for (
                index,
                sheet
            ) in enumerate(
                self.rename_sheets
            ):

                sheet.SheetNumber = (
                    "{}_{}"
                    .format(
                        temporary_prefix,
                        index + 1
                    )
                )


            # =================================================
            # APPLY FINAL NUMBERS AND NAMES
            # =================================================

            for (
                index,
                sheet
            ) in enumerate(
                self.rename_sheets
            ):

                new_number = (
                    new_values[
                        index
                    ][0]
                )


                new_name = (
                    new_values[
                        index
                    ][1]
                )


                # ---------------------------------------------
                # SHEET NUMBER
                # ---------------------------------------------

                sheet.SheetNumber = (
                    new_number
                )


                # ---------------------------------------------
                # SHEET NAME
                # ---------------------------------------------

                sheet.Name = (
                    new_name
                )


            transaction.Commit()


        except Exception as error:

            try:

                transaction.RollBack()

            except:

                pass


            show_message(
                (
                    "Could not rename sheets.\n\n{}"
                ).format(
                    error
                ),
                icon=MessageBoxIcon.Error
            )

            return


        # ====================================================
        # SUCCESS MESSAGE
        # ====================================================

        show_message(
            (
                "{} sheet(s) updated successfully."
            ).format(
                changed_count
            )
        )


        # ====================================================
        # REFRESH TEXTBOX WITH LIVE REVIT VALUES
        # ====================================================

        refreshed_lines = []


        for sheet in (
            self.rename_sheets
        ):

            refreshed_lines.append(
                "{} - {}".format(
                    sheet.SheetNumber,
                    sheet.Name
                )
            )


        self.rename_textbox.Text = (
            "\r\n".join(
                refreshed_lines
            )
        )


# ============================================================
# RUN
# ============================================================

try:

    window = (
        SheetManagerForm()
    )


    _ndev_show_localized_dialog(window)


except Exception as error:

    ndev_message(
        (
            "Sheet Manager Error:\n\n{}"
        ).format(
            error
        ),
        title="Sheet Manager",
        icon=MessageBoxIcon.Error
    )
