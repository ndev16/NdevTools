# -*- coding: utf-8 -*-
"""NdevTools FramePilot: roof, floor, ceiling and flat-truss framing.

Compatible with the existing Wood Framing library and IronPython 2.7.
Private NdevTools roof modules are isolated from extension-wide framing tools.
"""

import os
import sys
import json
import webbrowser
import uuid

__persistentengine__ = True

from pyrevit import revit, DB, script, forms
from pyrevit.forms import WPFWindow
from System import Uri, AppDomain
from System.Windows import (WindowState, Visibility, SystemParameters, MessageBox,
                            MessageBoxButton, MessageBoxImage, Application)
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.Collections.Generic import List
from Autodesk.Revit.UI import ExternalEvent, ExternalEventRequest, IExternalEventHandler
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

TOOL_TITLE = u'NdevTools | FramePilot'
GITHUB_HELP_URL = 'https://github.com/ndev16/NdevTools'
LINKEDIN_HELP_URL = 'https://www.linkedin.com/in/nataraj016/'


def _extension_lib():
    cursor = os.path.abspath(os.path.dirname(__file__))
    while True:
        if cursor.lower().endswith('.extension'):
            return os.path.join(cursor, 'lib')
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return None
        cursor = parent


# Prefer the private roof-specific library shipped with this button.
# This avoids requiring / replacing the extension-wide Wood Framing library.
_LIB_DIR = os.path.join(os.path.dirname(__file__), 'lib')
if not os.path.isfile(os.path.join(_LIB_DIR, 'ndev_roof_config.py')):
    forms.alert('FramePilot library was not found. Reinstall the complete button including its lib folder.',
                title=TOOL_TITLE, warn_icon=True)
    script.exit()
if _LIB_DIR and _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

try:
    from ndev_roof_config import (FramingConfig, SPACING_16OC, SPACING_24OC,
                                  WORKPLANE_FACES, Z_JUSTIFICATION_VALUES)
    from ndev_roof_families import get_available_types_flat, parse_family_type_label
    from ndev_roof_single import RoofFramingEngine
    from ndev_roof_host import analyze_floor_host, analyze_ceiling_host
    from ndev_roof_flat import FlatRoofBeamSystemEngine
    import ndev_roof_sketch as _sketch_module
    if getattr(_sketch_module, 'BUILD', None) != '2026-10-18-sketch-settings-5':
        try:
            from importlib import reload
        except ImportError:
            pass  # IronPython 2.7 provides reload as a built-in.
        _sketch_module = reload(_sketch_module)
    NativeBeamSystemSketch = _sketch_module.NativeBeamSystemSketch
    from ndev_roof_multi import RoofFramingEngineV2
    from ndev_roof_tracking import (delete_tracked_members_for_hosts,
                                ensure_private_tracking)
except Exception as import_error:
    forms.alert(
        'Missing NdevTools private roof-framing library.\n\n'
        'This combined button requires ndev_roof_config, ndev_roof_families, ndev_roof_single, '
        'ndev_roof_multi and ndev_roof_tracking (plus their dependencies) in:\n'
        '{0}\n\nThe private roof library is required.\n'
        'Reinstall the complete FramePilot bundle (including its lib folder) and reload pyRevit.\n\n'
        'Details: {1}'.format(_LIB_DIR or '[extension]/lib', import_error),
        title=TOOL_TITLE,
        warn_icon=True,
    )
    script.exit()


OUTPUT = script.get_output()
XAML_FILE = script.get_bundle_file('NdevRoofConfig.xaml')
HELP_XAML_FILE = script.get_bundle_file('RoofPilotHelp.xaml')
CFG_PATH = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')),
    'pyRevit', 'NdevRoof_LastConfig.json',
)


LEGACY_CFG_PATH = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')),
    'pyRevit', 'WoodFraming_RoofLastConfig.json',
)


PURPOSE_OPTIONS = (u'Roof', u'Flat Truss', u'Floor', u'Ceiling')
PURPOSE_COMMENT = {u'Roof': u'ROOF', u'Flat Truss': u'ROOF',
                   u'Floor': u'FLOOR', u'Ceiling': u'CEIL'}
PURPOSE_BOTTOM = (u'Roof', u'Ceiling')
WORKPLANE_OPTIONS = (u'Top', u'Bottom')
Z_JUSTIFICATION_OPTIONS = (u'Top', u'Center', u'Origin', u'Bottom')
PURPOSE_DESCRIPTIONS = {
    u'Roof': u'Create rafters and ridge boards on supported roof hosts.',
    u'Flat Truss': u'Create structural beam systems on supported flat roof hosts.',
    u'Floor': u'Create structural beam systems on supported floor faces.',
    u'Ceiling': u'Create structural beam systems on supported ceiling faces.',
}
PURPOSE_HOST_LABELS = {u'Roof': u'roofs', u'Flat Truss': u'flat roofs',
                       u'Floor': u'floors', u'Ceiling': u'ceilings'}
SPACING_OPTIONS = (u'12" OC', u'16" OC', u'24" OC', u'Custom')
SPACING_VALUES = {u'12" OC': 12.0, u'16" OC': SPACING_16OC, u'24" OC': SPACING_24OC}
SESSION_KEY = '_ndevtools_framepilot_properties_panel'
SESSION_BUILD = '2026-10-18-sketch-settings-5'


