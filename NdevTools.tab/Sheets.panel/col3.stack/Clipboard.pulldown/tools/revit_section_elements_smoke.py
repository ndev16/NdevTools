# -*- coding: utf-8 -*-
"""Exercise section detail selection and paste in two unsaved projects."""
import imp
import os
import traceback

from pyrevit import DB
from System.Collections.Generic import List

fixture = imp.load_source('section_clip_fixture', os.path.join(os.path.dirname(__file__), 'revit_cross_project_smoke.py'))
command = fixture.command
bundle = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def add_image(doc, view, filename, source, point):
    with DB.ImageTypeOptions(os.path.join(bundle, filename), False, source) as options:
        image_type = DB.ImageType.Create(doc, options)
    with DB.ImagePlacementOptions(point, DB.BoxPlacement.Center) as placement:
        return DB.ImageInstance.Create(doc, view, image_type.Id, placement)


def check_images(source_images, items, target, center, point, expected_types):
    images = [e for e in items if isinstance(e, DB.ImageInstance)]
    assert len(images) == len(source_images), ('image count', len(images), len(source_images))
    for old in source_images:
        original = old.Document.GetElement(old.GetTypeId())
        new = next(e for e in images if target.Document.GetElement(e.GetTypeId()).Source == original.Source)
        new_type = target.Document.GetElement(new.GetTypeId())
        assert expected_types.setdefault(original.UniqueId, new_type.UniqueId) == new_type.UniqueId
        assert new.OwnerViewId == target.Id and new.Pinned == old.Pinned
        assert abs(new.Width - old.Width) < 1e-6 and abs(new.Height - old.Height) < 1e-6, (new.Width, old.Width, new.Height, old.Height)
        assert new.LockProportions == old.LockProportions and new.DrawLayer == old.DrawLayer
        if original.Source == DB.ImageTypeSource.Link:
            assert os.path.normcase(new_type.Path) == os.path.normcase(original.Path)
        with original.GetImage() as before, new_type.GetImage() as after:
            assert (before.Width, before.Height) == (after.Width, after.Height)
            for ix in range(0, before.Width, max(1, before.Width // 8)):
                for iy in range(0, before.Height, max(1, before.Height // 8)):
                    assert before.GetPixel(ix, iy).ToArgb() == after.GetPixel(ix, iy).ToArgb()
        source = old.Document.GetElement(old.OwnerViewId)
        align = DB.ElementTransformUtils.GetTransformFromViewToView(source, target)
        delta = point - align.OfPoint(center)
        for corner in (DB.BoxPlacement.Center, DB.BoxPlacement.TopLeft, DB.BoxPlacement.BottomRight):
            error = new.GetLocation(corner) - (align.OfPoint(old.GetLocation(corner)) + delta)
            assert abs(error.DotProduct(target.RightDirection)) < 1e-6 and abs(error.DotProduct(target.UpDirection)) < 1e-6, (str(corner), str(error))


def section(doc, rotated=False):
    family = next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                  if t.ViewFamily == DB.ViewFamily.Section)
    box = DB.BoundingBoxXYZ()
    box.Min, box.Max = DB.XYZ(-40, -40, 0), DB.XYZ(40, 40, 20)
    frame = DB.Transform.Identity
    frame.Origin = DB.XYZ(10, 6, 4) if rotated else DB.XYZ(2, 3, 1)
    frame.BasisX = DB.XYZ.BasisY if rotated else DB.XYZ.BasisX
    frame.BasisY = DB.XYZ.BasisZ
    frame.BasisZ = frame.BasisX.CrossProduct(frame.BasisY)
    box.Transform = frame
    return DB.ViewSection.CreateSection(doc, family.Id, box)


def make_source(doc):
    with DB.Transaction(doc, 'Prepare source section') as tx:
        tx.Start()
        view = section(doc)
        doc.Regenerate()
        o, x, y = view.Origin, view.RightDirection, view.UpDirection
        line = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(o, o + 4*x))
        note = DB.TextNote.Create(doc, view.Id, o + 2*y, 'SECTION NOTE', doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType))
        loop = DB.CurveLoop()
        pts = [o+x, o+3*x, o+3*x+y, o+x+y]
        for i, p in enumerate(pts):
            loop.Append(DB.Line.CreateBound(p, pts[(i+1) % 4]))
        loops = List[DB.CurveLoop]()
        loops.Add(loop)
        rtype = next(iter(DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType)))
        region = DB.FilledRegion.Create(doc, rtype.Id, view.Id, loops)
        libraries = os.path.join(os.environ['ProgramData'], 'Autodesk')
        family = os.path.join('Detail Items', 'Div 10-Specialties', '102600-Wall and Door Protection', 'Corner Guard-Squared.rfa')
        candidates = [os.path.join(libraries, 'RVT ' + year, 'Libraries', 'English-Imperial', family)
                      for year in (doc.Application.VersionNumber, '2023')]
        path = next(path for path in candidates if os.path.isfile(path))
        assert doc.LoadFamily(path)
        symbol = next(s for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol) if s.FamilyName == 'Corner Guard-Squared')
        symbol.Activate()
        component = doc.Create.NewFamilyInstance(o+5*x+y, symbol, view)
        images = []
        for filename, kind in (('assets/ndevtools-logo.png', DB.ImageTypeSource.Import), ('icon.png', DB.ImageTypeSource.Link)):
            center = o + (4 + len(images))*x + 2*y
            image = add_image(doc, view, filename, kind, center)
            image.LockProportions = False
            image.Width, image.Height = 2.25, .85
            axis = DB.Line.CreateBound(center, center + view.ViewDirection)
            DB.ElementTransformUtils.RotateElement(doc, image.Id, axis, .27)
            image.Pinned = not images
            images.append(image)
        level = next(iter(DB.FilteredElementCollector(doc).OfClass(DB.Level)))
        wall = DB.Wall.Create(doc, DB.Line.CreateBound(DB.XYZ.Zero, DB.XYZ(4,0,0)), level.Id, False)
        assert tx.Commit() == DB.TransactionStatus.Committed
    return view, [line, note, region, component] + images, wall


