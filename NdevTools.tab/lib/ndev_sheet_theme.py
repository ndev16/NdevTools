# -*- coding: utf-8 -*-
"""ViewPilot presentation for the native Sheets tools (IronPython 2.7).

Only controls and window chrome are styled here. Revit operations, selection
bindings, namescopes and existing event handlers remain owned by each tool.
"""
import os
import clr

ROOT = os.path.dirname(__file__)
LOGO = os.path.join(ROOT, 'sheet_theme', 'ndevtools-logo.png')
BG = '#051220'
PANEL = '#052039'
INPUT = '#092940'
LINE = '#176282'
TEXT = '#DEEFFB'
MUTED = '#8BB8CE'
CYAN = '#0DC7E7'


def _wpf():
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')
    clr.AddReference('WindowsBase')


def _brush(value):
    from System.Windows.Media import BrushConverter
    return BrushConverter().ConvertFromString(value)


def _logical_nodes(root):
    from System.Windows import LogicalTreeHelper, DependencyObject
    yield root
    if isinstance(root, DependencyObject):
        for child in LogicalTreeHelper.GetChildren(root):
            if isinstance(child, DependencyObject):
                for node in _logical_nodes(child):
                    yield node


def _style_wpf_tree(window, resources):
    from System import Double
    from System.Windows.Controls import (Control, Panel, Border, TextBlock,
        TextBox, Button, ComboBox, ListBox, ListView, ScrollViewer, WrapPanel)
    from System.Windows.Media import FontFamily
    from System.Windows import Thickness
    for node in _logical_nodes(window):
        if isinstance(node, Control):
            node.FontFamily = FontFamily('Segoe UI')
            node.Foreground = _brush(TEXT)
        if isinstance(node, Panel):
            # Do not color template internals or replace logical item templates.
            node.Background = _brush(BG)
        if isinstance(node, TextBlock):
            node.Foreground = _brush(TEXT)
        if isinstance(node, (TextBox, ComboBox, ListBox, ListView)):
            node.Background = _brush(INPUT if isinstance(node, (TextBox, ComboBox)) else PANEL)
            node.BorderBrush = _brush(LINE)
            node.BorderThickness = Thickness(1)
        if isinstance(node, ScrollViewer):
            node.Background = _brush(BG)
        if isinstance(node, Button):
            node.Background = _brush('#09243A')
            node.BorderBrush = _brush(LINE)
            node.BorderThickness = Thickness(1)
            if isinstance(node.Parent, WrapPanel):
                node.Margin = Thickness(3)
                node.MinHeight = 34
            if not Double.IsNaN(node.Height) and node.Height <= 26:
                node.Padding = Thickness(6, 1, 6, 1)
            text = str(node.Content).lower()
            primary = (node.IsDefault or getattr(node, 'Name', '') == 'select_b'
                       or text in ('yes', 'ok', 'create sheets', 'rename sheets',
                                   'place all views', 'apply', 'save'))
            if primary:
                node.Background = _brush(CYAN)
                node.Foreground = _brush('#002032')
        if isinstance(node, Border) and node is window.Content:
            node.BorderBrush = _brush(LINE)


def _wpf_brand(tool, tagline):
    from System import Uri
    from System.Windows import Thickness, VerticalAlignment, FontWeights
    from System.Windows.Controls import StackPanel, Image, Border, TextBlock, Orientation
    from System.Windows.Documents import Run
    from System.Windows.Media.Imaging import BitmapImage
    from System.Windows.Media import Stretch
    brand = StackPanel()
    brand.Orientation = Orientation.Horizontal
    brand.VerticalAlignment = VerticalAlignment.Center
    brand.Margin = Thickness(10, 0, 8, 0)
    image = Image()
    image.Source = BitmapImage(Uri(LOGO))
    image.Width = 54
    image.Height = 54
    image.Stretch = Stretch.Uniform
    image.Margin = Thickness(0, 0, 12, 0)
    brand.Children.Add(image)
    divider = Border()
    divider.Width = 1
    divider.Height = 46
    divider.Background = _brush(LINE)
    divider.Margin = Thickness(0, 0, 12, 0)
    brand.Children.Add(divider)
    text = StackPanel()
    text.VerticalAlignment = VerticalAlignment.Center
    title = TextBlock()
    title.FontSize = 26
    title.FontWeight = FontWeights.Bold
    first, accent = tool
    title.Inlines.Add(Run(first))
    last = Run(accent)
    last.Foreground = _brush(CYAN)
    title.Inlines.Add(last)
    title.Foreground = _brush(TEXT)
    text.Children.Add(title)
    sub = TextBlock()
    sub.Text = tagline
    sub.FontSize = 10
    sub.Foreground = _brush(MUTED)
    text.Children.Add(sub)
    brand.Children.Add(text)
    return brand