def _placement_choice(combo, choices):
    """Editable dropdowns accept only supported complete choices."""
    text = unicode(combo.Text or u'').strip().lower()
    return text if text in choices else None


def _is_ceiling(element):
    try:
        return isinstance(element, DB.Ceiling)
    except AttributeError:
        try:
            return element.Category.Id.IntegerValue == int(DB.BuiltInCategory.OST_Ceilings)
        except Exception:
            return False


class _HostFilter(ISelectionFilter):
    def __init__(self, purpose):
        self.purpose = purpose

    def AllowElement(self, elem):
        if self.purpose in (u'Roof', u'Flat Truss'):
            return isinstance(elem, DB.RoofBase)
        if self.purpose == u'Floor':
            return isinstance(elem, DB.Floor)
        return _is_ceiling(elem)

    def AllowReference(self, reference, position):
        return False


def _open_support_url(url):
    """Open support link without changing the framing dialog."""
    try:
        if not webbrowser.open(url):
            from System.Diagnostics import Process
            Process.Start(url)
    except Exception as err:
        forms.alert(u'Unable to open link: {0}\n{1}'.format(url, err),
                    title=TOOL_TITLE, warn_icon=True)


class FramePilotHelpDialog(WPFWindow):
    """Instructions and support for the single FramePilot workspace."""
    def __init__(self, owner):
        WPFWindow.__init__(self, HELP_XAML_FILE)
        self.Owner = owner
        self.btn_help_github.Click += self._on_github
        self.btn_help_linkedin.Click += self._on_linkedin

    def _on_github(self, sender, args):
        _open_support_url(GITHUB_HELP_URL)

    def _on_linkedin(self, sender, args):
        _open_support_url(LINKEDIN_HELP_URL)


