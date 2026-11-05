# -*- coding: utf-8 -*-
"""A project-bound clipboard for cut and repeatable copy on drawing sheets."""
from System import AppDomain, Array, Double, Guid
from System.Collections import ArrayList, Hashtable
from Autodesk.Revit.Exceptions import ArgumentException, InvalidOperationException, OperationCanceledException
from pyrevit import DB


KEY = 'NdevTools.Main.SheetCutPaste.Clipboard.v1'
TOLERANCE = 1e-6


def _entries():
    entries = AppDomain.CurrentDomain.GetData(KEY)
    if entries is None:
        entries = ArrayList()
        AppDomain.CurrentDomain.SetData(KEY, entries)
    for i in reversed(range(entries.Count)):
        if not entries[i]['document'].IsValidObject:
            entries.RemoveAt(i)
    return entries


def current(doc):
    for entry in _entries():
        if entry['document'].Equals(doc):
            return entry
    return None


def _sheet_element(element):
    return element.SheetId if isinstance(element, DB.Viewport) else element.OwnerViewId


def eligible(doc, sheet, element, moves):
    return moves.supported(doc, element) and _sheet_element(element) == sheet.Id


def selected_placements(doc, sheet, element_ids):
    selected = [doc.GetElement(eid) for eid in element_ids]
    selected = [item for item in selected if item is not None]
    if not any(isinstance(item, DB.View) and not isinstance(item, DB.ViewSheet) for item in selected):
        return selected
    # A Project Browser selection identifies the view definition, while the
    # clipboard operates on each of its actual placements on the active sheet.
    by_view = {}
    for eid in sheet.GetAllViewports():
        item = doc.GetElement(eid)
        by_view.setdefault(item.ViewId, []).append(item)
    collector = DB.FilteredElementCollector(doc).OfClass(DB.ScheduleSheetInstance).OwnedByView(sheet.Id)
    try:
        for item in collector:
            by_view.setdefault(item.ScheduleId, []).append(item)
    finally:
        collector.Dispose()
    result, seen = [], set()
    for item in selected:
        for instance in by_view.get(item.Id, [item]):
            if instance.Id not in seen:
                result.append(instance)
                seen.add(instance.Id)
    return result


def display_name(doc, element):
    if isinstance(element, DB.Viewport):
        return doc.GetElement(element.ViewId).Name
    if isinstance(element, DB.ScheduleSheetInstance):
        view = doc.GetElement(element.ScheduleId)
        if view is not None:
            return view.Name
    if isinstance(element, DB.TextNote) and element.Text:
        return element.Text.splitlines()[0]
    return element.Name or element.GetType().Name


def unavailable(doc, sheet, element):
    if element is None:
        return 'The original placement was deleted.'
    if _sheet_element(element) != sheet.Id:
        return 'The item does not belong to this sheet.'
    if element.Pinned:
        return 'The placement is pinned.'
    if element.GroupId != DB.ElementId.InvalidElementId:
        return 'The placement belongs to a group.'
    if isinstance(element, DB.ScheduleSheetInstance) and element.IsTitleblockRevisionSchedule:
        return 'The revision schedule belongs to a title block.'
    return u'Unsupported sheet item ({0}).'.format(element.GetType().Name)


def _record(doc, sheet, element, moves, preview):
    if not eligible(doc, sheet, element, moves):
        raise ValueError(unavailable(doc, sheet, element))
    row = preview._placement(doc, sheet, element, moves)
    if row is None:
        raise ValueError('A placement has no measurable bounds. Select the group again.')
    row['version'] = str(element.VersionGuid)
    return row


def sheet_items(doc, sheet, moves, preview):
    if not isinstance(sheet, DB.ViewSheet) or sheet.IsPlaceholder:
        raise ValueError('Open the source drawing sheet before selecting placements.')
    collector = DB.FilteredElementCollector(doc).OwnedByView(sheet.Id).WhereElementIsNotElementType()
    try:
        ids = list(collector.ToElementIds()) + list(sheet.GetAllViewports())
    finally:
        collector.Dispose()
    unique = set(ids)
    rows = []
    for eid in unique:
        element = doc.GetElement(eid)
        if moves.supported(doc, element):
            rows.append(_record(doc, sheet, element, moves, preview))
    return sorted(rows, key=lambda row: (row['label'].lower(), row['uid']))


