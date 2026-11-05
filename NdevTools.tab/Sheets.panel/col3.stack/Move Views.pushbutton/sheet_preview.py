# -*- coding: utf-8 -*-
"""Read-only sheet inventory and native sheet image snapshots. All rectangles use paper feet."""
from __future__ import division

import os
import shutil
import struct
import tempfile

from pyrevit import DB
from System.Collections.Generic import List


def sheet_label(sheet):
    return u'{} — {}'.format(sheet.SheetNumber, sheet.Name)


def list_sheets(doc):
    collector = DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
    try:
        rows = [{'uid': sheet.UniqueId, 'label': sheet_label(sheet)}
                for sheet in collector if not sheet.IsPlaceholder]
    finally:
        collector.Dispose()
    return sorted(rows, key=lambda row: row['label'].lower())


def _combine(rectangles):
    return [min(r[0] for r in rectangles), min(r[1] for r in rectangles),
            max(r[2] for r in rectangles), max(r[3] for r in rectangles)]


def _box_rect(box):
    if box is None:
        return None
    lo, hi = box.Min, box.Max
    transform = box.Transform
    corners = [transform.OfPoint(DB.XYZ(x, y, z)) for x in (lo.X, hi.X)
               for y in (lo.Y, hi.Y) for z in (lo.Z, hi.Z)]
    return [min(p.X for p in corners), min(p.Y for p in corners),
            max(p.X for p in corners), max(p.Y for p in corners)]


def _outline_rect(outline):
    lo, hi = outline.MinimumPoint, outline.MaximumPoint
    return [lo.X, lo.Y, hi.X, hi.Y]


def _placement(doc, sheet, element, moves):
    kind = element.Category.Name if element.Category is not None else element.GetType().Name
    detail = ''
    if isinstance(element, DB.Viewport):
        view = doc.GetElement(element.ViewId)
        title, kind = view.Name, str(view.ViewType)
        number = element.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
        detail = number.AsString() if number is not None else ''
        rect = _outline_rect(element.GetBoxOutline())
        try:
            label = element.GetLabelOutline()
            if label is not None and not label.IsEmpty:
                label_rect = _outline_rect(label)
                if label_rect[2] > label_rect[0] or label_rect[3] > label_rect[1]:
                    rect = _combine([rect, label_rect])
        except Exception:
            # A viewport type can suppress its title; its view box is still selectable.
            pass
    else:
        rect = _box_rect(element.get_BoundingBox(sheet))
        if isinstance(element, DB.ScheduleSheetInstance):
            view = doc.GetElement(element.ScheduleId)
            title, kind = view.Name, 'Schedule'
            if view.GetSegmentCount() > 1:
                title += u' · Segment {}'.format(element.SegmentIndex + 1)
        elif isinstance(element, DB.TextNote):
            title = (element.Text or '').splitlines()
            title = title[0].strip() if title else kind
        else:
            title = element.Name or kind
    anchor = moves.item_anchor(element)
    if rect is None or anchor is None:
        return None
    return {'uid': element.UniqueId, 'source': sheet.UniqueId, 'source_uid': sheet.UniqueId,
            'label': u'{} · {}'.format(detail, title) if detail else title,
            'name': title, 'kind': kind, 'detail': detail or '', 'rect': rect,
            'anchor': [anchor.X, anchor.Y]}


def _has_area(rect):
    return rect is not None and rect[2] > rect[0] + 1e-8 and rect[3] > rect[1] + 1e-8