class RoofFramingDialog(WPFWindow):
    def __init__(self, doc, session):
        WPFWindow.__init__(self, XAML_FILE, handle_esc=False)
        self.session = session
        self._load_brand()
        self.txt_project_context.Text = unicode(doc.Title or u'Active Revit project')
        self.result = None
        self.comment_text = u'ROOF'
        self.tb_comments.Text = u'ROOF'
        self.cb_purpose.ItemsSource = PURPOSE_OPTIONS
        self.cb_purpose.SelectedIndex = 0
        self.cb_workplane.ItemsSource = WORKPLANE_OPTIONS
        self.cb_z_justification.ItemsSource = Z_JUSTIFICATION_OPTIONS
        self.cb_spacing.ItemsSource = SPACING_OPTIONS
        self.cb_spacing.SelectedItem = u'16" OC'
        self.purpose = u'Roof'
        self._labels = list(get_available_types_flat(doc))
        self.cb_rafter_type.ItemsSource = self._labels
        self.cb_ridge_type.ItemsSource = self._labels

        if self._labels:
            self.cb_rafter_type.SelectedIndex = 0
            self.cb_ridge_type.SelectedIndex = 0

        # Editable combos supply their own search field (no separate textboxes).
        # The PART_EditableTextBox is created when WPF applies its template.
        self._filtering_catalog = False
        self._rafter_editor = None
        self._ridge_editor = None
        self.cb_rafter_type.Loaded += self._on_catalog_loaded
        self.cb_ridge_type.Loaded += self._on_catalog_loaded
        self._update_catalog_counts()

        self.cb_purpose.SelectionChanged += self._on_purpose_changed
        self.cb_spacing.SelectionChanged += self._on_spacing_changed
        self.btn_select_hosts.Click += self._on_select_hosts
        self.btn_refresh_types.Click += self._on_refresh_types
        self.btn_sketch_beam_system.Click += self._on_sketch_beam_system
        self.btn_ok.Click += self._on_ok
        self.btn_cancel.Click += self._on_cancel
        self.btn_title_help.Click += self._on_help
        self.btn_title_minimize.Click += self._on_minimize
        self.btn_title_close.Click += self._on_cancel
        self.btn_support_github.Click += self._on_github
        self.bd_title_drag.MouseLeftButtonDown += self._on_drag_window
        self._on_purpose_changed(None, None)
        self._restore_last()
        self._on_spacing_changed(None, None)

    def _load_brand(self):
        """Load the same local NdevTools brand used by ViewPilot."""
        try:
            image = BitmapImage()
            image.BeginInit()
            image.CacheOption = BitmapCacheOption.OnLoad
            image.UriSource = Uri(os.path.join(os.path.dirname(__file__),
                                               'assets', 'ndevtools-logo.png'))
            image.EndInit()
            image.Freeze()
            self.img_brand.Source = image
        except Exception:
            self.img_brand.Visibility = Visibility.Collapsed

    def _filtered_types(self, search_text):
        query = unicode(search_text or u'').strip().lower()
        if not query:
            return list(self._labels)
        # Search both family and type names, case insensitive.
        return [label for label in self._labels
                if query in unicode(label).lower()]

    def _update_catalog_counts(self):
        self.txt_rafter_count.Text = u'{0} of {1} types'.format(
            self.cb_rafter_type.Items.Count, len(self._labels))
        self.txt_ridge_count.Text = u'{0} of {1} types'.format(
            self.cb_ridge_type.Items.Count, len(self._labels))
        self.btn_ok.IsEnabled = bool(self._labels)
        if not self._labels:
            self.txt_catalog_hint.Text = (u'Load a Structural Framing family in Revit, '
                                          u'then reopen FramePilot.')

    def _on_catalog_loaded(self, sender, args):
        """Listen to typing in the editable part of each WPF ComboBox."""
        combo = sender
        try:
            combo.ApplyTemplate()
            editor = combo.Template.FindName('PART_EditableTextBox', combo)
        except Exception:
            editor = None
        if editor is None:
            return
        if combo is self.cb_rafter_type:
            if self._rafter_editor is not None:
                return
            self._rafter_editor = editor
            editor.TextChanged += self._on_rafter_combo_edited
        else:
            if self._ridge_editor is not None:
                return
            self._ridge_editor = editor
            editor.TextChanged += self._on_ridge_combo_edited
        # Select the previous value on focus so users can simply type a search.
        editor.GotKeyboardFocus += self._on_editor_focus

    def _on_editor_focus(self, sender, args):
        try:
            sender.SelectAll()
        except Exception:
            pass

    def _on_rafter_combo_edited(self, sender, args):
        self._filter_catalog(self.cb_rafter_type, sender)

    def _on_ridge_combo_edited(self, sender, args):
        self._filter_catalog(self.cb_ridge_type, sender)

    def _filter_catalog(self, combo, editor):
        """Live substring filter inside the dropdown, without losing typed text.

        Guard re-entrant TextChanged events raised when WPF updates ItemsSource,
        SelectedItem, or combo.Text. Never auto-select a partial match.
        """
        if self._filtering_catalog:
            return
        typed = unicode(editor.Text or u'')
        cursor = editor.SelectionStart
        matches = self._filtered_types(typed)
        try:
            self._filtering_catalog = True
            # Updating the item list can overwrite the editable search text.
            combo.ItemsSource = matches
            combo.SelectedIndex = -1
            if typed in matches:
                combo.SelectedItem = typed
            if unicode(editor.Text or u'') != typed:
                editor.Text = typed
            editor.SelectionStart = min(cursor, len(editor.Text))
            self._update_catalog_counts()
            if typed.strip() and matches and not combo.IsDropDownOpen:
                combo.IsDropDownOpen = True
        finally:
            self._filtering_catalog = False

    def _selected_catalog_label(self, combo):
        """Accept only a real loaded family/type, not a partial search query."""
        typed = unicode(combo.Text or u'').strip()
        selected = combo.SelectedItem
        label = unicode(selected) if selected is not None else u''
        if label in self._labels and typed == label:
            return label
        if typed in self._labels:
            return typed
        return None

    def _on_purpose_changed(self, sender, args):
        choice = unicode(self.cb_purpose.SelectedItem or u'Roof')
        if choice not in PURPOSE_COMMENT:
            return
        self.purpose = choice
        self.txt_purpose_description.Text = PURPOSE_DESCRIPTIONS[choice]
        self.txt_next_step.Text = u'Select {0} in Revit, then click FRAME.'.format(
            PURPOSE_HOST_LABELS[choice])
        self.btn_select_hosts.Content = u'Select ' + PURPOSE_HOST_LABELS[choice].title()
        # Changing the purpose resets its default. Users can then enter a custom note.
        self.tb_comments.Text = PURPOSE_COMMENT[choice]
        self.txt_comments_default.Text = u'Default: ' + PURPOSE_COMMENT[choice]
        default_face = u'Bottom' if choice in PURPOSE_BOTTOM else u'Top'
        self.cb_workplane.SelectedItem = default_face
        self.cb_z_justification.SelectedItem = default_face
        self.txt_workplane_rule.Text = u'Defaults: {0} / {0}. Change either choice independently.'.format(default_face)
        self.btn_ok.Content = u'FRAME ' + choice.upper()
        # Ridge is not applicable for floor, ceiling and flat-truss modes.
        needs_ridge = choice == u'Roof'
        self.cb_ridge_type.IsEnabled = needs_ridge
        self.txt_ridge_count.Visibility = (Visibility.Visible if needs_ridge else Visibility.Collapsed)
        self.ridge_section.Visibility = (Visibility.Visible if needs_ridge else Visibility.Collapsed)

    def _on_spacing_changed(self, sender, args):
        custom = self.cb_spacing.SelectedItem == u'Custom'
        self.tb_custom_spacing.IsEnabled = custom
        self.custom_spacing_row.Visibility = Visibility.Visible if custom else Visibility.Collapsed

    def _on_select_hosts(self, sender, args):
        self.session.request('select', {'purpose': self.purpose})

    def _on_refresh_types(self, sender, args):
        self.session.request('refresh', {})

    def _on_sketch_beam_system(self, sender, args):
        # WPF invokes this outside the Revit API context. Only collect values
        # and queue an ExternalEvent; never let an exception escape into WPF.
        try:
            cfg = self._read_config(require_ridge=False)
            if cfg is None:
                return
            elevation = unicode(self.tb_sketch_elevation.Text or u'').strip()
            if not elevation:
                self._validation_message('Enter Elevation from Level.')
                return
            if self.session.request('sketch', {'elevation': elevation,
                                               'comment': self.comment_text, 'config': cfg}):
                self._save_last(cfg)
        except Exception as error:
            script.get_logger().exception('Could not queue Sketch Beam System')
            self.set_status(u'Sketch could not start: ' + unicode(error))

    def _sketch_preferences(self):
        return {'_sketch_elevation': unicode(self.tb_sketch_elevation.Text or u'0')}

    def set_busy(self, busy):
        self.setup_scroll.IsEnabled = not busy
        self.btn_select_hosts.IsEnabled = not busy
        self.btn_ok.IsEnabled = not busy and bool(self._labels)

    def set_status(self, text):
        self.txt_status.Text = unicode(text)

    def refresh_types(self, labels):
        old_rafter = self._selected_catalog_label(self.cb_rafter_type)
        old_ridge = self._selected_catalog_label(self.cb_ridge_type)
        self._filtering_catalog = True
        try:
            self._labels = list(labels)
            for combo, previous in ((self.cb_rafter_type, old_rafter),
                                    (self.cb_ridge_type, old_ridge)):
                combo.ItemsSource = self._labels
                if previous in self._labels:
                    combo.SelectedItem = previous
                elif self._labels:
                    combo.SelectedIndex = 0
                else:
                    combo.Text = u''
            self._update_catalog_counts()
        finally:
            self._filtering_catalog = False

    def _validation_message(self, text):
        MessageBox.Show(self, text, TOOL_TITLE, MessageBoxButton.OK, MessageBoxImage.Warning)

    def _read_config(self, require_ridge=True):
        workplane = _placement_choice(self.cb_workplane, WORKPLANE_FACES)
        justification = _placement_choice(self.cb_z_justification, Z_JUSTIFICATION_VALUES)
        if workplane is None or justification is None:
            self._validation_message('Choose Top or Bottom for Workplane, and Top, Center, Origin, '
                                     'or Bottom for Z Justification. Choose or type a complete option.')
            return
        rafter_label = self._selected_catalog_label(self.cb_rafter_type)
        ridge_label = (self._selected_catalog_label(self.cb_ridge_type)
                       if require_ridge else rafter_label)
        purpose = unicode(self.cb_purpose.SelectedItem or u'Roof')
        if not rafter_label or (require_ridge and purpose == u'Roof' and not ridge_label):
            self._validation_message('Choose a valid framing family/type (and ridge type for Roof). '
                                     'A partial search term alone is not a selected family.')
            return

        cfg = FramingConfig()
        try:
            rafter_family, rafter_type = parse_family_type_label(str(rafter_label))
            ridge_family, ridge_type = (parse_family_type_label(str(ridge_label))
                                        if ridge_label else (rafter_family, rafter_type))
        except Exception as err:
            self._validation_message('Invalid family type selection: {0}'.format(err))
            return

        cfg.framing_purpose = purpose
        cfg.workplane_face = workplane
        cfg.z_justification = justification
        self.purpose = purpose
        cfg.stud_family_name = rafter_family
        cfg.stud_type_name = rafter_type
        cfg.header_family_name = ridge_family
        cfg.header_type_name = ridge_type
        # V2 may need a valid family type to calculate border board candidates.
        # Use the ridge type only during planning; non-rafter/ridge members
        # are filtered BEFORE place_members() executes.
        cfg.roof_edge_family_name = ridge_family
        cfg.roof_edge_type_name = ridge_type

        spacing_choice = unicode(self.cb_spacing.SelectedItem or u'')
        if spacing_choice in SPACING_VALUES:
            spacing = SPACING_VALUES[spacing_choice]
        elif spacing_choice == u'Custom':
            try:
                spacing = float(self.tb_custom_spacing.Text.strip())
            except (ValueError, TypeError):
                self._validation_message('Enter a valid custom spacing in inches.')
                return
        else:
            self._validation_message('Choose 12", 16", 24" OC, or Custom for framing spacing.')
            return

        # Reject zero, negative and non-finite values. Stored spacing uses inches.
        if not (spacing > 0 and spacing < 1000000):
            self._validation_message('Spacing must be a positive, finite value in inches.')
            return
        cfg.stud_spacing = spacing

        # This button deliberately generates only rafters and ridge boards.
        cfg.include_collar_ties = False
        cfg.include_ceiling_joists = False
        cfg.include_roof_kickers = False

        # Unicode is intentional: supports Tamil/German and other languages
        # in Revit's built-in Comments parameter under IronPython 2.7.
        self.comment_text = unicode(self.tb_comments.Text or u'').strip() or PURPOSE_COMMENT[purpose]
        return cfg

    def _on_ok(self, sender, args):
        cfg = self._read_config()
        if cfg is None:
            return
        if self.session.request('frame', {'config': cfg, 'purpose': self.purpose,
                                          'comment': self.comment_text}):
            self._save_last(cfg)

    def _on_help(self, sender, args):
        """Open a dedicated instructional dialog, not a tab or switch menu."""
        help_window = FramePilotHelpDialog(self)
        help_window.ShowDialog()

    def _on_minimize(self, sender, args):
        self.WindowState = WindowState.Minimized

    def _on_github(self, sender, args):
        _open_support_url(GITHUB_HELP_URL)

    def _on_drag_window(self, sender, args):
        """Keep the compact properties panel movable without maximizing it."""
        try:
            self.DragMove()
        except Exception:
            pass

    def _on_cancel(self, sender, args):
        self.result = None
        self.comment_text = u''
        self.Close()

    def _save_last(self, cfg):
        try:
            data = cfg.to_dict()
            data.update(self._sketch_preferences())
            data['_framing_purpose'] = unicode(self.cb_purpose.SelectedItem or u'Roof')
            data['_rafter_label'] = str(self._selected_catalog_label(self.cb_rafter_type) or '')
            data['_ridge_label'] = str(self._selected_catalog_label(self.cb_ridge_type) or '')
            data.pop('_edge_label', None)  # drop obsolete saved setting
            directory = os.path.dirname(CFG_PATH)
            if not os.path.exists(directory):
                os.makedirs(directory)
            with open(CFG_PATH, 'w') as stream:
                json.dump(data, stream, indent=2)
        except Exception:
            # The tool works even if local preference persistence is unavailable.
            pass

    def _restore_last(self):
        try:
            source_path = CFG_PATH if os.path.exists(CFG_PATH) else LEGACY_CFG_PATH
            if not os.path.exists(source_path):
                return
            with open(source_path, 'r') as stream:
                data = json.load(stream)
            self.tb_sketch_elevation.Text = unicode(data.get('_sketch_elevation', u'0'))
            last_purpose = data.get('_framing_purpose', data.get('framing_purpose', u'Roof'))
            if last_purpose in PURPOSE_OPTIONS:
                self.cb_purpose.SelectedItem = last_purpose
            # Legacy files without placement choices keep their purpose defaults.
            for control, key, choices in (
                    (self.cb_workplane, 'workplane_face', WORKPLANE_FACES),
                    (self.cb_z_justification, 'z_justification', Z_JUSTIFICATION_VALUES)):
                value = unicode(data.get(key, u'') or u'').strip().lower()
                if value in choices:
                    control.SelectedItem = value.title()
            for control, key in (
                    (self.cb_rafter_type, '_rafter_label'),
                    (self.cb_ridge_type, '_ridge_label')):
                label = data.get(key, '')
                if label in self._labels:
                    control.SelectedItem = label

            spacing = float(data.get('stud_spacing', SPACING_16OC))
            matching = next((label for label in SPACING_OPTIONS if label in SPACING_VALUES
                             and abs(spacing - SPACING_VALUES[label]) < 0.001), None)
            if matching:
                self.cb_spacing.SelectedItem = matching
            else:
                self.cb_spacing.SelectedItem = u'Custom'
                self.tb_custom_spacing.Text = str(spacing)
        except Exception:
            pass


