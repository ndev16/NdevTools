# -*- coding: utf-8 -*-
"""ViewPilot-style chrome for Annotation dialogs; no Revit geometry code."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
from System import Double
from System.Windows import (Window, WindowState, WindowStyle, ResizeMode,
    Thickness, CornerRadius, WindowStartupLocation, VerticalAlignment,
    HorizontalAlignment, TextWrapping)
from System.Windows.Controls import (DockPanel, Dock, Grid, ColumnDefinition,
    StackPanel, Border, Button, TextBlock, ScrollViewer, Orientation,
    ScrollBarVisibility)
from System.Windows.Shell import WindowChrome
from ndev_sheet_theme import apply_wpf
from ndev_i18n import show_localized_dialog


def finish_detail_settings(window):
    apply_wpf(window, window.title_bar, window.title_caption,
              ('Detail', 'Generator'), 'TRACE | FILL | OUTLINE | DETAIL')

    def style_tabs(sender, args):
        from System.Windows.Controls import Control
        for tab in window.category_tabs.Items:
            # Let the selected-tab trigger control its contrasting text color.
            tab.ClearValue(Control.ForegroundProperty)
    style_tabs(None, None)
    window.Loaded += style_tabs


def attach_dialog(window, tool, tagline, help_callback=None):
    """Wrap existing content, retaining its namescope, controls and handlers."""
    original = window.Content
    if original is None:
        return
    bar = Border()
    bar.Height = 38
    header = Grid()
    header.ColumnDefinitions.Add(ColumnDefinition())
    from System.Windows import GridLength
    actions_column = ColumnDefinition()
    actions_column.Width = GridLength.Auto
    header.ColumnDefinitions.Add(actions_column)
    caption = TextBlock()
    caption.Text = window.Title
    header.Children.Add(caption)
    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    Grid.SetColumn(actions, 1)
    header.Children.Add(actions)

    def action(text, width, hint, callback):
        button = Button()
        button.Content = text
        button.Width = width
        button.Height = 30
        button.Padding = Thickness(4, 0, 4, 0)
        button.ToolTip = hint
        button.Click += callback
        actions.Children.Add(button)
        return button

    if help_callback is not None:
        action('? Help', 78, 'Instructions and NdevTools links',
               lambda sender, args: help_callback(window))
    action('-', 40, 'Minimize', lambda sender, args:
           setattr(window, 'WindowState', WindowState.Minimized))

    def maximize(sender, args):
        window.WindowState = (WindowState.Normal if window.WindowState == WindowState.Maximized
                              else WindowState.Maximized)
    maximize_button = action('[]', 40, 'Maximize / Restore', maximize)
    maximize_button.IsEnabled = window.ResizeMode not in (ResizeMode.NoResize, ResizeMode.CanMinimize)
    action('X', 40, 'Close', lambda sender, args: window.Close())

    def drag(sender, args):
        if actions.IsMouseOver:
            return
        if args.ClickCount == 2:
            if maximize_button.IsEnabled:
                maximize(None, None)
            args.Handled = True
        else:
            window.DragMove()
    bar.MouseLeftButtonDown += drag
    bar.Child = header
    root = DockPanel()
    DockPanel.SetDock(bar, Dock.Top)
    window.Content = None
    root.Children.Add(bar)
    root.Children.Add(original)
    outline = Border()
    outline.BorderThickness = Thickness(1)
    outline.Child = root
    window.Content = outline
    window.WindowStyle = getattr(WindowStyle, 'None')
    chrome = WindowChrome()
    chrome.CaptionHeight = 0.0
    chrome.ResizeBorderThickness = Thickness(6)
    chrome.GlassFrameThickness = Thickness(0)
    chrome.CornerRadius = CornerRadius(0)
    WindowChrome.SetWindowChrome(window, chrome)
    if not Double.IsNaN(window.Height):
        window.Height += 38
    apply_wpf(window, bar, caption, tool, tagline)
    # Retain the operation/step title when the brand replaces the caption.
    bar.ToolTip = window.Title


def show_detail_message(message, title=None, exitscript=False, **kwargs):
    """Information/validation alerts used by Detail Generator."""
    window = Window()
    window.Title = title or 'Ndev Tools - Auto Detail Generator'
    window.Width = 760
    window.Height = min(650, max(240, 150 + 19 * len(str(message).splitlines())))
    window.MinHeight = 240
    window.WindowStartupLocation = WindowStartupLocation.CenterScreen
    window.ShowInTaskbar = False
    body = DockPanel()
    body.Margin = Thickness(18)
    ok = Button()
    ok.Content = 'OK'
    ok.Width = 100
    ok.Height = 32
    ok.IsDefault = True
    ok.IsCancel = True
    ok.HorizontalAlignment = HorizontalAlignment.Right
    ok.Margin = Thickness(0, 12, 0, 0)
    ok.Click += lambda sender, args: window.Close()
    DockPanel.SetDock(ok, Dock.Bottom)
    body.Children.Add(ok)
    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    text = TextBlock()
    text.Text = str(message)
    text.TextWrapping = TextWrapping.Wrap
    scroll.Content = text
    body.Children.Add(scroll)
    window.Content = body
    attach_dialog(window, ('Detail', 'Generator'), 'TRACE | FILL | OUTLINE | DETAIL')
    show_localized_dialog(window)
    if exitscript:
        from pyrevit import script
        script.exit()
