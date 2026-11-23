# -*- coding: utf-8 -*-
"""Exercise the actual Copy/Paste entry points using two unsaved Revit projects."""
import imp
import os
import traceback
from System import IntPtr
from System.Collections.Generic import List
from pyrevit import DB


bundle = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
command = imp.load_source('ndev_main_project_copy_smoke', os.path.join(bundle, 'script.py'))
clip, moves, preview = command.load_modules()


class Context(object):
    MainWindowHandle = IntPtr.Zero

    def __init__(self, doc, sheet):
        self.ActiveUIDocument = self.Selection = self
        self.Document, self.ActiveView = doc, sheet
        self.ids = []
        self.point = DB.XYZ(2, 1, 0)

    def GetElementIds(self):
        return self.ids

    def SetElementIds(self, ids):
        self.ids = list(ids)

    def PickPoint(self, prompt):
        return self.point


def elements(doc, cls):
    return list(DB.FilteredElementCollector(doc).OfClass(cls).WhereElementIsNotElementType())


def sample(doc, details):
    tx = DB.Transaction(doc, 'Test detail sheet')
    tx.Start()
    try:
        sheet = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
        drafting_type = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                             if t.ViewFamily == DB.ViewFamily.Drafting)
        draft = DB.ViewDrafting.Create(doc, drafting_type.Id)
        draft.Name = 'Typical edge detail'
        if not details:
            tx.Commit()
            return sheet, []
        section_type = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                            if t.ViewFamily == DB.ViewFamily.Section)
        box = DB.BoundingBoxXYZ()
        box.Min, box.Max = DB.XYZ(-6,-4,0), DB.XYZ(6,4,8)
        t = DB.Transform.Identity
        t.BasisY, t.BasisZ = DB.XYZ.BasisZ, -DB.XYZ.BasisY
        box.Transform = t
        section = DB.ViewSection.CreateSection(doc, section_type.Id, box)
        detail_type = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                           if t.ViewFamily == DB.ViewFamily.Detail)
        detail = DB.ViewSection.CreateDetail(doc, detail_type.Id, box)
        level = next(iter(DB.FilteredElementCollector(doc).OfClass(DB.Level)))
        DB.Wall.Create(doc, DB.Line.CreateBound(DB.XYZ(-3, -2, 0), DB.XYZ(3, -2, 0)), level.Id, False)
        owned = []
        note_type = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
        for idx,view in enumerate((draft, section, detail)):
            view.Scale = 24
            doc.Create.NewDetailCurve(view, DB.Line.CreateBound(view.Origin, view.Origin + 3*view.RightDirection))
            DB.TextNote.Create(doc, view.Id, view.Origin, 'Keep this detail text', note_type)
            if view == draft:
                loop = DB.CurveLoop()
                corners = [DB.XYZ(0,0,0), DB.XYZ(2,0,0), DB.XYZ(2,2,0), DB.XYZ(0,2,0)]
                for i,p in enumerate(corners): loop.Append(DB.Line.CreateBound(p, corners[(i+1)%4]))
                loops=List[DB.CurveLoop](); loops.Add(loop)
                region=next(iter(DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType)))
                DB.FilledRegion.Create(doc,region.Id,view.Id,loops)
                # The CMU reproduction lost entire detail groups because their
                # category is Internal. Include a group with a source-only type.
                group_region_type = region.Duplicate('Clipboard grouped region')
                group_region = DB.FilledRegion.Create(doc,group_region_type.Id,view.Id,loops)
                group_line = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(DB.XYZ(4,0,0), DB.XYZ(4,2,0)))
                group_note = DB.TextNote.Create(doc,view.Id,DB.XYZ(4,3,0),'Keep the grouped detail',note_type)
                group_ids = List[DB.ElementId]()
                for element in (group_region, group_line, group_note): group_ids.Add(element.Id)
                doc.Create.NewGroup(group_ids)
            owned.append(DB.Viewport.Create(doc, sheet.Id, view.Id, DB.XYZ(.5+idx,.4,0)))
        owned.append(DB.TextNote.Create(doc,sheet.Id,DB.XYZ(.2,.8,0),'Sheet note',note_type))
        tx.Commit()
        return sheet, owned
    finally:
        if tx.GetStatus() == DB.TransactionStatus.Started:tx.RollBack()
        tx.Dispose()


