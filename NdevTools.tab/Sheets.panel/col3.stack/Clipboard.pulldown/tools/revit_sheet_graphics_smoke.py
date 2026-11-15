# -*- coding: utf-8 -*-
"""Copy sheet-owned graphics and title blocks in disposable Revit projects."""
import imp
import os
import shutil
import tempfile
import traceback

from pyrevit import DB
from pyrevit.coreutils import yaml

fixture = imp.load_source('ndev_main_sheet_graphics_fixture',
                          os.path.join(os.path.dirname(__file__), 'revit_cross_project_smoke.py'))
command, clip, moves, preview = fixture.command, fixture.clip, fixture.moves, fixture.preview


def prepare(doc, titleblock_path=None):
    tx = DB.Transaction(doc, 'Prepare test sheets')
    tx.Start()
    try:
        first = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
        second = DB.ViewSheet.Create(doc, DB.ElementId.InvalidElementId)
        first.SheetNumber = 'SRC-001' if titleblock_path else 'DEST-101'
        second.SheetNumber = 'QA-002'
        items = []
        if titleblock_path:
            assert doc.LoadFamily(titleblock_path)
            family = os.path.splitext(os.path.basename(titleblock_path))[0]
            types = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_TitleBlocks).WhereElementIsElementType()
            symbol = next(t for t in types if t.FamilyName == family)
            symbol.Activate()
            block = doc.Create.NewFamilyInstance(DB.XYZ.Zero, symbol, first)
            line = doc.Create.NewDetailCurve(first, DB.Line.CreateBound(DB.XYZ.Zero, DB.XYZ(1, 0, 0)))
            arc = doc.Create.NewDetailCurve(first, DB.Arc.Create(DB.XYZ(0, 1, 0), DB.XYZ(1, 1, 0), DB.XYZ(.5, 1.5, 0)))
            categories = doc.Settings.Categories
            style = categories.NewSubcategory(categories.get_Item(DB.BuiltInCategory.OST_Lines), 'QA sheet line')
            line.LineStyle = style.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
            block.Pinned = True
            line.Pinned = True
            bundle = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            images = []
            for name, source in (('assets/ndevtools-logo.png', DB.ImageTypeSource.Import),
                                 ('icon.png', DB.ImageTypeSource.Link)):
                path = os.path.abspath(os.path.join(bundle, name))
                with DB.ImageTypeOptions(path, False, source) as options:
                    image_type = DB.ImageType.Create(doc, options)
                center = DB.XYZ(1, 2 + len(images), 0)
                with DB.ImagePlacementOptions(center, DB.BoxPlacement.Center) as location:
                    image = DB.ImageInstance.Create(doc, first, image_type.Id, location)
                image.LockProportions = False
                image.Width, image.Height = .7, .45
                axis = DB.Line.CreateBound(center, center + DB.XYZ.BasisZ)
                DB.ElementTransformUtils.RotateElement(doc, image.Id, axis, .31)
                image.Pinned = not images
                images.append(image)
            items = [block, line, arc] + images
        assert tx.Commit() == DB.TransactionStatus.Committed
        return first, second, items
    finally:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        tx.Dispose()


