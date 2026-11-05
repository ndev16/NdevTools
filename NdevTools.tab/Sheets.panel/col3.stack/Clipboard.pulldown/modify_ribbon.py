# -*- coding: utf-8 -*-
"""Expose the Sheets clipboard on the project Modify ribbon."""
import os

from pyrevit import UI
from pyrevit.api import AdWindows
from System import AppDomain, Object
from System.IO import File
from System.Reflection import BindingFlags
from System.Windows import Rect
from System.Windows.Data import Binding, BindingMode
from System.Windows.Input import ICommand, CommandManager
from System.Windows.Media import BitmapScalingMode, DrawingVisual, PixelFormats, RenderOptions, VisualTreeHelper
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapCreateOptions, BitmapDecoder, RenderTargetBitmap

REGISTRY = 'NdevTools.Main.ModifySheetClipboard'
PANEL_ID = 'NdevTools.Main.ModifySheetClipboard.Panel'
ACTIONS = ('Cut', 'Copy', 'Paste')
BUNDLE = os.path.dirname(os.path.abspath(__file__))


def _render_icon(bitmap, size, scale):
    # Match pyRevit's supersampling while preserving the native 16/32 DIP ribbon size.
    pixels = int(round(size * scale * 2.0))
    dpi = 96.0 * pixels / size
    drawing = DrawingVisual()
    RenderOptions.SetBitmapScalingMode(drawing, BitmapScalingMode.HighQuality)
    context = drawing.RenderOpen()
    try:
        context.DrawImage(bitmap, Rect(0, 0, size, size))
    finally:
        context.Close()
    result = RenderTargetBitmap(pixels, pixels, dpi, dpi, PixelFormats.Pbgra32)
    result.Render(drawing)
    result.Freeze()
    return result


def _read_icons(folder, dark, scale):
    path = os.path.join(folder, 'icon.dark.png') if dark else None
    if not path or not os.path.isfile(path):
        path = os.path.join(folder, 'icon.png')
    stream = File.OpenRead(path)
    try:
        bitmap = BitmapDecoder.Create(stream, BitmapCreateOptions.PreservePixelFormat,
                                      BitmapCacheOption.OnLoad).Frames[0]
        return _render_icon(bitmap, 16, scale), _render_icon(bitmap, 32, scale)
    finally:
        stream.Dispose()


class SourceCommand(ICommand):
    """Invoke the original Sheets ribbon button with its own command parameter."""
    def __init__(self, source):
        self.source = source

    def CanExecute(self, parameter):
        try:
            return self.source.IsEnabled and self.source.CommandHandler.CanExecute(self.source)
        except Exception:
            return False

    def Execute(self, parameter):
        if self.CanExecute(parameter):
            self.source.CommandHandler.Execute(self.source)

    def add_CanExecuteChanged(self, handler):
        CommandManager.RequerySuggested += handler

    def remove_CanExecuteChanged(self, handler):
        CommandManager.RequerySuggested -= handler


def _item_control(item):
    method = item.GetType().GetMethod('getRibbonItem', BindingFlags.Instance | BindingFlags.NonPublic)
    return method.Invoke(item, None) if method else None


def _original_menu(uiapp):
    for panel in uiapp.GetRibbonPanels('NdevTools'):
        if panel.Name != 'Sheets':
            continue
        for group in panel.GetItems():
            if not isinstance(group, UI.PulldownButton) or group.Name != 'Clipboard':
                continue
            children = list(group.GetItems())
            if len(children) == len(ACTIONS) and set(c.Name for c in children) == set(ACTIONS):
                return group, children
    return None, []


def _show_source(target, item, source):
    target.Text = item.ItemText
    target.ShowText = True
    target.ShowImage = True
    # RibbonItem exposes native bindings and raises PropertyChanged when pyRevit swaps icons.
    for name in ('Image', 'LargeImage'):
        binding = Binding(name)
        binding.Source = source
        binding.Mode = BindingMode.OneWay
        setattr(target, name + 'Binding', binding)
    if item.ToolTip or item.LongDescription:
        target.Description = item.ToolTip or ''
        tip = AdWindows.RibbonToolTip()
        tip.Title = item.ItemText
        tip.Content = item.ToolTip or ''
        tip.ExpandedContent = item.LongDescription or ''
        target.ToolTip = tip