def run(app):
    source = app.NewProjectDocument(DB.UnitSystem.Imperial)
    dest = None
    reports = []
    command.report_skips = lambda placed, skipped, data, owner=None: reports.extend(skipped)
    try:
        dest = app.NewProjectDocument(DB.UnitSystem.Imperial)
        a, originals = sample(source, True)
        b, _ = sample(dest, False)
        existing_regions = dict((DB.Element.Name.GetValue(t),t.Id)
                                for t in DB.FilteredElementCollector(dest).OfClass(DB.FilledRegionType))
        from_sheet, to_sheet = Context(source,a), Context(dest,b)
        source_uids = set(e.UniqueId for e in originals)
        from_sheet.ids = [e.Id for e in originals]
        token = command.main(from_sheet,'copy')['token']
        assert clip.for_paste(dest)['token'] == token
        results = []
        for pos in (DB.XYZ(.9,1.1,0), DB.XYZ(2.1,.3,0)):
            to_sheet.point = pos
            pasted = command.main(to_sheet,'paste')
            assert set(pasted) == source_uids, (pasted,reports)
            assert not reports,reports
            results.extend(pasted.values())
            for old in originals:
                new = dest.GetElement(pasted[old.UniqueId])
                assert moves._sheet_id(new) == b.Id
                if isinstance(old,DB.Viewport):
                    v = dest.GetElement(new.ViewId)
                    assert v.ViewType == source.GetElement(old.ViewId).ViewType and v.Scale==24
                    contents = list(DB.FilteredElementCollector(dest).OwnedByView(v.Id))
                    notes = [n.Text for n in contents if isinstance(n,DB.TextNote)]
                    original_view = source.GetElement(old.ViewId)
                    expected_notes = [n.Text for n in DB.FilteredElementCollector(source).OwnedByView(original_view.Id)
                                      if isinstance(n, DB.TextNote)]
                    assert expected_notes and sorted(notes) == sorted(expected_notes), (str(v.ViewType),repr(notes),repr(expected_notes))
                    assert any(isinstance(n,DB.DetailCurve) for n in contents)
                    if v.ViewType == DB.ViewType.DraftingView:
                        groups = [n for n in contents if isinstance(n,DB.Group)]
                        regions = [n for n in contents if isinstance(n,DB.FilledRegion)]
                        assert len(groups) == 1 and len(regions) == 2, (len(groups),len(regions))
                        original_group = next(n for n in DB.FilteredElementCollector(source).OwnedByView(original_view.Id)
                                              if isinstance(n,DB.Group))
                        # Revit adds the filled region's sketch dependencies to
                        # the group as well as the three selected elements.
                        expected_members = sorted(source.GetElement(eid).GetType().FullName
                                                  for eid in original_group.GetMemberIds())
                        copied_members = sorted(dest.GetElement(eid).GetType().FullName
                                                for eid in groups[0].GetMemberIds())
                        assert copied_members == expected_members, (copied_members,expected_members)
                        for region in regions:
                            name = DB.Element.Name.GetValue(dest.GetElement(region.GetTypeId()))
                            if name in existing_regions:
                                assert region.GetTypeId() == existing_regions[name]
                            else:
                                assert name == 'Clipboard grouped region', name
                else:
                    assert new.Text == old.Text
        assert len(set(results)) == 8 and len(b.GetAllViewports()) == 6
        assert len(a.GetAllViewports()) == 3 and all(source.GetElement(uid) for uid in source_uids)
        assert len(elements(source, DB.Wall)) == 1 and not elements(dest, DB.Wall)
        command.main(from_sheet,'cut')
        assert clip.for_paste(dest) is None
        command.main(from_sheet,'copy')
        source.Close(False);source=None
        try:clip.for_paste(dest)
        except ValueError as error:assert 'closed' in str(error)
        else:raise AssertionError('Clipboard reused a closed source.')
    finally:
        if dest is not None: dest.Close(False)
        if source is not None: source.Close(False)


if __name__ == '__main__':
    try:
        run(__revit__.Application)
        print('PASS cross-project drafting, section and detail views, filled region, sheet note, repeated paste, model isolation, source closure and Cut isolation')
    except:
        print('FAIL cross-project clipboard\n' + traceback.format_exc())
        raise
