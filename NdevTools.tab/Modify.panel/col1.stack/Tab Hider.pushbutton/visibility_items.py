# -*- coding: utf-8 -*-
"""Editable Revit ribbon items, shared by the dialog and startup restore."""
from pyrevit.api import AdWindows


NORMAL_TABS = set(('Architecture', 'Structure', 'Steel', 'thePrecastTab', 'Systems',
                   'Insert', 'Annotate', 'Analyze', 'MassingSite',
                   'Collaborate', 'View', 'Manage', 'Add-Ins'))
FAMILY_TABS = set(('Home_Family', 'Insert_AnnotationDetailModelMassConceptualProfileTrussFamily',
                   'Annotate_ModelMassFamily', 'View_Family', 'Manage_Family'))
OWNER_TABS = ('ndevtools', 'ndevtools_r&d', 'ndevtools_r_d')


def visible(item):
    return bool(item.Visible if hasattr(item, 'Visible') else item.IsVisible)


def set_visible(item, value):
    if hasattr(item, 'Visible'):
        item.Visible = value
    else:
        item.IsVisible = value


def _key_part(value):
    return value.replace('%', '%25').replace('/', '%2F')


def ribbon_rows(uiapp):
    """Return each tab and its public add-in panels. Locked rows have no key."""
    uidoc = uiapp.ActiveUIDocument
    in_project = uidoc is not None and not uidoc.Document.IsFamilyDocument
    for tab in AdWindows.ComponentManager.Ribbon.Tabs:
        tab_id = tab.Id or ''
        title = tab.Title or tab_id or '(unnamed tab)'
        try:
            addin_panels = list(uiapp.GetRibbonPanels(title))
        except Exception:
            addin_panels = []
        contextual = (getattr(tab, 'IsContextualTab', False) or
                      getattr(tab, 'IsContextual', False) or tab_id in FAMILY_TABS or
                      (not addin_panels and tab_id not in NORMAL_TABS) or
                      (tab_id in NORMAL_TABS and not in_project))
        is_modify = title.strip().lower() == 'modify' or tab_id.lower() == 'modify'
        owner = title.strip().lower() in OWNER_TABS or tab_id.lower() in OWNER_TABS
        identity = _key_part(tab_id or title)
        key = 'tab/' + identity
        if is_modify or owner:
            note = ' (kept visible so you can reopen this tool)' if owner else ' (locked)'
            key = None
        elif contextual:
            note = ' (context controlled by Revit)'
            key = None
        else:
            note = ''
        panels = []
        if not contextual and not is_modify:
            for panel in addin_panels:
                name = panel.Name or ''
                # Name is the internal name; Title may be translated at startup.
                label = getattr(panel, 'Title', None) or name or '(unnamed panel)'
                panel_key = 'panel/' + identity + '/' + _key_part(name)
                if not name or name.strip().lower() == 'modify':
                    panel_key = None
                    label += ' (locked)'
                panels.append((panel, label, panel_key))
        yield tab, title, note, key, panels


def restore_visibility(uiapp, choices):
    handled = set()
    if not choices:
        return handled
    for tab, title, note, key, panels in ribbon_rows(uiapp):
        for item, label, item_key in [(tab, title, key)] + panels:
            if item_key not in choices or item_key is None:
                continue
            desired = choices[item_key]
            try:
                if visible(item) != desired:
                    set_visible(item, desired)
                if visible(item) == desired:
                    handled.add(item_key)
            except Exception:
                # Some add-ins build their panels later in startup.
                continue
    return handled
