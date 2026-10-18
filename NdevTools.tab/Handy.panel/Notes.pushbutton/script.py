# -*- coding: utf-8 -*-
"""Personal notes in a modeless WPF notebook; never edits the Revit model."""
__persistentengine__ = True

import datetime
import io
import os
import re
import sys
from pyrevit import forms, script
from System import TimeSpan, AppDomain
from System.Diagnostics import Process
from System.Windows import (MessageBox, MessageBoxButton, MessageBoxImage,
                            MessageBoxResult, Thickness, TextTrimming, GridLength, Visibility, HorizontalAlignment, VerticalAlignment)
from System.Windows.Controls import ListBoxItem, StackPanel, TextBlock, ScrollBarVisibility
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Media import BrushConverter
from System.Windows.Threading import DispatcherTimer
from Microsoft.Win32 import SaveFileDialog

ROOT = os.path.dirname(__file__)
LIB = os.path.join(os.path.dirname(ROOT), 'lib')
if LIB not in sys.path:
    sys.path.insert(0, LIB)
import ndev_handy_common
if getattr(ndev_handy_common, 'BUILD', None) != '2026-10-19-native-maximize-8':
    reload(ndev_handy_common)
from ndev_handy_common import data_folder, prepare_window, remember, show_existing, HandyFooter, show_tool_help, open_support_link
import ndev_handy_notes_store
if getattr(ndev_handy_notes_store, 'BUILD', None) != '2026-10-18-note-sheets-3':
    reload(ndev_handy_notes_store)
from ndev_handy_notes_store import NoteStore, NoteConflictError, new_note, note_sheets, new_sheet
import ndev_handy_richtext
if getattr(ndev_handy_richtext, 'BUILD', None) != '2026-10-19-safe-sheet-layout-6':
    reload(ndev_handy_richtext)
from ndev_handy_richtext import RichNoteEditor, plain_text, pack_document, export_rtf

from ndev_handy_sheets import export_sheets_rtf, export_sheets_text

SESSION_KEY = 'NdevTools.Handy.Notes.v3'


class NotesWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(ROOT, 'Notes.xaml'), handle_esc=False)
        prepare_window(self)
        self.footer = HandyFooter(self, 'notes')
        self.sidebar_width = 200.0
        self.notes_toggle_button.Click += self.toggle_notes
        self.help_button.Click += self.show_help
        self.github_button.Click += self.open_github
        self.closed, self.loading, self.dirty = False, True, False
        self.current = None
        self.sheets, self.active_sheet = [], 0
        self.store = NoteStore(data_folder('Notes'))
        self.notes, failures = self.store.list_notes()
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromSeconds(1.2)
        self.timer.Tick += self.autosave
        self.rich = RichNoteEditor(self, self.changed)
        self.sheet_combo.SelectionChanged += self.choose_sheet
        self.orientation_combo.SelectionChanged += self.change_orientation
        self.add_sheet_button.Click += self.add_sheet
        self.fill_window_toggle.Checked += self.view_mode_changed
        self.fill_window_toggle.Unchecked += self.view_mode_changed
        self.new_button.Click += self.new
        self.save_button.Click += self.save
        self.export_button.Click += self.export
        self.delete_button.Click += self.delete
        self.folder_button.Click += self.open_folder
        self.search_box.TextChanged += self.search
        self.note_list.SelectionChanged += self.choose
        self.title_editor.TextChanged += self.changed
        self.body_editor.TextChanged += self.changed
        self.PreviewKeyDown += self.shortcut
        self.Closing += self.closing
        self.Closed += self.on_closed
        self.loading = False
        if self.notes:
            self.select(self.notes[0])
        else:
            self.new(None, None)
        if failures:
            self.status_text.Text = '{} unreadable note file(s); originals kept in Notes folder.'.format(len(failures))
            self.status_text.ToolTip = '\n'.join('{}: {}'.format(name, error) for name, error in failures)

    def toggle_notes(self, sender, args):
        if self.notes_sidebar.Visibility == Visibility.Visible:
            self.sidebar_width = max(150.0, self.sidebar_column.ActualWidth)
            self.sidebar_column.MinWidth = 0
            self.sidebar_column.Width = GridLength(0)
            self.splitter_column.Width = GridLength(0)
            self.notes_sidebar.Visibility = Visibility.Collapsed
            self.sidebar_splitter.Visibility = Visibility.Collapsed
            self.notes_toggle_button.Content = 'Show notes'
        else:
            self.sidebar_column.MinWidth = 150
            self.sidebar_column.Width = GridLength(self.sidebar_width)
            self.splitter_column.Width = GridLength(8)
            self.notes_sidebar.Visibility = Visibility.Visible
            self.sidebar_splitter.Visibility = Visibility.Visible
            self.notes_toggle_button.Content = 'Hide notes'

    def show_help(self, sender, args):
        show_tool_help(self, 'notes')

    def open_github(self, sender, args):
        open_support_link(self, 'github')

    def refresh(self):
        self.loading = True
        self.note_list.Items.Clear()
        query = self.search_box.Text.lower().strip()
        shown = 0
        for note in sorted(self.notes, key=lambda n: n.get('updated') or 'Z', reverse=True):
            if query and query not in (note['title'] + '\n' + note['body']).lower():
                continue
            item, stack = ListBoxItem(), StackPanel()
            item.Tag = note['id']
            title, preview = TextBlock(), TextBlock()
            title.Text, title.FontSize = note['title'], 14
            title.TextTrimming = TextTrimming.CharacterEllipsis
            preview.Text = note['body'].strip().replace('\r', '').replace('\n', ' ')[:100] or ('Image / formatted note' if note.get('rich_text') or note.get('sheets') else 'Empty note')
            preview.FontSize = 12
            preview.Foreground = BrushConverter().ConvertFromString('#8DB6CC')
            preview.TextTrimming = TextTrimming.CharacterEllipsis
            preview.Margin = Thickness(0, 5, 0, 0)
            stack.Children.Add(title)
            stack.Children.Add(preview)
            item.Content = stack
            self.note_list.Items.Add(item)
            if self.current and note['id'] == self.current['id']:
                self.note_list.SelectedItem = item
            shown += 1
        self.note_count.Text = '{} of {} notes'.format(shown, len(self.notes))
        self.loading = False

    def update_sheet_controls(self):
        was_loading = self.loading
        self.loading = True
        try:
            self.sheet_combo.Items.Clear()
            for sheet in self.sheets:
                self.sheet_combo.Items.Add(sheet['name'])
            self.sheet_combo.SelectedIndex = self.active_sheet
            self.orientation_combo.SelectedIndex = 1 if self.sheets[self.active_sheet]['orientation'] == 'landscape' else 0
        finally:
            self.loading = was_loading
        self.update_sheet_label()
        self.apply_sheet_layout()

    def update_sheet_label(self):
        if not self.sheets:
            return
        landscape = self.sheets[self.active_sheet]['orientation'] == 'landscape'
        self.page_size_label.Text = 'A4 landscape | 297 x 210 mm' if landscape else 'A4 portrait | 210 x 297 mm'
        self.character_count.Text = '{} characters | Sheet {} of {}'.format(
            len(plain_text(self.body_editor)), self.active_sheet + 1, len(self.sheets))

    def apply_sheet_layout(self):
        if not self.sheets:
            return
        fill = self.fill_window_toggle.IsChecked == True
        self.body_editor.Height = float('nan')
        if fill:
            self.body_editor.Width = float('nan')
            self.body_editor.MinHeight = 0
            self.body_editor.HorizontalAlignment = HorizontalAlignment.Stretch
            self.body_editor.VerticalAlignment = VerticalAlignment.Stretch
            self.body_editor.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
            self.body_editor.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
            self.sheet_scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled
            self.sheet_scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
            self.sheet_scroll.Padding = Thickness(0)
            self.sheet_scroll.Background = self.body_editor.Document.Background
        else:
            landscape = self.sheets[self.active_sheet]['orientation'] == 'landscape'
            width, height = (297.0, 210.0) if landscape else (210.0, 297.0)
            self.body_editor.Width = width * 96.0 / 25.4
            self.body_editor.MinHeight = height * 96.0 / 25.4
            self.body_editor.HorizontalAlignment = HorizontalAlignment.Center
            self.body_editor.VerticalAlignment = VerticalAlignment.Top
            self.body_editor.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled
            self.body_editor.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
            self.sheet_scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
            self.sheet_scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
            self.sheet_scroll.Padding = Thickness(10)
            self.sheet_scroll.Background = BrushConverter().ConvertFromString('#153342')

    def view_mode_changed(self, sender, args):
        self.apply_sheet_layout()

    def snapshot_sheets(self):
        sheets = [dict(sheet) for sheet in self.sheets]
        sheets[self.active_sheet].update(body=plain_text(self.body_editor), rich_text=pack_document(self.body_editor))
        return sheets

    def select(self, note):
        sheets = note_sheets(note)
        index = note.get('active_sheet', 0)
        self.loading = True
        try:
            self.rich.load(sheets[index])
            self.current, self.sheets, self.active_sheet = note, sheets, index
            self.title_editor.Text = note['title']
            self.update_sheet_controls()
            self.dirty = False
            self.status_text.Text = 'Saved locally' if note.get('revision') else 'New note'
        finally:
            self.loading = False
        self.refresh()

    def choose_sheet(self, sender, args):
        index = self.sheet_combo.SelectedIndex
        if self.loading or index < 0 or index == self.active_sheet:
            return
        if not self.flush():
            self.update_sheet_controls()
            return
        self.loading = True
        try:
            self.rich.load(self.sheets[index])
            self.active_sheet = index
            self.update_sheet_controls()
        except Exception as error:
            self.status_text.Text = 'Could not open sheet: {}'.format(error)
            self.update_sheet_controls()
            return
        finally:
            self.loading = False
        self.changed(None, None)

    def change_orientation(self, sender, args):
        if self.loading or not self.sheets or self.orientation_combo.SelectedIndex < 0:
            return
        self.sheets[self.active_sheet]['orientation'] = 'landscape' if self.orientation_combo.SelectedIndex == 1 else 'portrait'
        self.fill_window_toggle.IsChecked = False
        self.apply_sheet_layout()
        self.update_sheet_label()
        self.changed(None, None)

    def add_sheet(self, sender, args):
        if not self.flush():
            return
        sheet = new_sheet(len(self.sheets) + 1, self.sheets[self.active_sheet]['orientation'])
        self.loading = True
        try:
            self.rich.load(sheet)
            self.sheets.append(sheet)
            self.active_sheet = len(self.sheets) - 1
            self.update_sheet_controls()
        finally:
            self.loading = False
        self.changed(None, None)
        self.body_editor.Focus()

    def flush(self, interactive=True, force=False):
        self.timer.Stop()
        if not self.current or (not self.dirty and not force):
            return True
        try:
            candidate = dict(self.current)
            sheets = self.snapshot_sheets()
            candidate.update(title=self.title_editor.Text, body=u'\n\n'.join(sheet['body'] for sheet in sheets),
                             sheets=sheets, active_sheet=self.active_sheet)
            candidate.pop('rich_text', None)
            try:
                self.store.save(candidate)
            except NoteConflictError:
                if not interactive:
                    self.status_text.Text = 'Changed elsewhere. Click Save to keep a separate copy.'
                    return False
                answer = MessageBox.Show(self, 'This note changed in another Revit session.\nSave your edits as a new note?',
                                         'Notes', MessageBoxButton.YesNo, MessageBoxImage.Question)
                if answer != MessageBoxResult.Yes:
                    return False
                copy = new_note()
                copy.update(title=candidate['title'] + ' (copy)', body=candidate['body'],
                            sheets=candidate['sheets'], active_sheet=candidate['active_sheet'])
                self.store.save(copy)
                candidate = copy
            self.current = candidate
            self.sheets = note_sheets(candidate)
            for index, note in enumerate(self.notes):
                if note['id'] == candidate['id']:
                    self.notes[index] = candidate
                    break
            else:
                self.notes.append(candidate)
            self.dirty = False
            self.status_text.Text = 'Saved at ' + datetime.datetime.now().strftime('%H:%M:%S')
            self.refresh()
            return True
        except Exception as error:
            self.status_text.Text = 'Not saved. Click Save to retry, or Export to keep a copy.'
            if interactive:
                MessageBox.Show(self, 'Could not save this note:\n{}'.format(error), 'Notes',
                                MessageBoxButton.OK, MessageBoxImage.Warning)
            return False

    def new(self, sender, args):
        if not self.flush():
            return
        note = new_note()
        self.notes.append(note)
        self.loading = True
        self.search_box.Text = ''
        self.loading = False
        self.select(note)
        self.title_editor.Focus()
        self.title_editor.SelectAll()

    def choose(self, sender, args):
        if self.loading or self.note_list.SelectedItem is None:
            return
        note_id = self.note_list.SelectedItem.Tag
        if self.current and self.current['id'] == note_id:
            return
        if not self.flush():
            self.refresh()
            return
        note = next((n for n in self.notes if n['id'] == note_id), None)
        if note:
            try:
                if note.get('revision'):
                    note = self.store.load(note_id)
                    self.notes = [note if n['id'] == note_id else n for n in self.notes]
                self.select(note)
            except Exception as error:
                MessageBox.Show(self, 'Could not open this note:\n{}'.format(error), 'Notes')
                self.refresh()

    def changed(self, sender, args):
        if self.loading:
            return
        self.dirty = True
        self.update_sheet_label()
        self.status_text.Text = 'Saving...'
        self.timer.Stop()
        self.timer.Start()

    def search(self, sender, args):
        if not self.loading:
            self.refresh()

    def autosave(self, sender, args):
        self.flush(interactive=False)

    def save(self, sender, args):
        self.flush(force=True)

    def delete(self, sender, args):
        if not self.current:
            return
        answer = MessageBox.Show(self, 'Delete this note?\nSaved notes remain recoverable in the Deleted subfolder.',
                                 'Notes', MessageBoxButton.YesNo, MessageBoxImage.Question)
        if answer != MessageBoxResult.Yes:
            return
        self.timer.Stop()
        try:
            self.store.delete(self.current)
            note_id = self.current['id']
            self.notes = [n for n in self.notes if n['id'] != note_id]
            self.current, self.dirty = None, False
            if self.notes:
                self.select(self.notes[0])
            else:
                self.new(None, None)
        except Exception as error:
            MessageBox.Show(self, 'Could not delete this note:\n{}'.format(error), 'Notes')

    def export(self, sender, args):
        dialog = SaveFileDialog()
        dialog.Title = 'Export note'
        dialog.Filter = 'Word-compatible rich text (*.rtf)|*.rtf|Plain text (*.txt)|*.txt'
        dialog.DefaultExt = '.rtf'
        dialog.AddExtension = True
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', self.title_editor.Text).strip(' .')[:100] or 'Note'
        # Prefix reserved Windows device names so the Save dialog remains usable.
        if filename.split('.')[0].upper() in ('CON', 'PRN', 'AUX', 'NUL') or re.match(r'^(COM|LPT)[1-9](\.|$)', filename, re.I):
            filename = 'Note_' + filename
        dialog.FileName = filename + '.rtf'
        if dialog.ShowDialog(self) == True:
            try:
                if dialog.FilterIndex == 1:
                    export_sheets_rtf(self.snapshot_sheets(), dialog.FileName)
                else:
                    with io.open(dialog.FileName, 'w', encoding='utf-8-sig') as stream:
                        stream.write(self.title_editor.Text + u'\n\n' + export_sheets_text(self.snapshot_sheets()))
                self.status_text.Text = 'Exported to ' + dialog.FileName
            except Exception as error:
                MessageBox.Show(self, 'Could not export this note:\n{}'.format(error), 'Notes')

    def open_folder(self, sender, args):
        try:
            Process.Start('explorer.exe', self.store.directory)
        except Exception as error:
            MessageBox.Show(self, 'Notes folder:\n{}\n\n{}'.format(self.store.directory, error), 'Notes')

    def shortcut(self, sender, args):
        if Keyboard.Modifiers & ModifierKeys.Control:
            if args.Key == Key.S:
                args.Handled = True
                self.save(None, None)
            elif args.Key == Key.N:
                args.Handled = True
                self.new(None, None)

    def closing(self, sender, args):
        if not self.flush():
            answer = MessageBox.Show(self, 'Your latest edits are not saved.\nClose without saving them?',
                                     'Notes', MessageBoxButton.YesNo, MessageBoxImage.Warning)
            args.Cancel = answer != MessageBoxResult.Yes

    def on_closed(self, sender, args):
        self.timer.Stop()
        self.rich.dispose()
        self.closed = True


if __name__ == '__main__':
    # Close the previous plain-text editor through its normal save/close path.
    for legacy_key in ('NdevTools.Handy.Notes.v1', 'NdevTools.Handy.Notes.v2'):
        legacy = AppDomain.CurrentDomain.GetData(legacy_key)
        if legacy is not None and not getattr(legacy, 'closed', True):
            legacy.Close()
            if not getattr(legacy, 'closed', False):
                script.exit()
    if not show_existing(SESSION_KEY):
        try:
            remember(SESSION_KEY, NotesWindow())
        except Exception as error:
            forms.alert('Notes could not start:\n{}'.format(error), title='NdevTools | Notes')
