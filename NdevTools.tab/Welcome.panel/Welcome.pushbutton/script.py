# -*- coding: utf-8 -*-

from ndev_i18n import show_localized_dialog as _ndev_show_localized_dialog
"""Ndev Tools - Welcome & About.

A display-only pyRevit ribbon command. Does not alter the Revit document.
Designed for Revit 2022-2027 and IronPython 2.7.

Files installed together in Welcome.pushbutton:
    script.py
    Welcome.xaml
    bundle.yaml
    icon.png
    assets/ndevtools_logo.png
    assets/architecture.png               # retained from original ZIP
    assets/atmosphere_overlay.png        # approved neon wave + soft blend
    assets/approved_design_reference.png
"""

import os
import sys
import webbrowser

from pyrevit import forms, script
from System import Uri, UriKind
from System.Windows import SystemParameters
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption


TITLE = 'Ndev Tools - Welcome & About'
GITHUB_URL = 'https://github.com/ndev16'
LINKEDIN_URL = 'https://www.linkedin.com/in/nataraj016/'
EMAIL = 'devnataraj39@gmail.com'
EMAIL_URL = 'mailto:' + EMAIL + '?subject=Ndev%20Tools%20Feedback'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_pyrevit_version_text():
    """Read the active pyRevit version; never pretend a version was tested."""
    try:
        result = script.get_pyrevit_version().get_formatted()
        if result:
            return str(result)
    except Exception:
        pass
    try:
        from pyrevit import versionmgr
        result = versionmgr.get_pyrevit_version().get_formatted()
        if result:
            return str(result)
    except Exception:
        pass
    return 'Not available'


def get_engine_text():
    """Show the current engine instead of claiming Python 2.7 when not used."""
    try:
        major, minor = sys.version_info[:2]
        if sys.platform == 'cli':
            return 'IronPython {}.{}'.format(major, minor)
        # IronPython can report the .NET runtime platform as 'cli'.
        # On other engines, show what is actually running.
        if 'IronPython' in sys.version:
            return 'IronPython {}.{}'.format(major, minor)
        return 'Python {}.{}'.format(major, minor)
    except Exception:
        return 'IronPython 2.7'


def set_bitmap(target, filepath):
    """Load PNG by absolute path; avoids relative-resource lookup failures."""
    if not os.path.isfile(filepath):
        raise IOError('Required image not found: ' + filepath)
    bitmap = BitmapImage()
    bitmap.BeginInit()
    bitmap.CacheOption = BitmapCacheOption.OnLoad
    bitmap.UriSource = Uri(filepath, UriKind.Absolute)
    bitmap.EndInit()
    bitmap.Freeze()
    target.Source = bitmap


def open_external_link(url):
    """Use the OS-default browser or email app; never modify the model."""
    try:
        from System.Diagnostics import Process, ProcessStartInfo
        info = ProcessStartInfo(url)
        info.UseShellExecute = True
        Process.Start(info)
        return
    except Exception:
        pass
    try:
        if webbrowser.open(url):
            return
    except Exception:
        pass
    forms.alert('Could not open this link automatically.\n\n' + url,
                title=TITLE)


class NdevWelcomeWindow(forms.WPFWindow):

    def __init__(self):
        xaml_path = os.path.join(BASE_DIR, 'Welcome.xaml')
        forms.WPFWindow.__init__(self, xaml_path)

        # The unmodified, original user-supplied NdevTools logo.
        set_bitmap(self.NdevLogoImage,
                   os.path.join(BASE_DIR, 'assets', 'ndevtools_logo.png'))
        # The approved glowing cyan wave is built into this transparent
        # atmospheric layer; all buttons and runtime labels remain live.
        set_bitmap(self.AtmosphereImage,
                   os.path.join(BASE_DIR, 'assets', 'atmosphere_overlay.png'))

        # Dynamic runtime data, without hardcoded pyRevit release claims.
        self.PyRevitVersionText.Text = get_pyrevit_version_text()
        self.IronPythonVersionText.Text = get_engine_text()

        # Real buttons, not clickable regions baked into a background image.
        self.GitHubButton.Click += self.github_click
        self.LinkedInButton.Click += self.linkedin_click
        self.EmailButton.Click += self.email_click
        self.CloseButton.Click += self.close_click
        self.TitleBar.MouseLeftButtonDown += self.drag_click
        self.KeyDown += self.key_down

        # Fit on smaller monitors/high-DPI desktops without clipping.
        try:
            usable = SystemParameters.WorkArea
            self.Width = min(self.Width, max(800.0, usable.Width - 36.0))
            self.Height = min(self.Height, max(470.0, usable.Height - 36.0))
        except Exception:
            pass

    def github_click(self, sender, args):
        open_external_link(GITHUB_URL)

    def linkedin_click(self, sender, args):
        open_external_link(LINKEDIN_URL)

    def email_click(self, sender, args):
        open_external_link(EMAIL_URL)

    def close_click(self, sender, args):
        self.Close()

    def drag_click(self, sender, args):
        try:
            self.DragMove()
        except Exception:
            pass

    def key_down(self, sender, args):
        try:
            from System.Windows.Input import Key
            if args.Key == Key.Escape:
                self.Close()
                args.Handled = True
        except Exception:
            pass


def main():
    window = NdevWelcomeWindow()
    _ndev_show_localized_dialog(window)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        forms.alert(
            'Ndev Tools Welcome could not open.\n\n{}\n\n'
            'Check that Welcome.xaml and assets are inside the SAME '
            'Welcome.pushbutton folder as script.py.'.format(exc),
            title=TITLE)
