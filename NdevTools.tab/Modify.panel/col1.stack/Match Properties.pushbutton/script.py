# -*- coding: utf-8 -*-
"""Match native model and annotation types and editable properties."""
from __future__ import unicode_literals
import io
import os
import tempfile
import traceback

from pyrevit import DB, forms, revit, script
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent

import match_properties_core as core
import match_properties_revit as adapter

__title__ = 'Match Properties'
__author__ = 'NdevTools'
__persistentengine__ = True
__doc__ = 'Pick a model element, text note, tag or annotation, then compatible targets. Match type and editable properties.'


class StartWindow(forms.WPFWindow):
    def __init__(self, controller):
        self.controller = controller
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'MatchProperties.xaml'))
        self.start_button.Click += self.start
        self.cancel_button.Click += self.cancel
        self.github_button.Click += self.open_github
        self.help_button.Click += self.show_help
        self.Closed += lambda s, e: controller.close()
        try:
            from System import Uri
            from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
            brand = BitmapImage()
            brand.BeginInit()
            brand.CacheOption = BitmapCacheOption.OnLoad
            brand.UriSource = Uri(os.path.join(os.path.dirname(__file__), 'assets', 'ndevtools-logo.png'))
            brand.EndInit()
            brand.Freeze()
            self.brand_image.Source = brand
        except Exception:
            pass

    def start(self, sender, args):
        self.controller.request('source')

    def open_github(self, sender, args):
        script.open_url('https://github.com/ndev16/NdevTools')

    def show_help(self, sender, args):
        from pyrevit.coreutils import applocales, yaml
        from System.Windows import FlowDirection
        bundle = os.path.dirname(__file__)
        tips = yaml.load_as_dict(os.path.join(bundle, 'bundle.yaml'))['tooltip']
        locale = applocales.get_current_applocale()
        language = locale.locale_code if locale else 'en_us'
        heading, body = tips.get(language, tips['en_us']).strip().split('\n', 1)
        dialog = forms.WPFWindow(os.path.join(bundle, 'MatchPropertiesHelp.xaml'))
        dialog.Owner = self
        dialog.Resources.MergedDictionaries.Add(self.Resources)
        dialog.heading.Text = heading.strip()
        dialog.instructions.Text = body.strip()
        if language in ('ar', 'fa'):
            dialog.FlowDirection = FlowDirection.RightToLeft
        dialog.ShowDialog()

    def cancel(self, sender, args):
        self.Close()


class PropertySelection(forms.WPFWindow):
    def __init__(self, doc, source, controller):
        self.controller = controller
        from System.Windows.Controls import CheckBox
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'PropertySelection.xaml'))
        snapshot = adapter.source_snapshot(doc, source)
        self.source_label.Text = snapshot['label']
        self.choices = []
        self.level_keys = set(r['key'] for r in snapshot['rows'] if adapter.is_level_reference(doc, r))
        self.type_choice = CheckBox()
        self.type_choice.Content = ('Text type (font, size and shared text-style properties)'
                                    if adapter.is_instance_of(source, 'TextNote') else
                                    'Element type (includes shared type properties)')
        self.type_choice.IsChecked = True
        self.property_rows.Children.Add(self.type_choice)
        for row in snapshot['rows']:
            box = CheckBox()
            box.Content = '{}  |  {}'.format(row['name'], row['value'])
            box.ToolTip = 'Source value: {}'.format(row['value'])
            box.IsChecked = True
            self.property_rows.Children.Add(box)
            self.choices.append((row, box))
        self.notes.Text = ('Text-note content and tag hosts are retained. Calculated fields are omitted. Target read-only fields are reported. '
                           'Type changes can affect dependent properties; conflicts with unchecked fields retain the target.')
        self.all_button.Click += lambda s, e: self.set_all(True)
        self.none_button.Click += lambda s, e: self.set_all(False)
        self.levels_button.Click += lambda s, e: self.exclude_levels()
        self.continue_button.Click += self.accept
        self.cancel_button.Click += lambda s, e: self.Close()
        self.Closed += lambda s, e: controller.selection_closed(self)

    def set_all(self, value):
        self.type_choice.IsChecked = value
        for row, box in self.choices:
            box.IsChecked = value

    def exclude_levels(self):
        for row, box in self.choices:
            if row['key'] in self.level_keys:
                box.IsChecked = False

    def accept(self, sender, args):
        self.selected_keys = [row['key'] for row, box in self.choices if box.IsChecked]
        self.copy_type = bool(self.type_choice.IsChecked)
        if not self.selected_keys and not self.copy_type:
            self.notes.Text = 'Select at least one property to continue.'
            return
        self.controller.request('targets')


