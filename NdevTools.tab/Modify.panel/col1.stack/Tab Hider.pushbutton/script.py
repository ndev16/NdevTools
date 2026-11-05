# -*- coding: utf-8 -*-
"""Manage this user's persistent ribbon visibility choices."""
import os
import sys

from pyrevit import forms, HOST_APP
from pyrevit.api import AdWindows
from System.Windows.Controls import CheckBox, TabItem, StackPanel, ScrollViewer, ScrollBarVisibility
from System.Windows import Thickness

bundle_dir = os.path.dirname(__file__)
if bundle_dir not in sys.path:
    sys.path.insert(0, bundle_dir)
from visibility_items import FAMILY_TABS, ribbon_rows, set_visible, visible
from visibility_store import save_choices, VisibilityStoreError
from visibility_startup import queue_restore


class TabHider(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(bundle_dir, 'Tabs.xaml'))
        self.rows = []
        self.initial = {}
        for tab, title, note, key, panels in ribbon_rows(HOST_APP.uiapp):
            self.add_row(self.tab_list, tab, title + note, key)
            if panels:
                panel_list = StackPanel()
                panel_list.Margin = Thickness(8)
                scroll = ScrollViewer()
                scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
                scroll.Content = panel_list
                page = TabItem()
                page.Header = title
                page.Content = scroll
                self.visibility_pages.Items.Add(page)
                for panel, label, panel_key in panels:
                    self.add_row(panel_list, panel, label, panel_key)
        self.apply_button.Click += self.apply
        self.show_all_button.Click += self.show_all
        self.help_button.Click += self.show_help
        self.github_button.Click += self.open_link
        self.linkedin_button.Click += self.open_link
        self.close_button.Click += lambda s, e: self.Close()

    def open_link(self, sender, args):
        from pyrevit import script
        script.open_url(sender.Tag)

    def show_help(self, sender, args):
        from pyrevit.coreutils import applocales, yaml
        from System.Windows import FlowDirection
        tips = yaml.load_as_dict(os.path.join(bundle_dir, 'bundle.yaml'))['tooltip']
        locale = applocales.get_current_applocale()
        language = locale.locale_code if locale else 'en_us'
        heading, _, instructions = tips.get(language, tips['en_us']).strip().partition('\n')
        dialog = forms.WPFWindow(os.path.join(bundle_dir, 'TabHiderHelp.xaml'))
        dialog.Owner = self
        dialog.heading.Text = heading.strip()
        dialog.instructions.Text = instructions.strip()
        if language in ('ar', 'fa'):
            dialog.FlowDirection = FlowDirection.RightToLeft
        dialog.ShowDialog()

    def add_row(self, container, item, label, key):
        row = CheckBox()
        row.Content = label
        row.IsChecked = visible(item)
        row.IsEnabled = key is not None
        row.Margin = Thickness(4, 6, 4, 6)
        container.Children.Add(row)
        self.rows.append((item, row, key))
        self.initial[row] = bool(row.IsChecked)

    def show_all(self, sender, args):
        for item, row, key in self.rows:
            if key is not None:
                row.IsChecked = True
        self.save_and_apply(all_rows=True)

    def apply(self, sender, args):
        self.save_and_apply(all_rows=False)

    def save_and_apply(self, all_rows):
        changed = [(item, row, key) for item, row, key in self.rows
                   if key is not None and (all_rows or bool(row.IsChecked) != self.initial[row])]
        if not changed:
            self.status.Text = 'No visibility changes to save.'
            return
        try:
            save_choices(dict((key, bool(row.IsChecked)) for item, row, key in changed))
        except VisibilityStoreError as error:
            self.status.Text = u'{}'.format(error)
            return
        pending = []
        for item, row, key in changed:
            desired = bool(row.IsChecked)
            try:
                if visible(item) != desired:
                    set_visible(item, desired)
                if visible(item) == desired:
                    self.initial[row] = desired
                    continue
            except Exception:
                pass
            pending.append(row.Content)
        queue_restore()
        self.status.Text = (u'Choices saved. Revit could not apply these yet: ' + u', '.join(pending)
                            if pending else 'Visibility choices saved for future sessions.')


# Repair the exact project-only exposure caused by older Show All versions.
# Never hide Family Editor controls in a family document.
if HOST_APP.doc is not None and not HOST_APP.doc.IsFamilyDocument:
    for ribbon_tab in AdWindows.ComponentManager.Ribbon.Tabs:
        if str(ribbon_tab.Id) in FAMILY_TABS:
            ribbon_tab.IsVisible = False
        for internal_panel in ribbon_tab.Panels:
            if internal_panel.Source.Title == 'Family Editor':
                internal_panel.IsVisible = False

TabHider().ShowDialog()
