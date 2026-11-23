# -*- coding: utf-8 -*-
import os
import sys
_cad_lib = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
if _cad_lib not in sys.path:
    sys.path.insert(0, _cad_lib)
__persistentengine__ = True
from pyrevit import forms, revit
import ndev_main_cad_mapping as mapping
try:
    existing=next((w for w in mapping.OPEN_WINDOWS if not w._closed and w.kind=='Walls' and w.doc==revit.doc),None)
    if existing is not None:
        from System.Windows import WindowState
        existing.WindowState=WindowState.Normal
        existing.Activate()
    else:
        import ndev_main_cad_mapping_math
        import ndev_main_cad_events
        reload(ndev_main_cad_mapping_math)
        import ndev_main_cad_wall_plan, ndev_main_cad_mapping_place, ndev_main_cad_trace_report
        import ndev_main_cad_perimeter, ndev_main_cad_openings, ndev_main_cad_corner_joins
        reload(ndev_main_cad_perimeter)
        reload(ndev_main_cad_openings)
        reload(ndev_main_cad_wall_plan)
        reload(ndev_main_cad_corner_joins)
        reload(ndev_main_cad_mapping_place)
        reload(ndev_main_cad_trace_report)
        reload(ndev_main_cad_events)
        reload(mapping)
        mapping.show('Walls')
except Exception as error:
    forms.alert(str(error),title='CAD to '+'Walls')
