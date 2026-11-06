# -*- coding: utf-8 -*-
"""Shared entry points for the Clipboard ribbon menu."""
import imp
import os

from pyrevit import DB, UI
from System import Uri
from System.Collections.Generic import List
from System.Diagnostics import Process, ProcessStartInfo
from System.IO import File
from System.Windows import FlowDirection, MessageBox, TextWrapping
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import ListBoxItem, TextBlock
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage


ROOT = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(os.path.dirname(ROOT), 'Move Views.pushbutton')
locale = imp.load_source('ndev_main_clipboard_locale', os.path.join(ROOT, 'clipboard_locale.py'))
tr = locale.Strings(locale.active())


def load_modules():
    def load(folder, name):
        return imp.load_source('ndev_main_cut_' + name, os.path.join(folder, name + '.py'))
    return load(ROOT, 'sheet_clip'), load(SHARED, 'sheet_moves'), load(SHARED, 'sheet_preview')


class Dialog(object):
    def __init__(self, sheet_name, rows, preselected, operation, owner):
        self.window = XamlReader.Parse(File.ReadAllText(os.path.join(ROOT, 'CutPaste.xaml')))
        if owner:
            WindowInteropHelper(self.window).Owner = owner
        if tr.code in locale.RTL:
            self.window.FlowDirection = FlowDirection.RightToLeft
        for name in ('SheetName', 'Placements', 'Count', 'Heading', 'Hint', 'ChooseButton',
                     'SelectAllButton', 'DismissButton'):
            setattr(self, name, self.window.FindName(name))
        self.chosen = []
        self.blocked = set(row['uid'] for row in rows if row.get('blocked'))
        self.operation = operation
        self.Heading.Text = tr(operation + '_title')
        self.window.Title = u'NdevTools | ' + self.Heading.Text
        logo = BitmapImage()
        logo.BeginInit()
        logo.CacheOption = BitmapCacheOption.OnLoad
        logo.UriSource = Uri(os.path.join(ROOT, 'assets', 'ndevtools-logo.png'))
        logo.EndInit()
        logo.Freeze()
        self.window.FindName('BrandLogo').Source = self.window.Icon = logo
        self.window.FindName('Credit').Text = tr('credit')
        help_button = self.window.FindName('HelpButton')
        help_button.ToolTip = tr('help')
        AutomationProperties.SetName(help_button, tr('help'))
        help_button.Click += self.show_help
        close_button = self.window.FindName('CloseButton')
        close_button.ToolTip = tr('cancel')
        AutomationProperties.SetName(close_button, tr('cancel'))
        self.ChooseButton.Content = tr(operation + '_selected')
        self.DismissButton.Content = tr('cancel')
        self.SelectAllButton.Content = tr('select_all')
        self.SheetName.Text = tr('active_sheet', sheet_name)
        for row in rows:
            item = ListBoxItem()
            item.Tag = row['uid']
            text = TextBlock()
            text.TextWrapping = TextWrapping.Wrap
            text.Text = u'{}  ·  {}'.format(row['label'], row['kind'])
            if row.get('blocked'):
                text.Text += u'  —  ' + tr.reason(row['blocked'])
                if operation == 'cut':
                    item.IsEnabled = False
            item.Content = text
            self.Placements.Items.Add(item)
            if row['uid'] in preselected and item.IsEnabled:
                item.IsSelected = True
        self.Hint.Text = tr(operation + '_hint')
        self.SelectAllButton.IsEnabled = bool(rows)
        self.SelectAllButton.Click += self.select_all
        self.Placements.SelectionChanged += self.changed
        self.ChooseButton.Click += self.choose
        self.window.Loaded += self.activate
        self.changed(None, None)

    def activate(self, sender, event):
        self.window.Activate()
        self.Placements.Focus()

    def show_help(self, sender, event):
        help_window = XamlReader.Parse(File.ReadAllText(os.path.join(ROOT, 'ClipboardHelp.xaml')))
        help_window.Owner = self.window
        help_window.Icon = self.window.Icon
        help_window.FlowDirection = self.window.FlowDirection
        help_window.Resources.MergedDictionaries.Add(self.window.Resources)
        title = u'{} · {}'.format(self.Heading.Text, tr('help'))
        help_window.Title = u'NdevTools | ' + title
        help_window.FindName('HelpHeading').Text = title
        help_window.FindName('SelectStep').Text = tr('help_select', tr('select_all'), self.ChooseButton.Content)
        help_window.FindName('PasteStep').Text = self.Hint.Text
        help_window.FindName('HelpCredit').Text = tr('credit')
        for name in ('GitHubButton', 'LinkedInButton'):
            button = help_window.FindName(name)
            button.ToolTip = button.Tag
            button.Click += self.open_link
        help_window.ShowDialog()

    def open_link(self, sender, event):
        start = ProcessStartInfo(sender.Tag)
        start.UseShellExecute = True
        try:
            Process.Start(start)
        except Exception as error:
            MessageBox.Show(unicode(error), sender.Content)

    def select_all(self, sender, event):
        for item in self.Placements.Items:
            item.IsSelected = item.IsEnabled

    def changed(self, sender, event):
        count = self.Placements.SelectedItems.Count
        self.ChooseButton.IsEnabled = count > 0
        self.Count.Text = tr('count', count, self.Placements.Items.Count)
        blocked = sum(1 for item in self.Placements.SelectedItems if item.Tag in self.blocked)
        if self.operation == 'copy' and blocked:
            self.Count.Text += u'  ·  ' + tr('will_skip', blocked)

    def choose(self, sender, event):
        self.chosen = [item.Tag for item in self.Placements.SelectedItems]
        self.window.Close()

    def show(self):
        self.window.ShowDialog()
        return self.chosen


