# -*- coding: utf-8 -*-
import imp
import os
from pyrevit import UI


if __name__ == '__main__':
    group = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        command = imp.load_source('ndev_main_sheet_clipboard_command', os.path.join(group, 'script.py'))
        command.main(__revit__, 'paste')
    except Exception as error:
        UI.TaskDialog.Show('Sheet Clipboard', unicode(error))