class ReportWindow(forms.WPFWindow):
    def __init__(self, report, result):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'Report.xaml'))
        self.report = report
        updated = sum(t['status'].startswith('Updated') for t in result.get('targets', []))
        unchanged = sum(t['status'] == 'Already matches' for t in result.get('targets', []))
        exceptions = sum(t['status'] not in ('Updated', 'Already matches') for t in result.get('targets', []))
        self.summary.Text = '{} updated  |  {} already matched  |  {} with exceptions'.format(updated, unchanged, exceptions)
        self.report_text.Text = report
        self.copy_button.Click += self.copy_report
        self.close_button.Click += self.close_report

    def copy_report(self, sender, args):
        try:
            from System.Windows import Clipboard
            Clipboard.SetText(self.report)
            self.copy_status.Text = 'Report copied.'
        except Exception as error:
            self.copy_status.Text = 'Clipboard unavailable. Select the report text and press Ctrl+C.'

    def close_report(self, sender, args):
        self.Close()


def save_report(report):
    folder = tempfile.mkdtemp(prefix='NdevTools-MatchProperties-')
    path = os.path.join(folder, 'match-properties-report.txt')
    with io.open(path, 'w', encoding='utf-8') as stream:
        stream.write(report)
    return path


class MatchEventHandler(IExternalEventHandler):
    def __init__(self, controller):
        self.controller = controller

    def GetName(self):
        return 'NdevTools Match Properties'

    def Execute(self, app):
        self.controller.execute(app)


class MatchController(object):
    def __init__(self, doc):
        self.doc = doc
        self.source_id = None
        self.selection = None
        self.reports = []
        self.pending = None
        self.closed = False
        self.executing = False
        self.handler = MatchEventHandler(self)
        self.event = ExternalEvent.Create(self.handler)
        self.start = StartWindow(self)

    def show(self):
        if not self.closed:
            window = self.selection or self.start
            window.IsEnabled = True
            window.Show()
            from System.Windows import WindowState
            if window.WindowState == WindowState.Minimized:
                window.WindowState = WindowState.Normal
            window.Activate()

    def request(self, action):
        if self.closed or self.pending is not None:
            return
        self.pending = action
        window = self.selection or self.start
        window.IsEnabled = False
        try:
            status = str(self.event.Raise())
            if status not in ('Accepted', 'Pending'):
                raise ValueError('Revit could not queue the request. Finish the active command and try again.')
        except Exception as error:
            self.pending = None
            window.IsEnabled = True
            forms.alert(str(error), title='Match Properties')

    def selection_closed(self, window):
        if self.selection is window:
            self.selection = None
            if not self.closed:
                self.show()

    def close(self):
        self.closed = True
        if self.selection is not None:
            self.selection.Close()
        for window in list(self.reports):
            window.Close()
        if self.pending is None and not self.executing:
            self.event.Dispose()

    def execute(self, app):
        if self.closed:
            self.pending = None
            self.event.Dispose()
            return
        action = self.pending
        self.executing = True
        window = self.selection or self.start
        try:
            uidoc = app.ActiveUIDocument
            if uidoc is None or not self.doc.IsValidObject or uidoc.Document != self.doc:
                raise ValueError('Return to the project where Match Properties was opened, or reopen the tool in this project.')
            if self.doc.IsReadOnly or self.doc.IsModifiable:
                raise ValueError('Finish the current edit before matching properties.')
            window.Hide()
            if action == 'source':
                reference = uidoc.Selection.PickObject(ObjectType.Element, adapter.ModelFilter(),
                                                      'Select the element whose properties you want to copy')
                source = self.doc.GetElement(reference.ElementId)
                self.source_id = source.Id
                self.selection = PropertySelection(self.doc, source, self)
            elif action == 'targets':
                source = self.doc.GetElement(self.source_id)
                if source is None:
                    raise ValueError('The source was deleted. Close the property list and select another source.')
                references = uidoc.Selection.PickObjects(ObjectType.Element, adapter.ModelFilter(source),
                                                         'Select similar target elements, then click Finish')
                targets = [self.doc.GetElement(r.ElementId) for r in references]
                if not targets:
                    return
                with forms.ProgressBar(title='Matching properties ({value} of {max_value})', cancellable=True) as progress:
                    result = adapter.run(self.doc, source, targets, progress,
                                         selected_keys=self.selection.selected_keys, copy_type=self.selection.copy_type)
                report = core.format_report(result)
                try:
                    path = save_report(report)
                    report += '\n\nSaved report: ' + path
                except Exception as error:
                    report += '\n\nCould not save report: ' + str(error)
                report_window = ReportWindow(report, result)
                self.reports.append(report_window)
                report_window.Closed += lambda s, e: self.reports.remove(s) if s in self.reports else None
                report_window.Show()
        except OperationCanceledException:
            pass
        except Exception as error:
            print(traceback.format_exc())
            forms.alert(str(error), title='Match Properties')
        finally:
            self.pending = None
            self.executing = False
            self.show()
            if self.closed:
                self.event.Dispose()


def main():
    global _match_controller
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument or doc.IsReadOnly:
        forms.alert('Open an editable Revit project to match model or annotation properties.', title='Match Properties')
        return
    _match_controller = MatchController(doc)
    _match_controller.show()


if __name__ == '__main__':
    try:
        main()
    except OperationCanceledException:
        pass
    except Exception as error:
        print(traceback.format_exc())
        forms.alert('Match Properties stopped: {}\nSee the pyRevit output for details.'.format(error), title='Match Properties')