def run(app):
    print('Testing Revit {} ({}).'.format(app.VersionNumber, app.VersionBuild))
    bundle = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for command_path in ('', 'Copy.pushbutton', 'Paste.pushbutton'):
        manifest = yaml.load_as_dict(os.path.join(bundle, command_path, 'bundle.yaml'))
        assert set(manifest['title']) == set(manifest['tooltip'])
        assert all(word in manifest['tooltip']['en_us'] for word in ('sheet lines', 'arcs', 'raster images', 'title blocks'))
        if not command_path:
            assert manifest['layout'] == ['Cut', 'Copy', 'Paste']
    print('PASS ribbon YAML for Sheet Clipboard, Copy and Paste')
    source = app.NewProjectDocument(DB.UnitSystem.Imperial)
    other = None
    try:
        other = app.NewProjectDocument(DB.UnitSystem.Imperial)
        library = os.path.join(os.environ['ProgramData'], 'Autodesk', 'RVT ' + app.VersionNumber,
                               'Libraries', 'English-Imperial')
        family = os.path.join(library, 'US', 'Structural Precast', 'Title Blocks', 'Solid Wall - B 11 x 17 Horizontal.rfa')
        if not os.path.isfile(family):
            family = os.path.join(library, 'Titleblocks', 'B 11 x 17 Horizontal.rfa')
        assert os.path.isfile(family), family
        first, second, items = prepare(source, family)
        external, _, _ = prepare(other)
        # A different raster in the destination can have the same filename.
        with_name = os.path.join(tempfile.mkdtemp(prefix='sheet-raster-'), 'ndevtools-logo.png')
        try:
            shutil.copyfile(os.path.join(bundle, 'icon.png'), with_name)
            with DB.Transaction(other, 'Prepare conflicting image type') as tx:
                tx.Start()
                with DB.ImageTypeOptions(with_name, False, DB.ImageTypeSource.Import) as options:
                    collision = DB.ImageType.Create(other, options)
                assert tx.Commit() == DB.TransactionStatus.Committed
        finally:
            if os.path.isfile(with_name):
                os.remove(with_name)
            os.rmdir(os.path.dirname(with_name))
        uids = set(item.UniqueId for item in items)
        available = clip.sheet_items(source, first, moves, preview, copying=True)
        assert uids == set(row['uid'] for row in available), available
        assert not clip.sheet_items(source, first, moves, preview, copying=False)
        context = fixture.Context(source, first)
        context.ids = [item.Id for item in items]
        held = command.main(context, 'copy')
        origin = DB.XYZ(held['center'][0], held['center'][1], 0)
        skipped = []
        command.report_skips = lambda placed, reasons, data, owner=None: skipped.extend(reasons)
        originals = dict((item.UniqueId, moves.item_anchor(item)) for item in items)
        external_types = {}
        for sheet in (first, second, external, external):
            ctx = fixture.Context(sheet.Document, sheet)
            ctx.point = origin + DB.XYZ(3, 2, 0)
            number, name = sheet.SheetNumber, sheet.Name
            result = command.main(ctx, 'paste')
            assert set(result) == uids and not skipped, (result, skipped)
            assert sheet.SheetNumber == number and sheet.Name == name
            for old in items:
                new = sheet.Document.GetElement(result[old.UniqueId])
                assert new.OwnerViewId == sheet.Id and new.UniqueId != old.UniqueId
                assert new.Pinned == old.Pinned
                offset = ctx.point - origin
                assert moves.item_anchor(old).DistanceTo(originals[old.UniqueId]) < 1e-6
                assert moves.item_anchor(new).DistanceTo(originals[old.UniqueId] + offset) < 1e-6
                if moves.is_title_block(old):
                    assert moves.is_title_block(new) and old.Symbol.FamilyName == new.Symbol.FamilyName
                    type_name = DB.BuiltInParameter.SYMBOL_NAME_PARAM
                    assert new.Symbol.get_Parameter(type_name).AsString() == old.Symbol.get_Parameter(type_name).AsString()
                    assert new.get_Parameter(DB.BuiltInParameter.SHEET_NUMBER).AsString() == number
                elif isinstance(old, DB.ImageInstance):
                    assert isinstance(new, DB.ImageInstance)
                    original_type = old.Document.GetElement(old.GetTypeId())
                    new_type = new.Document.GetElement(new.GetTypeId())
                    if old.Pinned and sheet.Document.Equals(other):
                        assert new_type.Id != collision.Id, 'Pasted the destination image with the same filename.'
                        assert collision.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == 'ndevtools-logo.png'
                    if sheet.Document.Equals(other):
                        assert external_types.setdefault(old.UniqueId, new_type.UniqueId) == new_type.UniqueId
                    assert original_type.Source == new_type.Source
                    if original_type.Source == DB.ImageTypeSource.Link:
                        assert os.path.normcase(original_type.Path) == os.path.normcase(new_type.Path)
                    assert (original_type.WidthInPixels, original_type.HeightInPixels) == (new_type.WidthInPixels, new_type.HeightInPixels)
                    with original_type.GetImage() as before, new_type.GetImage() as after:
                        for ix in range(0, before.Width, max(1, before.Width // 8)):
                            for iy in range(0, before.Height, max(1, before.Height // 8)):
                                assert before.GetPixel(ix, iy).ToArgb() == after.GetPixel(ix, iy).ToArgb()
                    assert abs(new.Width - old.Width) < 1e-6 and abs(new.Height - old.Height) < 1e-6
                    assert new.LockProportions == old.LockProportions and new.DrawLayer == old.DrawLayer
                    for corner in (DB.BoxPlacement.TopLeft, DB.BoxPlacement.BottomRight):
                        assert new.GetLocation(corner).DistanceTo(old.GetLocation(corner) + offset) < 1e-6
                else:
                    assert new.LineStyle.Name == old.LineStyle.Name
                    for t in (0., .5, 1.):
                        expected = old.GeometryCurve.Evaluate(t, True) + offset
                        assert new.GeometryCurve.Evaluate(t, True).DistanceTo(expected) < 1e-6
        print('PASS sheet line, arc and pinned title block copied on the same sheet, between sheets and across projects')
        print('PASS imported and linked raster images, dimensions, rotation, placement, pin state and link source')
    finally:
        if other is not None:
            other.Close(False)
        source.Close(False)


if __name__ == '__main__':
    try:
        run(__revit__.Application)
    except Exception:
        print(traceback.format_exc())
        raise