def _write_new_member_comments(placed_elements, text_value):
    """Write ONLY the user's note to newly created Revit instance Comments.

    No tracking metadata, invisible tags, or other appended text. By default
    the value follows the selected purpose. The caller passes only newly placed elements.
    """
    written = 0
    skipped = 0
    seen_ids = set()
    for element in placed_elements or []:
        if element is None:
            skipped += 1
            continue
        element_id = getattr(element, 'Id', None)
        key = getattr(element_id, 'IntegerValue', None)
        if key is not None and key in seen_ids:
            continue
        if key is not None:
            seen_ids.add(key)
        try:
            param = element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if param is None or param.IsReadOnly or param.StorageType != DB.StorageType.String:
                skipped += 1
                continue
            if not param.Set(unicode(text_value)):
                skipped += 1
                continue
            written += 1
        except Exception:
            skipped += 1
    return written, skipped


def _roof_id(roof):
    element_id = getattr(roof, 'Id', None)
    if element_id is None:
        return '?'
    return getattr(element_id, 'IntegerValue', getattr(element_id, 'Value', '?'))


def _selected_hosts(doc, purpose, uidoc, force_pick=False):
    selection_filter = _HostFilter(purpose)
    hosts = [] if force_pick else [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds()]
    hosts = [element for element in hosts
             if element is not None and selection_filter.AllowElement(element)]
    if not hosts:
        try:
            picked = uidoc.Selection.PickObjects(
                ObjectType.Element, selection_filter,
                'Select {0} host element(s) to frame'.format(purpose))
            hosts = [doc.GetElement(item.ElementId) for item in picked]
        except OperationCanceledException:
            return []

    unique = []
    ids = set()
    for host in hosts:
        if host is None:
            continue
        key = str(_roof_id(host))
        if key not in ids:
            unique.append(host)
            ids.add(key)
    return unique


