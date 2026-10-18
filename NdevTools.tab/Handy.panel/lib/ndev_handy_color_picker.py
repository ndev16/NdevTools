# -*- coding: utf-8 -*-
"""Inline WPF color palette. No native common dialogs or modal message loop."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
from System.Windows import Thickness, CornerRadius
from System.Windows.Controls import (Border, StackPanel, WrapPanel, Button,
                                     TextBlock, TextBox, Slider, Orientation)
from System.Windows.Controls.Primitives import Popup, PlacementMode
from System.Windows.Input import Key
from System.Windows.Media import BrushConverter, Color, SolidColorBrush


def parse_color(text):
    value = text.strip().lstrip('#')
    if len(value) != 6:
        return None
    try:
        return Color.FromRgb(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except (ValueError, TypeError, OverflowError):
        return None


def color_hex(color):
    # IronPython delegates formatting of CLR Byte to .NET; cast explicitly so
    # Python's hexadecimal formatting is used rather than a .NET format string.
    return '#{:02X}{:02X}{:02X}'.format(int(color.R), int(color.G), int(color.B))


class ColorPicker(object):
    def __init__(self, window):
        self.window = window
        self.syncing = False
        self.callback = None
        self.color = None
        self.popup = Popup()
        self.popup.Placement = PlacementMode.Bottom
        self.popup.StaysOpen = False
        self.popup.AllowsTransparency = True
        self.popup.VerticalOffset = 5
        self.popup.Opened += self.opened
        self.popup.Closed += self.closed
        self.popup.PreviewKeyDown += self.key_down
        border = Border()
        border.Background = self.brush('#082335')
        border.BorderBrush = self.brush('#27708C')
        border.BorderThickness = Thickness(1)
        border.CornerRadius = CornerRadius(6)
        border.Padding = Thickness(14)
        border.Width = 330
        root = StackPanel()
        border.Child = root
        self.popup.Child = border
        self.title = self.label('Choose color', 16)
        root.Children.Add(self.title)
        swatches = WrapPanel()
        swatches.Margin = Thickness(0, 10, 0, 8)
        for value in ('#000000','#FFFFFF','#202C35','#707070','#C00000','#FF0000','#E66B00','#FFC000',
                      '#FFFF00','#92D050','#008000','#00B050','#00C6E8','#0070C0','#203C88','#7030A0',
                      '#F4CCCC','#FCE5CD','#FFF2CC','#D9EAD3','#D0E0E3','#CFE2F3','#D9D2E9','#EAD1DC'):
            button = Button()
            button.Width, button.Height = 30, 24
            button.Margin = Thickness(0, 0, 5, 5)
            button.Padding = Thickness(0)
            button.Background = self.brush(value)
            button.BorderBrush = self.brush('#6D91A6')
            button.ToolTip = value
            button.Tag = value
            button.Click += self.swatch_clicked
            swatches.Children.Add(button)
        root.Children.Add(swatches)
        self.preview = Border()
        self.preview.Height = 24
        self.preview.Margin = Thickness(0, 0, 0, 10)
        root.Children.Add(self.preview)
        self.sliders, self.values = [], []
        for name in ('Red', 'Green', 'Blue'):
            row = StackPanel()
            row.Orientation = Orientation.Horizontal
            row.Margin = Thickness(0, 0, 0, 6)
            label = self.label(name)
            label.Width = 42
            row.Children.Add(label)
            slider = Slider()
            slider.Minimum, slider.Maximum = 0, 255
            slider.IsSnapToTickEnabled = True
            slider.TickFrequency = 1
            slider.Width = 205
            slider.ValueChanged += self.slider_changed
            row.Children.Add(slider)
            number = self.label('0')
            number.Width = 32
            number.Margin = Thickness(8, 0, 0, 0)
            row.Children.Add(number)
            self.sliders.append(slider)
            self.values.append(number)
            root.Children.Add(row)
        root.Children.Add(self.label('Hex color (#RRGGBB)'))
        self.hex_box = TextBox()
        self.hex_box.Margin = Thickness(0, 5, 0, 4)
        self.hex_box.Padding = Thickness(8, 6, 8, 6)
        self.hex_box.Background = self.brush('#FFFFFF')
        self.hex_box.Foreground = self.brush('#152E42')
        self.hex_box.TextChanged += self.hex_changed
        root.Children.Add(self.hex_box)
        self.error = self.label('')
        self.error.FontSize = 11
        root.Children.Add(self.error)
        actions = StackPanel()
        actions.Orientation = Orientation.Horizontal
        actions.Margin = Thickness(0, 8, 0, 0)
        self.apply_button = self.button('Apply color', '#00C6E8', '#031A28')
        self.apply_button.Click += self.accept
        actions.Children.Add(self.apply_button)
        cancel = self.button('Cancel', '#0B2B40', '#E9F6FF')
        cancel.Click += self.cancel
        actions.Children.Add(cancel)
        root.Children.Add(actions)

    @staticmethod
    def brush(value):
        return BrushConverter().ConvertFromString(value)

    def label(self, value, size=12):
        block = TextBlock()
        block.Text = value
        block.FontSize = size
        block.Foreground = self.brush('#E9F6FF')
        return block

    def button(self, text, background, foreground):
        button = Button()
        button.Content = text
        button.Background = self.brush(background)
        button.Foreground = self.brush(foreground)
        button.Padding = Thickness(12, 7, 12, 7)
        button.Margin = Thickness(0, 0, 8, 0)
        return button

    def prepare(self, target, title, current, callback):
        self.close()
        self.popup.PlacementTarget = target
        self.title.Text = title
        self.callback = callback
        color = current.Color if current is not None and hasattr(current, 'Color') and current.Color.A else parse_color('#202C35')
        self.set_color(color)

    def open(self, target, title, current, callback):
        self.prepare(target, title, current, callback)
        self.popup.IsOpen = True

    def set_color(self, color, update_hex=True):
        self.syncing = True
        try:
            self.color = color
            self.preview.Background = SolidColorBrush(color)
            for slider, number, value in zip(self.sliders, self.values, (color.R, color.G, color.B)):
                slider.Value = float(value)
                number.Text = str(value)
            if update_hex:
                self.hex_box.Text = color_hex(color)
            self.error.Text = ''
            self.apply_button.IsEnabled = True
        finally:
            self.syncing = False

    def hex_changed(self, sender, args):
        if self.syncing:
            return
        color = parse_color(self.hex_box.Text)
        if color is None:
            self.color = None
            self.error.Text = 'Enter six hex digits, for example #00A8D8.'
            self.apply_button.IsEnabled = False
        else:
            self.set_color(color, update_hex=False)

    def slider_changed(self, sender, args):
        if not self.syncing:
            self.set_color(Color.FromRgb(*[int(slider.Value) for slider in self.sliders]))

    def swatch_clicked(self, sender, args):
        self.set_color(parse_color(sender.Tag))

    def accept(self, sender, args):
        if self.color is None or self.callback is None:
            return
        callback, brush = self.callback, SolidColorBrush(self.color)
        self.close()
        try:
            callback(brush)
        except Exception as error:
            self.window.status_text.Text = 'Color was not applied: {}'.format(error)

    def opened(self, sender, args):
        self.hex_box.Focus()
        self.hex_box.SelectAll()

    def closed(self, sender, args):
        if not self.popup.IsOpen:
            self.callback = None

    def close(self):
        self.callback = None
        self.popup.IsOpen = False

    def cancel(self, sender, args):
        self.close()

    def key_down(self, sender, args):
        if args.Key == Key.Escape:
            args.Handled = True
            self.close()
        elif args.Key == Key.Enter and self.apply_button.IsEnabled:
            args.Handled = True
            self.accept(None, None)
