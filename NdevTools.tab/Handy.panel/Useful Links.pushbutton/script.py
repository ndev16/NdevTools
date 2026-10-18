# -*- coding: utf-8 -*-
"""Two modeless WebView2 pages hosted in Revit; no document operations."""
__persistentengine__ = True

import os
import sys
import clr
from pyrevit import forms, script
from System import AppDomain, Environment, Uri
from System.Diagnostics import Process
from System.Windows import MessageBox, Visibility
from System.Windows.Media import BrushConverter

ROOT = os.path.dirname(__file__)
LIB = os.path.join(os.path.dirname(ROOT), 'lib')
if LIB not in sys.path:
    sys.path.insert(0, LIB)
import ndev_handy_common
if getattr(ndev_handy_common, 'BUILD', None) != '2026-10-19-native-maximize-8':
    reload(ndev_handy_common)
from ndev_handy_common import prepare_window, remember, show_existing, HandyFooter, show_tool_help, open_support_link

SESSION_KEY = 'NdevTools.Handy.UsefulLinks.v1'
SITES = (('Image to Text', 'https://www.imagetotext.info/'),
         ('Convert Case', 'https://convertcase.net/'))


def webview_types():
    """Use the active Revit installation's SDK; never load another Revit version."""
    assemblies = dict((a.GetName().Name, a) for a in AppDomain.CurrentDomain.GetAssemblies())
    if 'Microsoft.Web.WebView2.Wpf' in assemblies:
        clr.AddReference(assemblies['Microsoft.Web.WebView2.Wpf'])
    else:
        base = os.path.dirname(Process.GetCurrentProcess().MainModule.FileName)
        candidates = []
        core = assemblies.get('Microsoft.Web.WebView2.Core')
        if core is not None and core.Location:
            # Keep the WPF wrapper aligned with an SDK already loaded by Revit.
            candidates.append(os.path.dirname(core.Location))
        candidates.extend([base, os.path.join(base, 'AddIns', 'DynamoForRevit')])
        errors = []
        for folder in candidates:
            wpf_path = os.path.join(folder, 'Microsoft.Web.WebView2.Wpf.dll')
            core_path = os.path.join(folder, 'Microsoft.Web.WebView2.Core.dll')
            if not os.path.isfile(wpf_path) or not os.path.isfile(core_path):
                continue
            try:
                clr.AddReferenceToFileAndPath(core_path)
                clr.AddReferenceToFileAndPath(wpf_path)
                break
            except Exception as error:
                errors.append(str(error))
        else:
            raise RuntimeError('The embedded browser components are unavailable in this Revit installation.'
                               + ('\n' + '\n'.join(errors) if errors else ''))
    from Microsoft.Web.WebView2.Wpf import WebView2, CoreWebView2CreationProperties
    return WebView2, CoreWebView2CreationProperties


class UsefulLinksWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(ROOT, 'UsefulLinks.xaml'), handle_esc=False)
        prepare_window(self)
        self.footer = HandyFooter(self, 'links')
        self.help_button.Click += self.show_help
        self.github_button.Click += self.open_github
        self.closed = False
        self.pages = {}
        self.active_url = SITES[0][1]
        self.browser_types = None
        self.image_button.Click += self.image_site
        self.case_button.Click += self.case_site
        self.back_button.Click += self.go_back
        self.forward_button.Click += self.go_forward
        self.reload_button.Click += self.reload_page
        self.external_button.Click += self.open_external
        self.fallback_button.Click += self.open_external
        self.Loaded += self.loaded
        self.Closed += self.on_closed

    def show_help(self, sender, args):
        show_tool_help(self, 'links')

    def open_github(self, sender, args):
        open_support_link(self, 'github')

    def loaded(self, sender, args):
        self.Loaded -= self.loaded
        self.select_site(self.active_url)

    def current(self):
        return self.pages.get(self.active_url)

    def context_for(self, browser):
        return next((page for page in self.pages.values() if page['browser'] == browser), None)

    def select_site(self, url):
        self.active_url = url
        self.fallback_panel.Visibility = Visibility.Collapsed
        brush = BrushConverter()
        for button, selected in ((self.image_button, url == SITES[0][1]), (self.case_button, url == SITES[1][1])):
            button.Background = brush.ConvertFromString('#00C6E8' if selected else '#0B2B40')
            button.Foreground = brush.ConvertFromString('#031A28' if selected else '#E9F6FF')
        for page in self.pages.values():
            page['browser'].Visibility = Visibility.Collapsed
        page = self.current()
        if page:
            if page.get('error'):
                self.show_fallback(page['error'])
            else:
                page['browser'].Visibility = Visibility.Visible
                self.update_toolbar()
                self.status_text.Text = page.get('status', 'Loading...')
            return
        self.address_box.Text = url
        self.status_text.Text = 'Opening ' + url
        try:
            if self.browser_types is None:
                self.browser_types = webview_types()
            WebView2, CreationProperties = self.browser_types
            browser = WebView2()
            properties = CreationProperties()
            local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
            version = os.path.basename(os.path.dirname(Process.GetCurrentProcess().MainModule.FileName))
            profile = os.path.join(local, 'NdevTools', 'Handy', 'WebView2', version)
            if not os.path.isdir(profile):
                os.makedirs(profile)
            properties.UserDataFolder = profile
            browser.CreationProperties = properties
            page = dict(browser=browser, ready=False, status='Loading...', url=url)
            self.pages[url] = page
            browser.CoreWebView2InitializationCompleted += self.initialized
            browser.NavigationStarting += self.navigating
            browser.NavigationCompleted += self.navigated
            self.browser_host.Children.Add(browser)
            browser.Source = Uri(url)
        except Exception as error:
            if page:
                page['error'] = str(error)
            self.show_fallback(str(error))

    def show_fallback(self, message):
        page = self.current()
        if page:
            page['browser'].Visibility = Visibility.Collapsed
        self.fallback_panel.Visibility = Visibility.Visible
        self.fallback_text.Text = ('The embedded browser could not start. Click Open selected site to use the tool in your browser.\n\n' + message)
        self.status_text.Text = 'Embedded browser unavailable. You can use Open in browser.'
        self.update_toolbar()

    def initialized(self, sender, args):
        page = self.context_for(sender)
        if page is None or self.closed:
            return
        if not args.IsSuccess:
            page['error'] = str(args.InitializationException)
            if page['url'] == self.active_url:
                self.show_fallback(page['error'])
            return
        page['ready'] = True
        core = sender.CoreWebView2
        # No host objects or messaging bridge are exposed to the websites.
        core.Settings.IsStatusBarEnabled = False
        core.NewWindowRequested += self.new_window
        core.SourceChanged += self.source_changed

    def navigating(self, sender, args):
        if self.closed:
            return
        # Only normal HTTPS web pages belong in this tools window.
        if not args.Uri.lower().startswith('https://'):
            args.Cancel = True
            if self.context_for(sender) == self.current():
                self.status_text.Text = 'Use Open in browser for this link type.'
            return
        page = self.context_for(sender)
        if page:
            page['status'] = 'Loading...'
            if page['url'] == self.active_url:
                self.status_text.Text = page['status']

    def navigated(self, sender, args):
        page = self.context_for(sender)
        if page is None or self.closed:
            return
        page['status'] = 'Ready' if args.IsSuccess else 'Page could not load. Try Reload or Open in browser. ({})'.format(args.WebErrorStatus)
        if page['url'] == self.active_url:
            self.status_text.Text = page['status']
            self.update_toolbar()

    def source_changed(self, sender, args):
        if not self.closed:
            self.update_toolbar()

    def new_window(self, sender, args):
        args.Handled = True
        if args.Uri and args.Uri.lower().startswith('https://'):
            sender.Navigate(args.Uri)

    def update_toolbar(self):
        page = self.current()
        ready = bool(page and page.get('ready') and not page.get('error'))
        self.back_button.IsEnabled = ready and page['browser'].CanGoBack
        self.forward_button.IsEnabled = ready and page['browser'].CanGoForward
        if page and page['browser'].Source is not None:
            self.address_box.Text = page['browser'].Source.AbsoluteUri
        else:
            self.address_box.Text = self.active_url

    def image_site(self, sender, args):
        self.select_site(SITES[0][1])

    def case_site(self, sender, args):
        self.select_site(SITES[1][1])

    def go_back(self, sender, args):
        page = self.current()
        if page and page.get('ready') and page['browser'].CanGoBack:
            page['browser'].GoBack()

    def go_forward(self, sender, args):
        page = self.current()
        if page and page.get('ready') and page['browser'].CanGoForward:
            page['browser'].GoForward()

    def reload_page(self, sender, args):
        page = self.current()
        if page and page.get('ready') and not page.get('error'):
            page['browser'].Reload()
        else:
            if page:
                self.browser_host.Children.Remove(page['browser'])
                page['browser'].Dispose()
                del self.pages[self.active_url]
            self.select_site(self.active_url)

    def open_external(self, sender, args):
        page = self.current()
        url = self.active_url
        if page and page.get('ready') and page['browser'].Source is not None:
            candidate = page['browser'].Source.AbsoluteUri
            if candidate.lower().startswith('https://'):
                url = candidate
        try:
            script.open_url(url)
        except Exception as error:
            MessageBox.Show(self, 'Could not open the browser:\n{}\n\n{}'.format(url, error), 'Useful Links')

    def on_closed(self, sender, args):
        self.closed = True
        for page in self.pages.values():
            try:
                page['browser'].Dispose()
            except Exception:
                pass
        self.pages.clear()


if __name__ == '__main__':
    if not show_existing(SESSION_KEY):
        try:
            remember(SESSION_KEY, UsefulLinksWindow())
        except Exception as error:
            forms.alert('Useful Links could not start:\n{}'.format(error), title='NdevTools | Useful Links')