def _plan_planar_host(doc, host, purpose, config, beam_engine):
    if purpose in (u'Roof', u'Flat Truss'):
        from ndev_roof_host import analyze_roof_host
        host_info = analyze_roof_host(doc, host, config)
        # Flat trusses require flat roof faces; no silent mono-slope routing.
        is_flat_only = purpose == u'Flat Truss'
    elif purpose == u'Floor':
        host_info = analyze_floor_host(doc, host, config)
        is_flat_only = False
    else:
        host_info = analyze_ceiling_host(doc, host, config)
        is_flat_only = False
    if host_info is None:
        raise _UnsupportedRoofError('No supported planar surface was found.')
    try:
        members = beam_engine.calculate_members_from_info(
            host_info, require_flat=is_flat_only)
    except Exception as err:
        raise _UnsupportedRoofError(str(err))
    return ('Beam System', beam_engine, members, host_info,
            ['Native beam systems; work plane {0}; no ridge'.format(config.workplane_face)])


def _sketch_host_plane(doc, uidoc, config):
    """Reuse the current host context and FRAME's face analysis; never prompt."""
    host_filter = _HostFilter(config.framing_purpose)
    hosts = [doc.GetElement(element_id) for element_id in uidoc.Selection.GetElementIds()]
    hosts = [host for host in hosts if host is not None and host_filter.AllowElement(host)]
    if not hosts:
        # Also accept a face already chosen as the active Revit work plane.
        try:
            reference = doc.ActiveView.SketchPlane.GetPlaneReference()
            host = doc.GetElement(reference.ElementId) if reference is not None else None
            if host is not None and host_filter.AllowElement(host):
                hosts = [host]
        except Exception:
            pass
    if len(hosts) != 1:
        return None
    purpose = config.framing_purpose
    if purpose in (u'Roof', u'Flat Truss'):
        from ndev_roof_host import analyze_roof_host
        info = analyze_roof_host(doc, hosts[0], config)
    elif purpose == u'Floor':
        info = analyze_floor_host(doc, hosts[0], config)
    else:
        info = analyze_ceiling_host(doc, hosts[0], config)
    if info is None:
        return None
    planes = getattr(info, 'planes', None) or [info]
    # A manual sketch describes one work plane. Do not invent a face choice
    # for a multi-face roof or change the existing native sketch workflow.
    return planes[0] if len(planes) == 1 else None