def apply_wpf(window, bar=None, caption=None, tool=('Sheet', 'Tools'), tagline='NDEVTOOLS | SHEETS'):
    """Theme an existing window; optionally upgrade its existing caption row."""
    _wpf()
    from System import Double
    from System.Windows import Thickness, VerticalAlignment, GridLength
    from System.Windows.Controls import Grid, DockPanel, Dock
    from System.Windows.Markup import XamlReader
    from System.Windows.Media import FontFamily
    from System.IO import File
    resources = XamlReader.Parse(File.ReadAllText(os.path.join(ROOT, 'sheet_theme', 'theme.xaml')))
    # Local resources override pyRevit's application theme without touching it.
    for key in resources.Keys:
        window.Resources[key] = resources[key]
    for key, color in (('pyRevitWindowBackgroundBrush', BG),
                       ('pyRevitControlBackgroundBrush', INPUT),
                       ('pyRevitForegroundBrush', TEXT),
                       ('pyRevitSubtleForegroundBrush', MUTED),
                       ('pyRevitIconBrush', CYAN),
                       ('pyRevitDarkerDarkBrush', BG),
                       ('pyRevitDarkBrush', INPUT)):
        window.Resources[key] = _brush(color)
    window.Background = _brush(BG)
    window.Foreground = _brush(TEXT)
    window.FontFamily = FontFamily('Segoe UI')
    window.FontSize = 13

    if bar is not None and caption is not None:
        parent = caption.Parent
        if isinstance(parent, Grid):
            parent.Children.Remove(caption)
            brand = _wpf_brand(tool, tagline)
            Grid.SetColumn(brand, 0)
            parent.Children.Add(brand)
        elif isinstance(parent, DockPanel):
            # DockPanel's last child fills the available caption width.
            parent.Children.Remove(caption)
            brand = _wpf_brand(tool, tagline)
            parent.Children.Add(brand)
        bar.Height = 78
        bar.Background = _brush('#04182B')
        bar.BorderBrush = _brush(LINE)
        bar.BorderThickness = Thickness(0, 0, 0, 1)
        # Keep the existing content area when replacing the old 38px header.
        if not Double.IsNaN(window.Height):
            window.Height += 40
        if isinstance(parent, (Grid, DockPanel)):
            for node in _logical_nodes(parent):
                from System.Windows.Controls import Button
                if isinstance(node, Button):
                    node.VerticalAlignment = VerticalAlignment.Center
                    node.Margin = Thickness(3, 0, 3, 0)
        window.MinWidth = max(window.MinWidth, 720 if len(''.join(tool)) >= 16 else 560)
    _style_wpf_tree(window, resources)

    def loaded(sender, args):
        _style_wpf_tree(window, resources)
        # The title's accent and subtitle intentionally differ from body text.
        if bar is not None:
            for node in _logical_nodes(bar):
                from System.Windows.Controls import TextBlock
                if isinstance(node, TextBlock) and node.FontSize == 10:
                    node.Foreground = _brush(MUTED)
    window.Loaded += loaded


