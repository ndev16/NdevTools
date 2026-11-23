# -*- coding: utf-8 -*-
"""Copy sheet details between two open projects in the same Revit session."""
from collections import Counter
import os

from pyrevit import DB
from System import Guid
from System.Collections.Generic import List


DETAIL_VIEWS = (DB.ViewType.DraftingView, DB.ViewType.Section, DB.ViewType.Detail)


class DestinationTypes(DB.IDuplicateTypeNamesHandler):
    def OnDuplicateTypeNamesFound(self, args):
        return DB.DuplicateTypeAction.UseDestinationTypes


def unsupported(doc, item):
    if isinstance(item, DB.Viewport):
        view = doc.GetElement(item.ViewId)
        if view.ViewType == DB.ViewType.EngineeringPlan:
            return ('This structural plan can be copied to another sheet in the same project. '
                    'Across projects, choose a drafting view, section, or detail view.')
        if view.ViewType not in DETAIL_VIEWS:
            return u'Cross-project Copy supports drafting views, sections and detail views. This is a {}.'.format(view.ViewType)
    elif isinstance(item, DB.ScheduleSheetInstance):
        return 'Schedules cannot be pasted across projects with Sheet Clipboard.'
    return None


def _ids(elements):
    result = List[DB.ElementId]()
    for element in elements:
        result.Add(element.Id)
    return result


def _content(view, check_references=False):
    # Revit regenerates internal work planes, sun settings and crop extents.
    # Sketches, sketch lines and group members travel with their owner.
    collector = DB.FilteredElementCollector(view.Document).OwnedByView(view.Id).WhereElementIsNotElementType()
    try:
        owned = list(collector)
    finally:
        collector.Dispose()
    sketch_members = set()
    for element in owned:
        if isinstance(element, DB.Sketch):
            sketch_members.update(element.GetAllElements())
    content = []
    for element in owned:
        if check_references and isinstance(element, DB.Dimension) and element.References is not None:
            for reference in element.References:
                host = view.Document.GetElement(reference.ElementId)
                if host is not None and not host.ViewSpecific and host.Id != view.Id:
                    raise ValueError('A dimension references source model geometry. Recreate that reference in the destination.')
        if check_references and isinstance(element, DB.IndependentTag):
            for reference in element.GetTaggedElementIds():
                host = view.Document.GetElement(reference.HostElementId)
                if reference.LinkInstanceId != DB.ElementId.InvalidElementId or (host is not None and not host.ViewSpecific):
                    raise ValueError('A tag references a source model element. Recreate that reference in the destination.')
        if (not element.ViewSpecific or element.Category is None or element.Id in sketch_members
                or element.GroupId != DB.ElementId.InvalidElementId
                or isinstance(element, (DB.Sketch, DB.SketchPlane, DB.SunAndShadowSettings))
                or (element.Category.CategoryType == DB.CategoryType.Internal
                    and not isinstance(element, DB.Group))):
            continue
        if element.GetType().Name == 'Element':
            # Revit represents its built-in work-plane grid, sun path and crop
            # controls as plain Element objects and recreates them with the view.
            continue
        content.append(element)
    return content


def _signature(elements):
    # Detail Groups are an Internal category, but are copyable view content.
    # Verify their members too: counting only the group container could report
    # a complete paste even when its filled regions or detail lines are missing.
    signature = Counter()
    for element in elements:
        members = ()
        if isinstance(element, DB.Group):
            contents = [element.Document.GetElement(eid) for eid in element.GetMemberIds()]
            members = tuple(sorted(_signature(contents).items()))
        signature[(element.GetType().FullName,
                   element.Text if isinstance(element, DB.TextNote) else '', members)] += 1
    return signature


def _viewport_type(old, placed, options):
    source = old.Document.GetElement(old.GetTypeId())
    name = DB.Element.Name.GetValue(source)
    dest = placed.Document
    for type_id in placed.GetValidTypes():
        if DB.Element.Name.GetValue(dest.GetElement(type_id)) == name:
            return type_id
    copied = DB.ElementTransformUtils.CopyElements(source.Document, _ids([source]), dest, DB.Transform.Identity, options)
    for type_id in copied:
        if placed.IsValidType(type_id) and DB.Element.Name.GetValue(dest.GetElement(type_id)) == name:
            return type_id
    raise ValueError(u'Revit could not transfer viewport type "{}".'.format(name))