def _members_without_edge_boards(members, allow_ridge=True):
    """Whitelist ONLY rafters, ridge boards, and V2 rafter beam systems.

    This intentionally removes eave/rim/fascia/rake/ledger boards and all
    unrelated secondary framing types irrespective of their naming schemes.
    """
    allowed_types = set((
        'RAFTER',
        'RIDGE_BOARD',
        'RIDGE_BOARD_V2',
        'BEAM_SYSTEM_V2',
        'FLAT_BEAM_SYSTEM',
    ))
    retained = []
    removed = 0
    unclassified = 0
    for member in members:
        role = getattr(member, 'member_type', None)
        if role is None or not str(role).strip():
            unclassified += 1
            continue
        role_name = str(role).strip().upper()
        if role_name in allowed_types and (allow_ridge or role_name not in ('RIDGE_BOARD', 'RIDGE_BOARD_V2')):
            retained.append(member)
        else:
            removed += 1
    return retained, removed, unclassified


def _plan_roof(roof, single_engine, multi_engine, flat_engine):
    """Try shed-roof engine first; use the V2 engine for other roof shapes.

    No model changes happen during this planning phase. An unsupported roof
    does not cause previously tracked framing to be deleted.
    """
    single_reason = 'Not a supported single-slope roof.'
    try:
        raw_members, info = single_engine.calculate_members(roof, mode='stick')
        simple_type = getattr(info, 'roof_type', None) if info is not None else None
        # Flat roofs use a genuine Revit Structural Beam System, never loose
        # RAFTER family instances generated by the single-slope scanline path.
        # Validate every flat face BEFORE replacing old tracked framing.
        if simple_type == 'flat' and info is not None and getattr(info, 'single_slope_supported', False):
            try:
                flat_members = flat_engine.calculate_members_from_info(info)
            except Exception as flat_error:
                # Do not fall through to another engine that might ignore
                # roof openings and frame across the void.
                return (None, None, [], None,
                        ['Flat roof Beam System boundary unsupported: {0}'.format(flat_error)])
            return ('Flat', flat_engine, flat_members, info,
                    ['Native Revit Structural Beam System; no ridge board'])
        if simple_type == 'shed' and info is not None and getattr(info, 'single_slope_supported', False):
            try:
                mono_systems = flat_engine.calculate_members_from_info(info, require_flat=False)
                return ('Mono-Slope', flat_engine, mono_systems, info,
                        ['Native sloped beam system on selected work plane; no ridge'])
            except Exception as mono_err:
                return (None, None, [], None,
                        ['Mono-slope beam system unsupported: {0}'.format(mono_err)])
        members, discarded, unclassified = _members_without_edge_boards(
            raw_members, allow_ridge=(simple_type not in ('flat', 'shed')))
        if unclassified:
            single_reason = ('{0} generated members have no member_type and '
                             'were not placed for safety.').format(unclassified)
        if info is not None and getattr(info, 'single_slope_supported', True):
            if members:
                return ('Flat' if simple_type == 'flat' else 'Mono-Slope', single_engine, members, info, ['{0} non-rafter/ridge members excluded'.format(discarded)] if discarded else [])
            single_reason = 'Single-slope engine returned no permissible framing members (possibly all excluded or unclassified).' 
        elif info is not None:
            single_reason = str(getattr(
                info, 'single_slope_support_reason', single_reason))
        else:
            single_reason = 'Single-slope engine returned no roof analysis.'
    except Exception as err:
        single_reason = str(err)

    multi_reason = 'No supported multi-slope plan.'
    try:
        raw_members, info = multi_engine.calculate_members(roof)
        members, discarded, unclassified = _members_without_edge_boards(raw_members)
        plan = getattr(info, 'v2_plan', None) if info is not None else None
        if plan is not None and getattr(plan, 'supported', False) and members:
            warnings = list(getattr(plan, 'warnings', None) or [])
            if discarded:
                warnings.append('{0} non-rafter/ridge members excluded'.format(discarded))
            if unclassified:
                warnings.append('{0} unclassified members skipped to avoid edge boards'.format(unclassified))
            return ('Multi-Slope', multi_engine, members, info, warnings)
        if plan is not None and getattr(plan, 'warnings', None):
            multi_reason = '; '.join(str(msg) for msg in plan.warnings)
        elif plan is not None and getattr(plan, 'supported', False):
            multi_reason = 'Multi-slope engine returned no permissible framing members (possibly all excluded or unclassified).' 
    except Exception as err:
        multi_reason = str(err)

    return (None, None, [], None, [
        'Single-slope: ' + single_reason,
        'Multi-slope: ' + multi_reason,
    ])


