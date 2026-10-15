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