def rejected_row(doc, sheet, element, preview, reason=None):
    rect = None
    if _sheet_element(element) == sheet.Id:
        rect = preview._box_rect(element.get_BoundingBox(sheet))
    return {'uid': element.UniqueId, 'label': display_name(doc, element), 'rect': rect or [],
            'kind': element.GetType().Name, 'anchor': [], 'version': '', 'blocked': reason or unavailable(doc, sheet, element)}


def store(doc, sheet, uids, operation, moves, preview):
    if operation not in ('cut', 'copy'):
        raise ValueError('Choose Cut or Copy.')
    if not uids or len(uids) != len(set(uids)):
        raise ValueError('Select one or more distinct items on the active sheet.')
    rows = []
    for uid in uids:
        element = doc.GetElement(uid)
        try:
            rows.append(_record(doc, sheet, element, moves, preview))
        except ValueError as error:
            if operation == 'cut' or element is None:
                raise
            rows.append(rejected_row(doc, sheet, element, preview, unicode(error)))
    rects = [row['rect'] for row in rows if row['rect']]
    center = [(min(r[axis] for r in rects) + max(r[axis+2] for r in rects)) * .5
              for axis in (0, 1)] if rects else [0., 0.]
    entry = Hashtable()
    entry['document'] = doc
    entry['token'] = str(Guid.NewGuid())
    entry['operation'] = operation
    entry['source'] = sheet.UniqueId
    entry['label'] = preview.sheet_label(sheet)
    entry['center'] = Array[Double](center)
    held = ArrayList()
    for row in rows:
        item = Hashtable()
        item['uid'], item['version'] = row['uid'], row['version']
        item['label'], item['blocked'] = row['label'], row.get('blocked', '')
        item['rect'] = Array[Double](row['rect'])
        item['anchor'] = Array[Double](row['anchor'])
        held.Add(item)
    entry['rows'] = held
    entries = _entries()
    previous = current(doc)
    if previous is not None:
        entries.Remove(previous)
    entries.Add(entry)
    return entry


def info(entry):
    if entry is None:
        return None
    rows = [{'uid': item['uid'], 'label': item['label'] or item['uid'], 'blocked': item['blocked'] or '',
             'version': item['version'], 'rect': list(item['rect']), 'anchor': list(item['anchor'])}
            for item in entry['rows']]
    # A held cut from the previous ribbon layout is still a valid cut in this session.
    return {'source': entry['source'], 'label': entry['label'], 'rows': rows,
            'operation': entry['operation'] or 'cut', 'center': list(entry['center'])}


def discard(doc, token):
    entry = current(doc)
    if entry is None or entry['token'] != token:
        raise ValueError('The clipboard has already changed.')
    _entries().Remove(entry)


def _validate(doc, token, moves, preview, skipped):
    entry = current(doc)
    if entry is None or entry['token'] != token:
        raise ValueError('This selection has been replaced or already pasted.')
    data = info(entry)
    source = doc.GetElement(data['source'])
    available = []
    for saved in data['rows']:
        try:
            if saved['blocked']:
                raise ValueError(saved['blocked'])
            if not isinstance(source, DB.ViewSheet) or source.IsPlaceholder:
                raise ValueError('The source sheet is unavailable.')
            row = _record(doc, source, doc.GetElement(saved['uid']), moves, preview)
            old = saved['rect'] + saved['anchor']
            new = row['rect'] + row['anchor']
            if saved['version'] != row['version'] or any(abs(a - b) > TOLERANCE for a, b in zip(old, new)):
                raise ValueError('The placement changed on its source sheet.')
            available.append(saved['uid'])
        except ValueError as error:
            if data['operation'] == 'cut':
                discard(doc, token)
                raise ValueError(u'{}: {} Cut the current group again.'.format(saved['label'], error))
            skipped.append((saved['uid'], unicode(error)))
    return entry, data, available


