# -*- coding: utf-8 -*-
"""Shared entry points for the Clipboard ribbon menu."""
import imp
import os

from pyrevit import DB, UI
from System import String, Uri
from System.Collections.Generic import KeyValuePair, List
from System.Diagnostics import Process, ProcessStartInfo
from System.IO import File
from System.Windows import FlowDirection, MessageBox, SystemParameters, TextWrapping
from System.Windows.Automation import AutomationProperties
from System.Windows.Controls import ListBoxItem, TextBlock
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import ParserContext, XamlReader
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage


ROOT = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(os.path.dirname(ROOT), 'Move Views.pushbutton')
locale = imp.load_source('ndev_main_clipboard_locale', os.path.join(ROOT, 'clipboard_locale.py'))
tr = locale.Strings(locale.active())


def load_modules():
    def load(folder, name):
        return imp.load_source('ndev_main_cut_' + name, os.path.join(folder, name + '.py'))
    return load(ROOT, 'sheet_clip'), load(SHARED, 'sheet_moves'), load(SHARED, 'sheet_preview')


def clipboard_window(filename, heading, owner):
    path = os.path.join(ROOT, filename)
    context = ParserContext()
    context.BaseUri = Uri(path)
    stream = File.OpenRead(path)
    try:
        window = XamlReader.Load(stream, context)
    finally:
        stream.Dispose()
    if owner:
        WindowInteropHelper(window).Owner = owner
    if tr.code in locale.RTL:
        window.FlowDirection = FlowDirection.RightToLeft
    window.Title = u'NdevTools | ' + heading
    logo = BitmapImage()
    logo.BeginInit()
    logo.CacheOption = BitmapCacheOption.OnLoad
    logo.UriSource = Uri(os.path.join(ROOT, 'assets', 'ndevtools-logo.png'))
    logo.EndInit()
    logo.Freeze()
    window.FindName('BrandLogo').Source = window.Icon = logo
    return window


class Dialog(object):
    def __init__(self, sheet_name, rows, preselected, operation, owner):
        heading = tr(operation + '_title')
        self.window = clipboard_window('CutPaste.xaml', heading, owner)
        for name in ('SheetName', 'Placements', 'Count', 'Heading', 'Hint', 'ChooseButton',
                     'SelectAllButton', 'DismissButton'):
            setattr(self, name, self.window.FindName(name))
        self.chosen = []
        self.blocked = set(row['uid'] for row in rows if row.get('blocked'))
        self.operation = operation
        self.Heading.Text = heading
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
    if doc.IsFamilyDocument or (doc.IsReadOnly and action != 'copy'):
        raise ValueError(tr('open_sheet'))
    clip, moves, preview = load_modules()
    on_sheet = isinstance(sheet, DB.ViewSheet) and not sheet.IsPlaceholder
    if action == 'copy' and sheet.ViewType in (DB.ViewType.Section, DB.ViewType.Detail) and not sheet.IsTemplate:
        details = imp.load_source('ndev_main_clipboard_view_details', os.path.join(ROOT, 'view_details.py'))
        return details.copy(uidoc, clip)
    if action == 'paste':
        entry = clip.for_paste(doc)
        if entry is None:
            raise ValueError(tr('empty'))
        data = clip.info(entry)
        source_label = data['label']
        if not entry['document'].Equals(doc):
            source_label = u'{} / {}'.format(entry['document'].Title, source_label)
        skipped = []
        view_details = entry['kind'] == 'view-details'
        if view_details:
            details = imp.load_source('ndev_main_clipboard_view_details', os.path.join(ROOT, 'view_details.py'))
            result = details.paste(uidoc, entry, clip, moves, tr('point', source_label, sheet.Name), skipped)
        else:
            if not on_sheet:
                raise ValueError(tr('open_sheet'))
            destination = preview.sheet_label(sheet)
            prompt = tr('point', source_label, destination)
            result = clip.paste(doc, sheet, entry['token'], moves, preview, lambda: uidoc.Selection.PickPoint(prompt),
                                lambda item: choose_mode(item, destination), skipped)
        if result:
            ids = List[DB.ElementId]()
            for uid in (result if view_details else result.values()):
                ids.Add(doc.GetElement(uid).Id)
            try:
                uidoc.Selection.SetElementIds(ids)
            except Exception:
                UI.TaskDialog.Show(tr('paste'), tr('selection_failed'))
        if result is not None and skipped:
            report_skips(result, skipped, data, owner=uiapp.MainWindowHandle)
        return result
    if not on_sheet:
        raise ValueError(tr('open_sheet'))
    selected = clip.selected_placements(doc, sheet, uidoc.Selection.GetElementIds())
    copying = action == 'copy'
    supported = [e.UniqueId for e in selected if clip.eligible(doc, sheet, e, moves, copying)]
    if not selected or len(supported) != len(selected):
        rows = clip.sheet_items(doc, sheet, moves, preview, copying)
        blocked = [clip.rejected_row(doc, sheet, e, preview) for e in selected if e is not None and e.UniqueId not in supported]
        rows.extend(blocked)
        if not rows:
            raise ValueError(tr('no_items'))
        preselected = set(e.UniqueId for e in selected if e is not None)
        dialog = Dialog(preview.sheet_label(sheet), rows, preselected, action, uiapp.MainWindowHandle)
        supported = dialog.show()
    if supported:
        return clip.store(doc, sheet, supported, action, moves, preview)