def _copy_detail(old, target, point, options):
    src = old.Document
    dest = target.Document
    view = src.GetElement(old.ViewId)
    details = _content(view, check_references=True)
    created = DB.ElementTransformUtils.CopyElements(src, _ids([view]), dest, DB.Transform.Identity, options)
    candidates = [dest.GetElement(i) for i in created]
    views = [e for e in candidates if isinstance(e, DB.View) and e.ViewType == view.ViewType and not e.IsTemplate]
    if len(views) != 1:
        raise ValueError('Revit could not identify a single independent detail view in the destination.')
    duplicate = views[0]
    dest.Regenerate()
    expected = _signature(details)
    existing = _signature(_content(duplicate))
    if details and not existing:
        # Copy the detailing between views so Revit aligns their drawing planes.
        DB.ElementTransformUtils.CopyElements(view, _ids(details), duplicate, DB.Transform.Identity, options)
        dest.Regenerate()
        existing = _signature(_content(duplicate))
    if expected != existing or duplicate.Scale != view.Scale:
        raise ValueError('Revit could not preserve all detailing and the view scale in the destination project.')
    title_param = DB.BuiltInParameter.VIEW_DESCRIPTION
    printed = view.get_Parameter(title_param).AsString() or view.Name
    new_title = duplicate.get_Parameter(title_param)
    if (new_title.AsString() or duplicate.Name) != printed and not new_title.Set(printed):
        raise ValueError('The title on the destination sheet could not be preserved.')
    if not DB.Viewport.CanAddViewToSheet(dest, target.Id, duplicate.Id):
        raise ValueError('Revit cannot place the copied detail on this sheet.')
    placed = DB.Viewport.Create(dest, target.Id, duplicate.Id, point)
    type_id = _viewport_type(old, placed, options)
    if placed.GetTypeId() != type_id:
        replacement = placed.ChangeTypeId(type_id)
        if replacement != DB.ElementId.InvalidElementId:
            placed = dest.GetElement(replacement)
    placed.Rotation = old.Rotation
    placed.LabelOffset = old.LabelOffset
    placed.LabelLineLength = old.LabelLineLength
    dest.Regenerate()
    placed.SetBoxCenter(point)
    return placed


def _copy_annotation(source, target, old, point, options, moves):
    doc = target.Document
    if isinstance(old, DB.ImageInstance):
        copied = copy_image_ids(source, target, old, options)
    else:
        copied = DB.ElementTransformUtils.CopyElements(source, _ids([old]), target, DB.Transform.Identity, options)
    elements = [doc.GetElement(i) for i in copied]
    matches = [e for e in elements if e.GetType() == old.GetType() and e.OwnerViewId == target.Id]
    if moves.is_title_block(old):
        matches = [e for e in matches if moves.is_title_block(e) and e.SuperComponent is None]
    if len(matches) != 1:
        raise ValueError('Revit could not identify the copied sheet annotation.')
    placed = matches[0]
    doc.Regenerate()
    moves.position_sheet_copy(placed, point, old.Pinned)
    return placed


def _image_digest(image_type):
    import clr
    from System import BitConverter, Environment
    from System.Drawing.Imaging import ImageFormat
    from System.IO import MemoryStream
    if Environment.Version.Major >= 5:
        clr.AddReference('System.Security.Cryptography')
    from System.Security.Cryptography import SHA256
    bitmap = image_type.GetImage()
    if bitmap is None:
        raise ValueError('Reload the raster image so Revit can verify its contents before copying.')
    with bitmap, MemoryStream() as stream, SHA256.Create() as sha:
        bitmap.Save(stream, ImageFormat.Png)
        stream.Position = 0
        return BitConverter.ToString(sha.ComputeHash(stream))


def _link_identity(image_type):
    if image_type.PathType == DB.PathType.Relative:
        return os.path.normcase(os.path.normpath(os.path.join(os.path.dirname(image_type.Document.PathName), image_type.Path)))
    if image_type.PathType == DB.PathType.Absolute:
        return os.path.normcase(os.path.normpath(image_type.Path))
    refs = image_type.GetExternalResourceReferences()
    return [(str(r.ServerId), sorted((k, r.GetReferenceInformation()[k]) for k in r.GetReferenceInformation().Keys))
            for r in refs.Values]


