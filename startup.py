# -*- coding: utf-8 -*-
"""Optional post-load ribbon language sync for NdevTools (IronPython 2.7).

Only updates NdevTools ribbon labels and tooltips on the next UI idle.
Does NOT change the pyRevit language preference or Revit model/document.
A failed event registration must NEVER block NdevTools from loading.
"""
import os
import sys

try:
    # Startup runs in the extension root, not the tab's Python lib folder.
    _lib = os.path.join(os.path.dirname(__file__), 'NdevTools.tab', 'lib')
    if _lib not in sys.path:
        sys.path.insert(0, _lib)

    from pyrevit import HOST_APP, framework, UI
    from ndev_i18n import sync_ribbon_to_revit_language

    _uiapp = HOST_APP.uiapp
    _sync_handler = None

    def _sync_on_idle(sender, args):
        global _sync_handler
        try:
            # The initial ribbon can be unavailable while pyRevit startup is running.
            sync_ribbon_to_revit_language(sender)
        except Exception:
            pass
        finally:
            try:
                if _sync_handler is not None:
                    sender.Idling -= _sync_handler
            except Exception:
                pass
            _sync_handler = None

    if _uiapp is not None:
        _sync_handler = framework.EventHandler[UI.Events.IdlingEventArgs](_sync_on_idle)
        _uiapp.Idling += _sync_handler
except Exception:
    # Localization must never interfere with core NdevTools loading.
    pass

# Optional Sheet Clipboard shortcut on the native Modify tab (Revit 2023+).
import imp

try:
    app = getattr(__revit__, 'Application', None) or getattr(__revit__, 'ControlledApplication', None)
    if app is not None and int(app.VersionNumber) >= 2023:
        folder = os.path.join(os.path.dirname(__file__), 'NdevTools.tab', 'Sheets.panel',
                              'col3.stack', 'Clipboard.pulldown')
        module = imp.load_source('ndev_main_sheet_modify_clipboard', os.path.join(folder, 'modify_ribbon.py'))
        module.install(__revit__)
except Exception as error:
    # The Sheets commands are independent of Modify-tab hosting.
    from pyrevit.coreutils.logger import get_logger
    get_logger('NdevSheetClipboard').debug('Modify shortcut startup: {}'.format(error))

# Restore saved Tab Hider choices after the ribbon is ready.
try:
    folder = os.path.join(os.path.dirname(__file__), 'NdevTools.tab', 'Modify.panel',
                          'col1.stack', 'Tab Hider.pushbutton')
    module = imp.load_source('ndev_tab_hider_startup', os.path.join(folder, 'visibility_startup.py'))
    module.install(__revit__)
except Exception as error:
    from pyrevit.coreutils.logger import get_logger
    get_logger('NdevTabHider').warning('Could not register ribbon restoration: {}'.format(error))