def main(uiapp, action):
    if action not in ('cut', 'copy', 'paste'):
        raise ValueError('Choose a command from the Clipboard menu.')
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        raise ValueError(tr('open_sheet'))
    doc, sheet = uidoc.Document, uidoc.ActiveView
    if doc.IsFamilyDocument or doc.IsReadOnly:
        raise ValueError(tr('open_sheet'))
    clip, moves, preview = load_modules()
    entry = clip.current(doc)
    if not isinstance(sheet, DB.ViewSheet) or sheet.IsPlaceholder:
        raise ValueError(tr('open_sheet'))
    if action == 'paste':
        if entry is None:
            raise ValueError(tr('empty'))
        data = clip.info(entry)
        prompt = tr('point', data['label'], preview.sheet_label(sheet))
        skipped = []
        result = clip.paste(doc, sheet, entry['token'], moves, preview, lambda: uidoc.Selection.PickPoint(prompt),
                            lambda item: choose_mode(item, preview.sheet_label(sheet)), skipped)
        if result:
            ids = List[DB.ElementId]()
            for uid in result.values():
                ids.Add(doc.GetElement(uid).Id)
            try:
                uidoc.Selection.SetElementIds(ids)
            except Exception:
                UI.TaskDialog.Show(tr('paste'), tr('selection_failed'))
        if result is not None and skipped:
            report_skips(result, skipped, data)
        return result
    selected = clip.selected_placements(doc, sheet, uidoc.Selection.GetElementIds())
    supported = [e.UniqueId for e in selected if clip.eligible(doc, sheet, e, moves)]
    if not selected or len(supported) != len(selected):
        rows = clip.sheet_items(doc, sheet, moves, preview)
        blocked = [clip.rejected_row(doc, sheet, e, preview) for e in selected if e is not None and e.UniqueId not in supported]
        rows.extend(blocked)
        if not rows:
            raise ValueError(tr('no_items'))
        preselected = set(e.UniqueId for e in selected if e is not None)
        dialog = Dialog(preview.sheet_label(sheet), rows, preselected, action, uiapp.MainWindowHandle)
        supported = dialog.show()
    if supported:
        return clip.store(doc, sheet, supported, action, moves, preview)


def choose_mode(item, destination, show=None):
    target_key = 'legend_target' if item['kind'] == 'Legend' else 'column_target'
    dialog = UI.TaskDialog(tr('paste'))
    try:
        dialog.MainInstruction = tr('choose_mode', item['label'])
        dialog.MainContent = tr(target_key, destination)
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Cancel
        dialog.AllowCancellation = True
        choices = {}
        for i, key in enumerate(item['options'], 1):
            name = 'CommandLink{}'.format(i)
            dialog.AddCommandLink(getattr(UI.TaskDialogCommandLinkId, name), tr(key))
            choices[getattr(UI.TaskDialogResult, name)] = key
        return choices.get(show(dialog) if show else dialog.Show())
    finally:
        if hasattr(dialog, 'Dispose'):
            dialog.Dispose()


def report_skips(placed, skipped, data, show=None):
    names = dict((r['uid'], r['label']) for r in data['rows'])
    dialog = UI.TaskDialog(tr('paste'))
    try:
        dialog.MainInstruction = tr('summary', len(placed), len(skipped))
        dialog.MainContent = u'\n'.join(u'{} — {}'.format(names.get(uid, uid), tr.reason(reason))
                                        for uid, reason in skipped)
        if show:
            show(dialog)
        else:
            dialog.Show()
    finally:
        if hasattr(dialog, 'Dispose'):
            dialog.Dispose()
