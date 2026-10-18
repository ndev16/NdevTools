# -*- coding: utf-8 -*-
"""Shared modeless window support; no Revit document operations."""
import os
from System import AppDomain, Environment, Uri, DateTime
from System.Windows import SystemParameters, WindowState
from System.Windows.Media.Imaging import BitmapImage

PANEL_ROOT = os.path.dirname(os.path.dirname(__file__))
BUILD = '2026-10-19-native-maximize-8'
GITHUB_URL = 'https://github.com/ndev16/NdevTools'
LINKEDIN_URL = 'https://www.linkedin.com/in/nataraj016/'

JOKES = (
    'Revit knows what you want. It just refuses to cooperate.',
    'One tiny model change. Twelve brand-new warnings.',
    'My family is fully parametric. My patience is not.',
    'It worked in the previous view.',
    'The model is coordinated. The meetings are not.',
    'I came. I saw. I synchronized.',
    'Warning: coffee level below working tolerance.',
    'That line is not off-axis. It is expressing itself.',
    'The grid moved. Nobody saw anything.',
    'BIM: Because It Moved.',
    'Loading families: the unofficial coffee break.',
    'All constraints are satisfied. Except the deadline.',
)

HELP_TEXT = {
    'notes': u'''HOW TO USE
1. Click New note (Ctrl+N), then enter a title and content.
2. Select text to change its font, size, bold, italic, underline, alignment or lists.
3. Text color, Highlight and Page color open an inline palette. Choose a swatch, RGB values or a hex color, then click Apply color. Cancel or click outside to leave the note unchanged.
4. Use Insert image for a file or Paste image for a copied screenshot. Click an image, change its width and use Resize. Press Delete to remove a selected image.
5. Click Save (Ctrl+S), or let autosave save after a short pause. Export offers Word-compatible RTF with images and formatting, or plain text.

SHEETS & ORIENTATION
Use + Add sheet to append another sheet inside the same note. Choose a sheet from the sheet dropdown. Each sheet can use A4 Portrait (210 x 297 mm) or Landscape (297 x 210 mm), selected independently. New sheets inherit the current orientation. Saving and autosave keep all sheets in one note file. Search includes text from every sheet.

Export includes all sheets in order. In RTF, each sheet starts a new section on an A4 page with its selected orientation and 20 mm margins. Long sheets continue onto further printed pages. Plain-text export includes sheet headings. Portrait and Landscape change the visible A4 sheet as well as its export settings. Use Fill window for a larger writing area; changing orientation returns to A4 page view. Hide notes and the sidebar divider also give you more space.

YOUR NOTEBOOK
Notes are personal files on this computer, outside the Revit model. Existing plain-text notes remain supported. Notes folder opens their location. Previous saved versions and deleted notes remain recoverable there.

BIM HUMOR
Humor is On by default. Use the footer switch to turn it On or Off; your choice is remembered for this tool. Next Joke changes the displayed joke.

HELP & SUPPORT
Use the buttons below to visit NdevTools on GitHub or Nataraj Devaraj on LinkedIn. The main window footer also has a Star NdevTools on GitHub button.''',
    'links': u'''HOW TO USE
1. Choose Image to Text for extracting text from an image, or Convert Case for changing capitalization.
2. Work with the website inside this window. Switching tools keeps both pages open. You can continue working in Revit alongside the window.
3. Back, Forward and Reload act on the selected page. Open in browser opens that page in your normal browser if the embedded browser is unavailable or the site needs it.

WEB TOOLS
Image to Text: https://www.imagetotext.info/
Convert Case: https://convertcase.net/
An internet connection and the embedded WebView2 runtime are required for browsing inside Revit. You choose which text or images to submit on each site; the tool does not send model data automatically.

BIM HUMOR
Humor is On by default. Use the footer switch to turn it On or Off; your choice is remembered for this tool. Next Joke changes the displayed joke.

HELP & SUPPORT
Use the buttons below to visit NdevTools on GitHub or Nataraj Devaraj on LinkedIn. The main window footer also has a Star NdevTools on GitHub button.''',
}


