# -*- coding: utf-8 -*-
"""Run in an empty Revit UI session and let it reach Idling after Paste."""
import imp
import os
import tempfile
import traceback

from pyrevit import DB, UI

smoke = imp.load_source('ndev_main_paste_fixture', os.path.join(os.path.dirname(__file__), 'revit_cross_project_smoke.py'))


def start(uiapp):
    if uiapp.ActiveUIDocument is not None or uiapp.Application.Documents.Size:
        raise ValueError('This test needs its own empty Revit session.')
    folder = tempfile.mkdtemp(prefix='ndev-paste-tabs-')
    path = os.path.join(folder, 'Clipboard tabs.rvt')
    report = os.environ.get('NDEV_PASTE_TAB_REPORT') or os.path.join(folder, 'result.txt')

    def record(message):
        with open(report, 'a') as stream:
            stream.write(message + '\n')

    source = uiapp.Application.NewProjectDocument(DB.UnitSystem.Imperial)
    try:
        source_sheet, originals = smoke.sample(source, True)
        source_context = smoke.Context(source, source_sheet)
        source_context.ids = [item.Id for item in originals]
        smoke.command.main(source_context, 'copy')
        destination = uiapp.Application.NewProjectDocument(DB.UnitSystem.Imperial)
        sheet, _ = smoke.sample(destination, False)
        sheet_uid = sheet.UniqueId
        destination.SaveAs(path)
        destination.Close(False)
        uidoc = uiapp.OpenAndActivateDocument(path)
        doc = uidoc.Document
        sheet = doc.GetElement(sheet_uid)
        existing = next(iter(DB.FilteredElementCollector(doc).OfClass(DB.ViewDrafting)))
        uidoc.ActiveView = existing
        uidoc.ActiveView = sheet
        before = set(tab.ViewId for tab in uidoc.GetOpenUIViews())
        assert existing.Id in before

        # Supply the point a person would click; all view and tab operations are native.
        clip, moves, preview = smoke.command.load_modules()
        paste = clip.paste
        def paste_at(doc, target, token, moves, preview, pick, choose, skipped):
            return paste(doc, target, token, moves, preview, lambda: DB.XYZ(1, 1, 0), choose, skipped)

        clip.paste = paste_at
        smoke.command.load_modules = lambda: (clip, moves, preview)
        result = smoke.command.paste_on_sheet(uiapp)
        assert len(result) == len(originals)
        placed = list(sheet.GetAllViewports())
        assert len(placed) == 3
        # Exercise the case where Revit opens multiple details before returning to idle.
        for viewport_id in placed:
            uidoc.ActiveView = doc.GetElement(doc.GetElement(viewport_id).ViewId)
        assert len(uidoc.GetOpenUIViews()) == len(before) + len(placed)
        record('Paste created three viewports. All three detail tabs are open before idle.')

        first_idle = [True]
        def check(sender, args):
            if first_idle[0]:
                first_idle[0] = False
                args.SetRaiseWithoutDelay()
                return
            uiapp.Idling -= check
            try:
                active = uiapp.ActiveUIDocument
                open_tabs = set(tab.ViewId for tab in active.GetOpenUIViews())
                record('Active: {}. Open: {}. Expected: {}.'.format(active.ActiveView.Name,
                       sorted(str(i) for i in open_tabs), sorted(str(i) for i in before)))
                assert active.ActiveView.Id == sheet.Id, 'The destination sheet lost focus.'
                assert open_tabs == before, 'The open tabs differ.'
                assert set(sheet.GetAllViewports()) == set(placed), 'A pasted viewport disappeared.'
                record('PASS destination sheet active, original tabs preserved, copied tabs closed, three viewports still placed.')
            except Exception:
                record(traceback.format_exc())
            finally:
                doc.Save()
                if uiapp.Application.Documents.Size == 1:
                    uiapp.PostCommand(UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.ExitRevit))
        uiapp.Idling += check
    except Exception:
        record(traceback.format_exc())
        raise
    finally:
        source.Close(False)


if __name__ == '__main__':
    # The runner clears its entry-script globals when it returns to Revit.
    module = imp.load_source('ndev_main_paste_tab_test', __file__)
    module.start(__revit__)
