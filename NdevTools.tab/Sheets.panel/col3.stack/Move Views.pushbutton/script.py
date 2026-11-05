# -*- coding: utf-8 -*-
"""Open the modeless sheet arrangement window."""
__persistentengine__ = True
import imp
import os
from pyrevit import UI


def main(uiapp):
    folder = os.path.dirname(__file__)
    module = imp.load_source('ndev_main_sheet_session', os.path.join(folder, 'sheet_session.py'))
    return module.open_window(uiapp, folder)


if __name__ == '__main__':
    try:
        main(__revit__)
    except Exception as error:
        UI.TaskDialog.Show('Move Views', unicode(error))