class HandyFooter(object):
    def __init__(self, window, kind):
        self.window, self.kind = window, kind
        self.index = int(DateTime.Now.Ticks % len(JOKES))
        self.config = None
        enabled = True
        try:
            from pyrevit import script
            self.config = script.get_config('ndev_handy_ui')
            enabled = bool(self.config.get_option(kind + '_humor_on', True))
        except Exception:
            pass
        window.humor_toggle.IsChecked = enabled
        self.render()
        window.humor_toggle.Checked += self.toggle
        window.humor_toggle.Unchecked += self.toggle
        window.humor_next_button.Click += self.next_joke

    def render(self):
        enabled = self.window.humor_toggle.IsChecked == True
        self.window.humor_toggle.Content = 'BIM Humor On' if enabled else 'BIM Humor Off'
        self.window.humor_next_button.IsEnabled = enabled
        self.window.humor_text.Text = JOKES[self.index] if enabled else ''

    def toggle(self, sender, args):
        self.render()
        if self.config is not None:
            try:
                from pyrevit import script
                setattr(self.config, self.kind + '_humor_on', self.window.humor_toggle.IsChecked == True)
                script.save_config()
            except Exception:
                pass  # The switch still works if the preference cannot be saved.

    def next_joke(self, sender, args):
        if self.window.humor_toggle.IsChecked == True:
            self.index = (self.index + 1) % len(JOKES)
            self.render()


def open_support_link(window, kind):
    try:
        from pyrevit import script
        script.open_url({'github': GITHUB_URL, 'linkedin': LINKEDIN_URL}[kind])
        return True
    except Exception as error:
        window.status_text.Text = 'Could not open the link: {}'.format(error)
        return False


def show_tool_help(window, kind):
    try:
        existing = getattr(window, '_help_window', None)
        if existing is not None and existing.IsVisible:
            if existing.WindowState == WindowState.Minimized:
                existing.WindowState = WindowState.Normal
            existing.Activate()
            return existing
        from pyrevit import forms
        help_window = forms.WPFWindow(os.path.join(PANEL_ROOT, 'resources', 'HandyHelp.xaml'), handle_esc=False)
        prepare_window(help_window)
        help_window.Owner = window
        name = 'Notes' if kind == 'notes' else 'Useful Links'
        help_window.Title = 'NdevTools | ' + name + ' - Help'
        help_window.help_title.Text = name + ' | Help'
        help_window.help_body.Text = HELP_TEXT[kind]
        help_window.help_github_button.Click += lambda sender, args: open_support_link(help_window, 'github')
        help_window.help_linkedin_button.Click += lambda sender, args: open_support_link(help_window, 'linkedin')
        help_window.close_button.Click += lambda sender, args: help_window.Close()
        window._help_window = help_window
        help_window.Show()
        help_window.Activate()
        return help_window
    except Exception as error:
        window.status_text.Text = 'Could not open Help: {}'.format(error)
        return None


def data_folder(*parts):
    root = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData)
    path = os.path.join(root, 'NdevTools', 'Handy', *parts)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def prepare_window(window):
    # Keep the palette injected by WPFWindow. Replacing Window.Resources in
    # XAML removes pyRevit's brushes before its startup contrast pass runs.
    window.merge_resource_dict(os.path.join(PANEL_ROOT, 'resources', 'HandyTheme.xaml'))
    logo = os.path.join(os.path.dirname(PANEL_ROOT), 'lib', 'sheet_theme', 'ndevtools-logo.png')
    if os.path.isfile(logo):
        window.brand_logo.Source = BitmapImage(Uri(logo))
    area = SystemParameters.WorkArea
    # Keep the initial restored size usable without limiting native maximize.
    # MaxHeight also constrains maximized windows, including on other monitors.
    window.MaxHeight = float('inf')
    window.Height = max(window.MinHeight, min(window.Height, area.Height - 30))
    window.Width = max(window.MinWidth, min(window.Width, area.Width - 30))


def show_existing(key):
    window = AppDomain.CurrentDomain.GetData(key)
    if window is not None and not getattr(window, 'closed', True):
        if window.WindowState == WindowState.Minimized:
            window.WindowState = WindowState.Normal
        window.Show()
        window.Activate()
        return True
    return False


def remember(key, window):
    AppDomain.CurrentDomain.SetData(key, window)
    window.Show()
    window.Activate()