def paste_on_sheet(uiapp):
    uidoc = uiapp.ActiveUIDocument
    sheet = uidoc.ActiveView if uidoc else None
    before = set(tab.ViewId for tab in uidoc.GetOpenUIViews()) if isinstance(sheet, DB.ViewSheet) else set()
    result = main(uiapp, 'paste')
    if not result or not isinstance(sheet, DB.ViewSheet):
        return result

    doc = sheet.Document
    items = [doc.GetElement(uid) for uid in result.values()]
    close_ids = set(item.ViewId for item in items if isinstance(item, DB.Viewport)) - before
    if close_ids:
        # Revit can open copied views after the ribbon command has returned.
        sheet_id = sheet.Id

        def close_pasted_tabs(sender, args):
            uiapp.Idling -= close_pasted_tabs
            active = uiapp.ActiveUIDocument
            if active is None or not doc.IsValidObject or not active.Document.Equals(doc):
                return
            try:
                active_id = active.ActiveView.Id
                tabs = [tab for tab in active.GetOpenUIViews() if tab.ViewId in close_ids]
                # Close the foreground tab last to avoid cycling through the others.
                for tab in sorted(tabs, key=lambda tab: tab.ViewId == active_id):
                    tab.Close()
                if active_id in close_ids and active.ActiveView.Id != sheet_id:
                    active.RequestViewChange(doc.GetElement(sheet_id))
            except Exception as error:
                from pyrevit.coreutils.logger import get_logger
                get_logger('NdevSheetClipboard').warning('Could not close pasted view tabs: {}'.format(error))

        uiapp.Idling += close_pasted_tabs
    return result


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


def report_skips(placed, skipped, data, show=None, owner=None):
    names = dict((r['uid'], r['label']) for r in data['rows'])
    heading = tr('paste_result')
    window = clipboard_window('PasteReport.xaml', heading, owner)
    window.MaxHeight = SystemParameters.WorkArea.Height * 0.8
    window.FindName('ReportHeading').Text = heading
    window.FindName('Summary').Text = tr('summary', len(placed), len(skipped))
    rows = window.FindName('SkippedItems')
    for uid, reason in skipped:
        rows.Items.Add(KeyValuePair[String, String](names.get(uid, uid), tr.reason(reason)))
    close = window.FindName('DismissButton')
    close.Content = tr('close')
    if show:
        show(window)
    else:
        window.ShowDialog()