class _UnsupportedRoofError(Exception):
    pass


def _frame_hosts(doc, cfg, purpose, custom_comment, hosts):
    single_engine = RoofFramingEngine(doc, cfg)
    flat_engine = FlatRoofBeamSystemEngine(doc, cfg)
    multi_engine = RoofFramingEngineV2(doc, cfg)
    stats = {'generated': 0, 'placed': 0, 'deleted': 0,
             'commented': 0, 'skipped': 0, 'justification_warnings': 0}
    errors = []
    OUTPUT.print_md('## NDEV TOOLS | FRAMEPILOT')
    OUTPUT.print_md('- Purpose: **{0}**'.format(purpose))
    OUTPUT.print_md('- Selected hosts: **{0}**'.format(len(hosts)))
    OUTPUT.print_md('- Spacing: **{0:.2f} in OC**'.format(cfg.stud_spacing))
    OUTPUT.print_md('- Comments: **{0}**'.format(custom_comment))
    OUTPUT.print_md('- Workplane: **{0}**; Z Justification: **{1}**'.format(
        cfg.workplane_face.upper(), cfg.z_justification.upper()))

    for host in hosts:
        host_id = _roof_id(host)
        try:
            with revit.Transaction('FramePilot: {0} {1}'.format(purpose, host_id)):
                if purpose == u'Roof':
                    kind, engine, members, host_info, notes = _plan_roof(
                        host, single_engine, multi_engine, flat_engine)
                else:
                    kind, engine, members, host_info, notes = _plan_planar_host(
                        doc, host, purpose, cfg, flat_engine)
                if kind is None or not members:
                    raise _UnsupportedRoofError(' / '.join(notes or ['No valid framing members']))
                if not ensure_private_tracking():
                    raise RuntimeError('Private framing ownership storage unavailable.')
                allowed_kind = 'roof' if purpose in (u'Roof', u'Flat Truss') else purpose.lower()
                deleted = delete_tracked_members_for_hosts(doc, [host], (allowed_kind,))
                placed = engine.place_members(members, host_info)
                if not placed:
                    raise RuntimeError('Nothing placed; previous framing preserved.')
                commented, comment_skipped = _write_new_member_comments(placed, custom_comment)
                if comment_skipped:
                    OUTPUT.print_md('  - Warning: {0} created elements have read-only/missing Comments'.format(
                        comment_skipped))
                just_warnings = list(getattr(engine, '_justification_warnings', []) or [])
        except Exception as err:
            stats['skipped'] += 1
            errors.append('Host {0}: {1}'.format(host_id, err))
            continue
        stats['generated'] += len(members)
        stats['placed'] += len(placed)
        stats['deleted'] += int(deleted or 0)
        stats['commented'] += commented
        stats['justification_warnings'] += len(just_warnings)
        OUTPUT.print_md('- Host **{0}**: **{1}**, {2} elements, Comments on {3}'.format(
            host_id, kind, len(placed), commented))
        for note in notes or []:
            OUTPUT.print_md('  - {0}'.format(str(note)))
        for warning in just_warnings:
            OUTPUT.print_md('  - **Justification warning:** {0}'.format(warning))
    OUTPUT.print_md(
        u'\n## Summary\n- Hosts framed: **{0}**\n- Hosts skipped: **{1}**'
        u'\n- New elements: **{2}**\n- Old elements replaced: **{3}**'
        u'\n- Elements with Comments: **{4}**\n- Justification warnings: **{5}**'.format(
            len(hosts) - stats['skipped'], stats['skipped'],
            stats['placed'], stats['deleted'], stats['commented'],
            stats['justification_warnings']))
    if errors:
        OUTPUT.print_md(u'\n### Skipped hosts / errors')
        for error in errors:
            OUTPUT.print_md('- ' + error)
    return stats, errors


def _qa_trace(message):
    script.get_logger().debug(message)