def _can_place(doc, target, view, option):
    # CanViewBeDuplicated and CanAddViewToSheet can both report True for a
    # plain legend duplicate that has no drawable content. Exercise Create,
    # then discard the check before opening the choice dialog.
    tx = DB.Transaction(doc, 'Check sheet placement')
    try:
        tx.Start()
        settings = tx.GetFailureHandlingOptions()
        settings.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(settings)
        vid = view.Id
        if option is not None:
            vid = view.Duplicate(option)
            doc.Regenerate()
        if not DB.Viewport.CanAddViewToSheet(doc, target.Id, vid):
            return False
        placed = DB.Viewport.Create(doc, target.Id, vid, DB.XYZ.Zero)
        if placed is None:
            return False
        doc.Regenerate()
        return placed.IsValidObject and placed.ViewId == vid
    except (ArgumentException, InvalidOperationException):
        return False
    finally:
        try:
            if tx.GetStatus() == DB.TransactionStatus.Started and tx.RollBack() != DB.TransactionStatus.RolledBack:
                raise RuntimeError('Revit could not complete its temporary placement check.')
        finally:
            tx.Dispose()


def _special_views(doc, target, uids):
    seen = set()
    for uid in uids:
        instance = doc.GetElement(uid)
        if not isinstance(instance, DB.Viewport):
            continue
        view = doc.GetElement(instance.ViewId)
        if str(view.ViewType) not in ('Legend', 'ColumnSchedule') or view.UniqueId in seen:
            continue
        seen.add(view.UniqueId)
        options = []
        if DB.Viewport.CanAddViewToSheet(doc, target.Id, view.Id) and _can_place(doc, target, view, None):
            options.append('share')
        for key, mode in [('detail', DB.ViewDuplicateOption.WithDetailing), ('duplicate', DB.ViewDuplicateOption.Duplicate)]:
            if view.CanViewBeDuplicated(mode) and _can_place(doc, target, view, mode):
                options.append(key)
        yield {'uid': view.UniqueId, 'label': view.Name, 'kind': str(view.ViewType),
               'options': options + ['skip']}


def paste(doc, destination, token, moves, preview, pick, choose=None, skipped=None):
    if not isinstance(destination, DB.ViewSheet) or destination.IsPlaceholder or not doc.Equals(destination.Document):
        raise ValueError('Open the destination drawing sheet before pasting.')
    if skipped is None:
        skipped = []
    entry, data, uids = _validate(doc, token, moves, preview, skipped)
    choices = {}
    if data['operation'] == 'copy':
        for prompt in _special_views(doc, destination, uids):
            if choose is None:
                raise ValueError('A legend or graphical column schedule requires a paste choice.')
            choice = choose(prompt)
            if choice is None:
                return None
            if choice not in prompt['options']:
                raise ValueError('This paste option is unavailable on the destination sheet.')
            choices[prompt['uid']] = choice
        for uid in list(uids):
            item = doc.GetElement(uid)
            if isinstance(item, DB.Viewport) and choices.get(doc.GetElement(item.ViewId).UniqueId) == 'skip':
                skipped.append((uid, 'Skipped by your paste choice.'))
                uids.remove(uid)
        if not uids:
            return {}
    try:
        point = pick()
    except OperationCanceledException:
        return None
    if point is None:
        return None
    # Native Revit selection is modal. Revalidate before writing if an external
    # callback changed the source or replaced the held selection while picking.
    new_skips = []
    entry, data, available = _validate(doc, token, moves, preview, new_skips)
    skipped.extend(item for item in new_skips if item not in skipped)
    uids = [uid for uid in uids if uid in available]
    dx, dy = point.X - data['center'][0], point.Y - data['center'][1]
    if data['operation'] == 'copy':
        if not uids:
            return {}
        return moves.copy_items(doc, data['source'], destination.UniqueId, uids, dx, dy, choices=choices, skipped=skipped)
    placed = moves.move(doc, data['source'], destination.UniqueId, uids, dx, dy, transaction_name='Paste Views')
    # Revit's shared move has committed before this buffer can be consumed.
    _entries().Remove(entry)
    return placed