def run(app):
    src = app.NewProjectDocument(DB.UnitSystem.Imperial)
    dst = None
    seen = []
    command.report_skips = lambda placed, skipped, data, owner=None: seen.extend(skipped)
    try:
        dst = app.NewProjectDocument(DB.UnitSystem.Imperial)
        source, details, wall = make_source(src)
        with DB.Transaction(dst, 'Set up destination section') as tx:
            tx.Start()
            target = section(dst, True)
            doc_origin = target.Origin
            existing = add_image(dst, target, 'icon.png', DB.ImageTypeSource.Import, doc_origin)
            conflict = dst.GetElement(existing.GetTypeId())
            conflict.Name = 'ndevtools-logo.png'
            assert tx.Commit() == DB.TransactionStatus.Committed
        plane_before = target.SketchPlane
        original = details[0].GeometryCurve
        a, b = fixture.Context(src, source), fixture.Context(dst, target)
        a.ids = [e.Id for e in details] + [wall.Id]
        entry = command.main(a, 'copy')
        assert len(entry['rows']) == len(details) + 1
        image_types = {}
        images = [e for e in details if isinstance(e, DB.ImageInstance)]
        center = DB.XYZ(*entry['center'])
        alignment = DB.ElementTransformUtils.GetTransformFromViewToView(source, target)
        normal = target.ViewDirection
        view_count = len(fixture.elements(dst, DB.View))
        for i in (1, 2):
            b.point = target.Origin + i * 4 * target.RightDirection + target.UpDirection
            delta = b.point - alignment.OfPoint(center)
            shift = delta - normal * normal.DotProduct(delta)
            placed = command.paste_on_sheet(b)
            assert len(placed) == len(details), (len(placed), seen)
            assert seen[-1][0] == wall.UniqueId and len(seen) == i, seen
            items = [dst.GetElement(uid) for uid in placed]
            assert all(e.OwnerViewId == target.Id for e in items)
            assert set(b.ids) == set(e.Id for e in items)
            check_images(images, items, target, center, b.point, image_types)
            note = next(e for e in items if isinstance(e, DB.TextNote))
            assert note.Text == details[1].Text
            assert any(isinstance(e, DB.FilledRegion) for e in items)
            component = next(e for e in items if isinstance(e, DB.FamilyInstance))
            assert component.Symbol.FamilyName == 'Corner Guard-Squared'
            for new, old in ((note.Coord, details[1].Coord), (component.Location.Point, details[3].Location.Point)):
                expected = alignment.OfPoint(old) + shift
                assert new.DistanceTo(expected) < 1e-6, (str(new), str(expected))
            curve = next(e.GeometryCurve for e in items if isinstance(e, DB.DetailCurve))
            for j in (0,1):
                assert curve.GetEndPoint(j).DistanceTo(alignment.OfPoint(original.GetEndPoint(j)) + shift) < 1e-6
        b.point = None
        assert command.paste_on_sheet(b) is None
        assert len(fixture.elements(dst, DB.View)) == view_count
        assert not fixture.elements(dst, DB.Wall)
        assert all(e.IsValidObject for e in details)
        assert (target.SketchPlane.Id if target.SketchPlane else None) == (plane_before.Id if plane_before else None)
        # Starting Copy before selecting must use the native selection prompt.
        a.ids = []
        a.PickObjects = lambda mode, prompt: [DB.Reference(e) for e in [details[0]] + images]
        entry = command.main(a, 'copy')
        assert len(entry['rows']) == 3
        with DB.Transaction(dst, 'Prepare drafting view') as tx:
            tx.Start()
            drafting = next(t for t in DB.FilteredElementCollector(dst).OfClass(DB.ViewFamilyType)
                            if t.ViewFamily == DB.ViewFamily.Drafting)
            draft = DB.ViewDrafting.Create(dst, drafting.Id)
            draft.Scale = 24
            assert tx.Commit() == DB.TransactionStatus.Committed
        draft_context = fixture.Context(dst, draft)
        placed = command.paste_on_sheet(draft_context)
        assert len(placed) == 3, (placed, seen)
        check_images(images, [dst.GetElement(uid) for uid in placed], draft, DB.XYZ(*entry['center']), draft_context.point, image_types)
        a.ids = [images[0].Id]
        command.main(a, 'copy')
        placed = command.paste_on_sheet(draft_context)
        assert len(placed) == 1
        actual = dst.GetElement(placed[0]).GetLocation(DB.BoxPlacement.Center)
        assert abs(actual.X - draft_context.point.X) < 1e-6 and abs(actual.Y - draft_context.point.Y) < 1e-6
        assert existing.GetTypeId() == conflict.Id and conflict.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == 'ndevtools-logo.png'
        assert conflict.UniqueId not in image_types.values()
        print('PASS section raster images to perpendicular section and drafting view; mixed and image-only placement, appearance, links, pins and name collisions')
        print('PASS Revit {} section elements, perpendicular destination, selected contents, repeat and cancel'.format(app.VersionNumber))
    finally:
        if dst is not None:
            dst.Close(False)
        src.Close(False)


if __name__ == '__main__':
    try:
        run(__revit__.Application)
    except Exception:
        print(traceback.format_exc())
        raise