class FramePilotSession(object):
    """Keep the modeless WPF panel alive and enter Revit only via ExternalEvent."""
    def __init__(self, doc):
        self.document = doc
        self.build = SESSION_BUILD
        self.closed = False
        self.pending = None
        self.executing = False
        self.disposed = False
        self.sketch_job = None
        self.window = RoofFramingDialog(doc, self)
        session = self

        class FramePilotEventHandler(IExternalEventHandler):
            __namespace__ = 'NdevTools.FramePilot.N' + uuid.uuid4().hex

            def Execute(self, application):
                session.execute(application)

            def GetName(self):
                return 'NdevTools FramePilot properties panel'

        self.handler = FramePilotEventHandler()
        self.external_event = ExternalEvent.Create(self.handler)
        self.window.Closed += self._on_closed

    def show(self):
        if not self.closed:
            if self.window.WindowState == WindowState.Minimized:
                self.window.WindowState = WindowState.Normal
            self.window.Show()
            self.window.Activate()
            _qa_trace("shown: visible={0} left={1} top={2} height={3} width={4}".format(self.window.IsVisible,self.window.Left,self.window.Top,self.window.Height,self.window.Width))

    def request(self, action, payload):
        if self.closed or self.pending is not None or self.executing:
            return False
        self.pending = (action, payload)
        self.window.set_busy(True)
        self.window.set_status(u'Waiting for Revit... Finish any active command to continue.')
        try:
            result = self.external_event.Raise()
            if result != ExternalEventRequest.Accepted:
                raise RuntimeError('Finish the current Revit command, then try again.')
        except Exception as err:
            self.pending = None
            self.window.set_busy(False)
            self.window.set_status(unicode(err))
            return False
        return True

    def execute(self, application):
        job = self.pending
        self.pending = None
        if self.closed:
            self._dispose()
            return
        if job is None:
            return
        self.executing = True
        try:
            # Event subscription changes require an API callback. A second
            # modeless button click must NOT remove handlers in request().
            if self.sketch_job is not None:
                self.sketch_job.cancel()
                self.sketch_job = None
            uidoc = application.ActiveUIDocument
            if (uidoc is None or not self.document.IsValidObject
                    or not uidoc.Document.Equals(self.document)):
                self.window.set_status(u'Return to this panel\'s project, or reopen FramePilot in the active project.')
                return
            doc = uidoc.Document
            action, payload = job
            if action == 'sketch':
                self.sketch_job = NativeBeamSystemSketch(
                    application, doc, self._sketch_finished, _write_new_member_comments)
                try:
                    config = payload['config']
                    host_plane = _sketch_host_plane(doc, uidoc, config)
                    self.sketch_job.start(payload['elevation'], payload['comment'],
                                          config=config, host_plane=host_plane)
                except Exception:
                    self.sketch_job.cancel()
                    self.sketch_job = None
                    raise
                self.window.set_status(u'In Revit, choose Sketch Beam System. Finish the boundary, '
                                       u'then exit the tool to apply the current FramePilot settings.')
                return
            if action == 'refresh':
                labels = list(get_available_types_flat(doc))
                self.window.refresh_types(labels)
                self.window.set_status(u'{0} loaded framing types refreshed.'.format(len(labels)))
                return
            if action not in ('select', 'frame'):
                raise ValueError('Unknown FramePilot action.')
            purpose = payload['purpose']
            if purpose not in PURPOSE_OPTIONS:
                raise ValueError('Choose a supported framing purpose.')
            # Picking and all model access happen inside this Revit callback.
            self.window.Hide()
            hosts = _selected_hosts(doc, purpose, uidoc, force_pick=(action == 'select'))
            if not hosts:
                self.window.set_status(u'Selection cancelled. No framing created; existing settings retained.')
                return
            if action == 'select':
                uidoc.Selection.SetElementIds(List[DB.ElementId]([host.Id for host in hosts]))
                self.window.set_status(u'{0} matching {1} selected. Ready to frame.'.format(
                    len(hosts), PURPOSE_HOST_LABELS[purpose]))
                return
            stats, errors = _frame_hosts(doc, payload['config'], purpose, payload['comment'], hosts)
            self.window.set_status(u'Created {0} members; {1} host(s) skipped.{2}'.format(
                stats['placed'], stats['skipped'], u' See the report for details.' if errors else u''))
        except OperationCanceledException:
            self.window.set_status(u'Selection cancelled. No framing created.')
        except Exception as err:
            self.window.set_status(u'FramePilot stopped: ' + unicode(err))
        finally:
            self.executing = False
            if not self.closed:
                self.window.set_busy(False)
                self.show()
            else:
                self._dispose()

    def _sketch_finished(self, message):
        self.sketch_job = None
        if not self.closed:
            self.window.set_busy(False)
            self.window.set_status(message)
            self.show()

    def _on_closed(self, sender, args):
        _qa_trace("window closed")
        self.closed = True
        self.pending = None
        if self.sketch_job is not None:
            # Closing WPF is outside API context. Let the listener detach
            # itself at the next Revit idle callback, without modifying a model.
            self.sketch_job.request_cancel()
            self.sketch_job = None
        if AppDomain.CurrentDomain.GetData(SESSION_KEY) is self:
            AppDomain.CurrentDomain.SetData(SESSION_KEY, None)
        # A queued callback owns the handler until it can observe closed=True.
        if not self.executing and not self.external_event.IsPending:
            self._dispose()

    def _dispose(self):
        if not self.disposed:
            self.disposed = True
            self.external_event.Dispose()


def main():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert('Open a Revit project before running FramePilot.', title=TOOL_TITLE)
        return
    existing = AppDomain.CurrentDomain.GetData(SESSION_KEY)
    if existing and not existing.closed:
        if (getattr(existing, 'build', None) == SESSION_BUILD
                and existing.document.IsValidObject and existing.document.Equals(doc)):
            if not existing.executing:
                existing.show()
            return
        if existing.pending is not None or existing.executing:
            forms.alert('Finish the current FramePilot action before changing projects.', title=TOOL_TITLE)
            return
        existing.window.Close()
    # Replace earlier unregistered FramePilot windows after an in-session update.
    if Application.Current is not None:
        for candidate in list(Application.Current.Windows):
            if candidate.Title == TOOL_TITLE:
                candidate.Close()
    _qa_trace("creating session")
    session = FramePilotSession(doc)
    _qa_trace("created session")
    area = SystemParameters.WorkArea
    session.window.MaxHeight = max(540, area.Height - 24)
    session.window.Height = min(session.window.Height, session.window.MaxHeight)
    session.window.Left = max(area.Left, area.Right - session.window.Width - 12)
    session.window.Top = area.Top + 10
    AppDomain.CurrentDomain.SetData(SESSION_KEY, session)
    session.show()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        _qa_trace(traceback.format_exc())
        raise
