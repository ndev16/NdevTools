# -*- coding: utf-8 -*-
import os
import sys
_cad_lib = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
if _cad_lib not in sys.path:
    sys.path.insert(0, _cad_lib)
__persistentengine__ = True
from pyrevit import forms
from ndev_main_cad_buttons import run
try:
    run('Grids')
except Exception as error:
    forms.alert(str(error), title='CAD to Grids')