def _build(group, children):
    panel_source = AdWindows.RibbonPanelSource()
    panel_source.Id = PANEL_ID
    panel_source.Title = 'NdevTools'
    menu = AdWindows.RibbonSplitButton()
    menu.Id = PANEL_ID + '.Clipboard'
    menu.IsSplit = False
    menu.IsSynchronizedWithCurrentItem = False
    menu.Size = AdWindows.RibbonItemSize.Large
    _show_source(menu, group, _item_control(group))
    for child in children:
        source = _item_control(child)
        if source is None or source.CommandHandler is None:
            raise ValueError('Could not resolve the Sheets ribbon command ' + child.ItemText)
        button = AdWindows.RibbonButton()
        button.Id = PANEL_ID + '.' + child.Name
        _show_source(button, child, source)
        button.CommandHandler = SourceCommand(source)
        menu.Items.Add(button)
    panel_source.Items.Add(menu)
    panel = AdWindows.RibbonPanel()
    panel.Source = panel_source
    return panel


class Session(object):
    def __init__(self, host):
        self.host = host
        self.idling = False
        self.attempts = 0
        self.theme_listening = False
        # Startup and theme changes can both schedule a later pyRevit ribbon refresh.
        self.passes = 2
        self.needs_alias = True
        self.icons = {}

    def _end_idle(self):
        if self.idling:
            self.host.Idling -= self.on_idle
            self.idling = False

    def queue(self):
        self.attempts = 0
        if not self.idling:
            self.host.Idling += self.on_idle
            self.idling = True

    def stop(self):
        self._end_idle()
        if self.theme_listening:
            self.host.ThemeChanged -= self.on_theme
            self.theme_listening = False

    def on_theme(self, sender, event):
        if event.ThemeChangedType == UI.ThemeType.UITheme:
            # pyRevit also refreshes its icons on Idling. Check once more after that pass.
            self.passes = 2
            self.queue()

    def on_idle(self, uiapp, event):
        self.attempts += 1
        try:
            if self.attach(uiapp):
                self.passes -= 1
                if self.passes <= 0:
                    self._end_idle()
        except Exception as error:
            if self.attempts >= 5:
                from pyrevit.coreutils.logger import get_logger
                get_logger('NdevSheetClipboard').debug('Modify ribbon: {}'.format(error))
        # An absent source group must never keep retrying for the rest of a session.
        if self.attempts >= 5:
            self._end_idle()

    def apply_icons(self, group, children, dark, scale):
        key = (dark, scale)
        if key not in self.icons:
            sizes = {'Clipboard': _read_icons(BUNDLE, dark, scale)}
            for name in ACTIONS:
                sizes[name] = _read_icons(os.path.join(BUNDLE, name + '.pushbutton'), dark, scale)
            self.icons[key] = sizes
        for item in [group] + children:
            small, large = self.icons[key][item.Name]
            if not Object.ReferenceEquals(item.Image, small):
                item.Image = small
            if not Object.ReferenceEquals(item.LargeImage, large):
                item.LargeImage = large

    def attach(self, uiapp):
        group, children = _original_menu(uiapp)
        if group is None:
            return False
        ribbon = AdWindows.ComponentManager.Ribbon
        scale = VisualTreeHelper.GetDpi(ribbon).DpiScaleX if ribbon is not None else 1.0
        theme_manager = getattr(UI, 'UIThemeManager', None)
        dark = theme_manager is not None and theme_manager.CurrentTheme == UI.UITheme.Dark
        self.apply_icons(group, children, dark, scale)
        if not self.needs_alias:
            return True
        tab = next((t for t in ribbon.Tabs if t.Id == 'Modify'), None) if ribbon is not None else None
        if tab is None:
            return False
        new_panel = _build(group, children)
        previous = [p for p in tab.Panels if p.Source and p.Source.Id == PANEL_ID]
        tab.Panels.Add(new_panel)
        for panel in previous:
            tab.Panels.Remove(panel)
        self.needs_alias = False
        return True


def install(host):
    domain = AppDomain.CurrentDomain
    old = domain.GetData(REGISTRY)
    if old is not None:
        old.stop()
    session = Session(host)
    domain.SetData(REGISTRY, session)
    session.queue()
    if hasattr(host, 'ThemeChanged'):
        host.ThemeChanged += session.on_theme
        session.theme_listening = True
    return session