def apply_winforms(window, caption_panel, caption_layout, caption_label,
                   tool=('Sheet', 'Manager'), tagline='CREATE | RENAME | ORGANIZE SHEETS'):
    """Apply ViewPilot colors to WinForms while preserving all tab controls."""
    clr.AddReference('System.Windows.Forms')
    clr.AddReference('System.Drawing')
    from System.Drawing import (Color, Font, FontStyle, Size, SolidBrush,
        Rectangle, StringFormat, StringAlignment, Image, Point)
    from System.Windows.Forms import (Button, TextBox, ComboBox, TabControl,
        TabPage, Label, Panel, FlatStyle, TabDrawMode, ComboBoxStyle,
        DrawMode, BorderStyle, DockStyle, Padding, PictureBox, PictureBoxSizeMode)

    def color(value):
        return Color.FromArgb(int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))

    tabs_to_style = []

    def style(node):
        node.ForeColor = color(TEXT)
        node.BackColor = color(BG)
        if isinstance(node, Button):
            node.FlatStyle = FlatStyle.Flat
            node.FlatAppearance.BorderSize = 1
            node.FlatAppearance.BorderColor = color(LINE)
            node.FlatAppearance.MouseOverBackColor = color('#124264')
            node.FlatAppearance.MouseDownBackColor = color('#0C3A52')
            node.BackColor = color('#09243A')
            node.UseVisualStyleBackColor = False
            if node.Text.lower() in ('create sheets', 'rename sheets', 'apply rename', 'yes', 'ok'):
                node.BackColor = color(CYAN)
                node.ForeColor = color('#002032')
                node.FlatAppearance.MouseOverBackColor = color('#6DEFFF')
        elif isinstance(node, TextBox):
            node.BackColor = color(INPUT)
            node.BorderStyle = BorderStyle.FixedSingle
        elif isinstance(node, ComboBox):
            node.BackColor = color(INPUT)
            node.FlatStyle = FlatStyle.Flat
            node.DrawMode = DrawMode.OwnerDrawFixed

            def draw_combo(sender, event):
                from System.Windows.Forms import DrawItemState
                selected = (event.State & DrawItemState.Selected) == DrawItemState.Selected
                fill = SolidBrush(color('#0C3A52' if selected else INPUT))
                ink = SolidBrush(color(TEXT))
                event.Graphics.FillRectangle(fill, event.Bounds)
                if event.Index >= 0:
                    event.Graphics.DrawString(str(sender.Items[event.Index]), sender.Font, ink,
                                              float(event.Bounds.X + 5), float(event.Bounds.Y + 2))
                event.DrawFocusRectangle()
                fill.Dispose()
                ink.Dispose()
            node.DrawItem += draw_combo
        elif isinstance(node, TabPage):
            node.UseVisualStyleBackColor = False
        elif isinstance(node, TabControl):
            tabs_to_style.append(node)
        for child in node.Controls:
            style(child)
    style(window)
    for tabs in tabs_to_style:
        # Native TabControl paints a light OS strip even with owner drawing.
        # Keep its selection state and events, and present the existing page
        # controls in dark panels under matching navigation buttons.
        from System.Windows.Forms import FlowLayoutPanel
        host = Panel()
        host.Dock = DockStyle.Fill
        host.BackColor = color(BG)
        navigation = FlowLayoutPanel()
        navigation.Dock = DockStyle.Top
        navigation.Height = 42
        navigation.BackColor = color(BG)
        navigation.WrapContents = False
        pages = []
        buttons = []
        for index, tab in enumerate(tabs.TabPages):
            page = Panel()
            page.Dock = DockStyle.Fill
            page.BackColor = color(BG)
            for child in list(tab.Controls):
                tab.Controls.Remove(child)
                page.Controls.Add(child)
            host.Controls.Add(page)
            pages.append(page)
            button = Button()
            button.Text = tab.Text
            button.Width = 170
            button.Height = 36
            button.Margin = Padding(0, 0, 4, 4)
            style(button)
            def select_page(sender, args, selected_index=index, control=tabs):
                control.SelectedIndex = selected_index
            button.Click += select_page
            navigation.Controls.Add(button)
            buttons.append(button)
        host.Controls.Add(navigation)
        navigation.SendToBack()
        # Keep native SelectedIndexChanged notifications active when hidden.
        native_handle = tabs.Handle
        tabs.Visible = False
        tabs.Parent.Controls.Add(host)
        host.BringToFront()

        def sync_tabs(sender, args, control=tabs, page_list=pages, button_list=buttons):
            for index, page in enumerate(page_list):
                active = index == control.SelectedIndex
                page.Visible = active
                button_list[index].BackColor = color(CYAN if active else '#09243A')
                button_list[index].ForeColor = color('#002032' if active else TEXT)
        tabs.SelectedIndexChanged += sync_tabs
        if tabs.SelectedIndex < 0:
            tabs.SelectedIndex = 0
        sync_tabs(None, None)

    window.BackColor = color(LINE)
    caption_panel.BackColor = color('#04182B')
    caption_panel.Height = 78
    for button in caption_layout.Controls:
        if isinstance(button, Button):
            button.Margin = Padding(3, 22, 3, 22)
    window.Height += 40
    window.MinimumSize = Size(max(640, window.MinimumSize.Width), window.MinimumSize.Height + 40)
    # Keep the original caption label for its existing drag/double-click handlers.
    caption_label.Text = ''.join(tool) + '\n' + tagline
    caption_label.Font = Font('Segoe UI', 13, FontStyle.Bold)
    caption_label.Padding = Padding(78, 0, 0, 0)
    caption_label.AutoEllipsis = True

    def paint_brand(sender, event):
        # The label keeps native events while its text receives two-color branding.
        from System.Drawing import RectangleF
        event.Graphics.Clear(color('#04182B'))
        title_font = Font('Segoe UI', 20, FontStyle.Bold)
        sub_font = Font('Segoe UI', 7.5)
        first_ink = SolidBrush(color(TEXT))
        accent_ink = SolidBrush(color(CYAN))
        muted_ink = SolidBrush(color(MUTED))
        first_size = event.Graphics.MeasureString(tool[0], title_font)
        event.Graphics.DrawString(tool[0], title_font, first_ink, 78.0, 10.0)
        event.Graphics.DrawString(tool[1], title_font, accent_ink, 78.0 + first_size.Width - 4, 10.0)
        event.Graphics.DrawString(tagline, sub_font, muted_ink, 80.0, 47.0)
        for disposable in (title_font, sub_font, first_ink, accent_ink, muted_ink):
            disposable.Dispose()
    caption_label.Paint += paint_brand
    logo = PictureBox()
    logo.Image = Image.FromFile(LOGO)
    logo.SizeMode = PictureBoxSizeMode.Zoom
    logo.Size = Size(54, 54)
    logo.Location = Point(10, 12)
    logo.BackColor = color('#04182B')
    caption_label.Controls.Add(logo)

    def cleanup(sender, args):
        logo.Image.Dispose()
    window.FormClosed += cleanup
