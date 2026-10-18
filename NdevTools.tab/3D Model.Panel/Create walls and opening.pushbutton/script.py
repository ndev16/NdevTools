# -*- coding: utf-8 -*-
"""NdevTools Wall Tracing - pyRevit command entry point."""
import os
import sys
from pyrevit import revit, DB, forms, script
ROOT = os.path.dirname(__file__)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from wall_tracing_ui import WallTracingWindow
from wall_tracing_engine import execute, validate, report, repair_selected_joins


def main():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert('Open a Revit project first.', title='Wall Tracing')
        return
    selected_walls = [doc.GetElement(i) for i in revit.uidoc.Selection.GetElementIds()
                      if isinstance(doc.GetElement(i), DB.Wall)]
    if selected_walls:
        action = forms.CommandSwitchWindow.show(
            ['Allow joins on selected walls', 'Trace new walls'],
            message='{} host wall(s) selected. Choose an action.'.format(len(selected_walls)))
        if action is None:
            return
        if action == 'Allow joins on selected walls':
            try:
                repaired, failures = repair_selected_joins(doc, selected_walls)
                forms.alert('Joins allowed at both ends of {} wall(s).\n{}'.format(
                    repaired, '\n'.join(failures)), title='Wall Tracing')
            except Exception as error:
                forms.alert('Join repair was rolled back:\n{}'.format(error), title='Wall Tracing')
            return
    view = revit.active_view
    if view.IsTemplate or not isinstance(view, (DB.ViewPlan, DB.View3D)):
        forms.alert('Start Wall Tracing from a plan or 3D view.', title='Wall Tracing')
        return
    window = WallTracingWindow(doc, revit.uidoc, ROOT)
    window.ShowDialog()
    if window.result is None:
        return
    link, configurations = window.result
    try:
        validate(doc, link, configurations)
        with forms.ProgressBar(title='Wall Tracing ({value}/{max_value})', cancellable=True) as progress:
            result = execute(doc, link, configurations, progress)
        report(result, script.get_output())
    except Exception as error:
        forms.alert('Wall Tracing stopped. The creation group was rolled back if it had started.\n\n{}'.format(error), title='Wall Tracing')


if __name__ == '__main__':
    main()