def copy_image_ids(source, target, image, options):
    """Copy a raster between views using the source bitmap and link identity."""
    ids = _ids([image])
    if source.Document.Equals(target.Document):
        return DB.ElementTransformUtils.CopyElements(source, ids, target, DB.Transform.Identity, options)
    original = source.Document.GetElement(image.GetTypeId())
    name_param = DB.BuiltInParameter.SYMBOL_NAME_PARAM
    name = original.get_Parameter(name_param).AsString()
    types = dict((t.get_Parameter(name_param).AsString().lower(), t)
                 for t in DB.FilteredElementCollector(target.Document).OfClass(DB.ImageType))
    conflict = types.get(name.lower())
    if conflict is None:
        return DB.ElementTransformUtils.CopyElements(source, ids, target, DB.Transform.Identity, options)

    digest = _image_digest(original)
    candidate, label, number = conflict, name, 1
    while candidate is not None:
        if (original.Source == candidate.Source and original.WidthInPixels == candidate.WidthInPixels
                and original.HeightInPixels == candidate.HeightInPixels and original.Resolution == candidate.Resolution
                and original.PageNumber == candidate.PageNumber
                and (original.Source != DB.ImageTypeSource.Link or _link_identity(original) == _link_identity(candidate))
                and digest == _image_digest(candidate)):
            break
        number += 1
        label = u'{} ({})'.format(name, number)
        candidate = types.get(label.lower())
    if candidate is conflict:
        return DB.ElementTransformUtils.CopyElements(source, ids, target, DB.Transform.Identity, options)

    # Native Paste resolves image types by name, even when their pixels differ.
    # Reserve the name only inside the caller's per-item transaction. Restore
    # existing names before commit; any copy or rename failure rolls it all back.
    previous = conflict.get_Parameter(name_param).AsString()
    conflict.Name = 'Sheet Clipboard ' + str(Guid.NewGuid())
    if candidate is not None:
        label = candidate.get_Parameter(name_param).AsString()
        candidate.Name = name
    result = DB.ElementTransformUtils.CopyElements(source, ids, target, DB.Transform.Identity, options)
    placed = [target.Document.GetElement(i) for i in result]
    images = [e for e in placed if isinstance(e, DB.ImageInstance) and e.OwnerViewId == target.Id]
    if len(images) != 1 or images[0].GetTypeId() == conflict.Id:
        raise ValueError('Revit could not transfer the source raster image.')
    transferred = target.Document.GetElement(images[0].GetTypeId())
    if candidate is not None and transferred.Id != candidate.Id:
        raise ValueError('Revit could not reuse the matching raster image.')
    transferred.Name = label
    conflict.Name = previous
    return result


def paste(source, target, uids, dx, dy, moves, skipped):
    doc = target.Document
    delta = DB.XYZ(dx, dy, 0)
    placed = {}
    numbers = []
    options = DB.CopyPasteOptions()
    options.SetDuplicateTypeNamesHandler(DestinationTypes())
    group = DB.TransactionGroup(doc, 'Paste details from another project')
    try:
        group.Start()
        for uid in uids:
            old = source.Document.GetElement(uid)
            point = moves.item_anchor(old) + delta
            # A failed detail rolls back its view, annotation and any imported
            # types, including failures that Revit raises only at commit.
            tx = DB.Transaction(doc, 'Copy sheet detail')
            failures = moves._Failures()
            try:
                tx.Start()
                settings = tx.GetFailureHandlingOptions()
                settings.SetFailuresPreprocessor(failures).SetClearAfterRollback(True)
                tx.SetFailureHandlingOptions(settings)
                item = (_copy_detail(old, target, point, options) if isinstance(old, DB.Viewport)
                        else _copy_annotation(source, target, old, point, options, moves))
                doc.Regenerate()
                if moves._sheet_id(item) != target.Id:
                    raise ValueError('Revit placed the item on a different sheet.')
                moves._require_position(item, point)
                if tx.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit rolled back this detail. ' + ' '.join(failures.messages))
                placed[uid] = item.UniqueId
                if isinstance(item, DB.Viewport):
                    numbers.append((item, moves._detail(old).AsString()))
            except Exception as error:
                if tx.GetStatus() == DB.TransactionStatus.Started:
                    tx.RollBack()
                if not moves._expected_copy_failure(getattr(error, 'clsException', error)):
                    raise
                skipped.append((uid, getattr(error, 'Message', None) or unicode(error)))
            finally:
                tx.Dispose()
        if numbers:
            tx = DB.Transaction(doc, 'Set copied detail numbers')
            try:
                tx.Start()
                moves._assign_numbers(doc, target, numbers)
                if tx.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit could not commit destination detail numbers.')
            finally:
                if tx.GetStatus() == DB.TransactionStatus.Started:
                    tx.RollBack()
                tx.Dispose()
        if placed and group.Assimilate() != DB.TransactionStatus.Committed:
            raise ValueError('Revit could not commit the cross-project paste.')
    finally:
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        group.Dispose()
        options.Dispose()
    return placed