def _export(doc, sheet, directory, outline):
    # Exporting only the requested sheet avoids activating it or changing its zoom.
    work = tempfile.mkdtemp(prefix='sheet-', dir=directory)
    options = DB.ImageExportOptions()
    try:
        options.ExportRange = DB.ExportRange.SetOfViews
        options.ZoomType = DB.ZoomFitType.FitToPage
        width, height = outline[2] - outline[0], outline[3] - outline[1]
        options.FitDirection = (DB.FitDirectionType.Horizontal if width >= height
                                else DB.FitDirectionType.Vertical)
        options.PixelSize = 2000
        options.HLRandWFViewsFileType = DB.ImageFileType.PNG
        options.ShadowViewsFileType = DB.ImageFileType.PNG
        options.FilePath = os.path.join(work, 'sheet')
        ids = List[DB.ElementId]()
        ids.Add(sheet.Id)
        options.SetViewsAndSheets(ids)
        doc.ExportImage(options)
        files = [os.path.join(work, f) for f in os.listdir(work) if f.lower().endswith('.png')]
        if len(files) != 1:
            raise ValueError('Revit did not produce one sheet image.')
        with open(files[0], 'rb') as source:
            header = source.read(24)
        if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
            raise ValueError('Revit returned an unreadable sheet image.')
        pw, ph = struct.unpack('>II', header[16:24])
        # Revit rounds the short side of FitToPage to pixels. A larger discrepancy
        # means we cannot safely overlay click targets on this crop.
        short = min(pw, ph)
        predicted = max(pw, ph) * min(width, height) / max(width, height)
        orientation_mismatch = (pw > ph) != (width > height) and abs(pw - ph) > 2
        if not pw or not ph or orientation_mismatch or abs(short - predicted) > 2:
            raise ValueError('The exported crop differs from the sheet coordinates.')
        return files[0]
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        options.Dispose()


def snapshot(doc, sheet_uid, temp_dir, moves):
    """Read one sheet. The caller owns the temporary images and caches this result."""
    sheet = doc.GetElement(sheet_uid)
    if not isinstance(sheet, DB.ViewSheet) or sheet.IsPlaceholder:
        raise ValueError('Choose an existing, placed sheet.')
    sheet_outline = sheet.Outline
    outline = [sheet_outline.Min.U, sheet_outline.Min.V, sheet_outline.Max.U, sheet_outline.Max.V]
    items, paper, messages = [], [], []
    # Reuse the same inventory for change detection. Sheet-owned annotations
    # can be deleted before DocumentChanged fires, so retain their element IDs.
    watched = set([sheet.Id])
    views = set()
    omitted = 0
    seen = set()
    owners = DB.FilteredElementCollector(doc).OwnedByView(sheet.Id).WhereElementIsNotElementType()
    # Some sheet placements expose SheetId rather than an OwnerViewId.
    ids = list(owners.ToElementIds()) + list(sheet.GetAllViewports())
    owners.Dispose()
    titleblock_category = DB.ElementId(DB.BuiltInCategory.OST_TitleBlocks)
    for element_id in ids:
        if element_id in seen:
            continue
        seen.add(element_id)
        element = doc.GetElement(element_id)
        if element is None:
            continue
        watched.update((element_id, element.GetTypeId()))
        if isinstance(element, DB.Viewport):
            views.add(element.ViewId)
        elif isinstance(element, DB.ScheduleSheetInstance):
            views.add(element.ScheduleId)
        if element.Category is not None and element.Category.Id == titleblock_category:
            box = _box_rect(element.get_BoundingBox(sheet))
            if _has_area(box):
                paper.append(box)
            continue
        if moves.supported(doc, element):
            try:
                item = _placement(doc, sheet, element, moves)
                if item:
                    items.append(item)
                else:
                    omitted += 1
            except Exception:
                omitted += 1
    image = None
    if _has_area(outline) and sheet.CanBePrinted:
        try:
            image = _export(doc, sheet, temp_dir, outline)
        except Exception as error:
            messages.append(u'Sheet drawing unavailable. {} Showing placement outlines.'.format(error))
    elif _has_area(outline):
        messages.append('This sheet cannot be printed. Showing placement outlines.')
    else:
        messages.append('This sheet has no two-dimensional drawing extents.')
    if omitted:
        messages.append('{} placement(s) could not be measured.'.format(omitted))
    rectangles = ([outline] if _has_area(outline) else []) + paper + [item['rect'] for item in items]
    bounds = _combine(rectangles) if rectangles else [0.0, 0.0, 3.0, 2.0]
    if not _has_area(bounds):
        bounds = [bounds[0] - .05, bounds[1] - .05, bounds[2] + .05, bounds[3] + .05]
    if paper and doc.ProjectInformation is not None:
        watched.add(doc.ProjectInformation.Id)
    watched.discard(DB.ElementId.InvalidElementId)
    views.discard(DB.ElementId.InvalidElementId)
    items.sort(key=lambda item: (item['label'].lower(), item['uid']))
    return {'uid': sheet.UniqueId, 'label': sheet_label(sheet), 'items': items, 'bounds': bounds,
            'image': image, 'image_bounds': outline if image else None,
            'paper_bounds': _combine(paper) if paper else None, 'message': ' '.join(messages),
            '_watch': (watched, views)}
