# -*- coding: utf-8 -*-
"""Copy a schedule definition once per paste; preserve the selected segment placements."""
from pyrevit import DB
from Autodesk.Revit.Exceptions import ArgumentException, InvalidOperationException
from System import Double
from System.Collections.Generic import List

TOLERANCE = 1e-6


def _split_heights(view):
    # The final segment is always automatic; GetSegmentHeight returns Double.MaxValue for it.
    return tuple(view.GetSegmentHeight(i) for i in range(view.GetSegmentCount() - 1))


def _same_splits(view, heights):
    actual = _split_heights(view)
    return len(actual) == len(heights) and all(abs(a-b) <= TOLERANCE for a, b in zip(actual, heights))


def _independent(doc, source, heights, cache):
    key = ('schedule', source.UniqueId)
    uid = cache.get(key)
    duplicate = doc.GetElement(uid) if uid else None
    if duplicate is None:
        option = DB.ViewDuplicateOption.Duplicate
        if not source.CanViewBeDuplicated(option):
            raise ValueError('Revit cannot duplicate the schedule "{}" independently.'.format(source.Name))
        duplicate = doc.GetElement(source.Duplicate(option))
        if not isinstance(duplicate, DB.ViewSchedule) or duplicate.Id == source.Id:
            raise ValueError('Revit did not create an independent schedule.')
        doc.Regenerate()
        if heights and duplicate.GetSegmentCount() == 1:
            # Revit Split takes the ordered fixed-height limits only. It calculates the final segment.
            values = List[Double]()
            for height in heights:
                values.Add(height)
            duplicate.Split(values)
            doc.Regenerate()
    if (not isinstance(duplicate, DB.ViewSchedule) or duplicate.Id == source.Id or
            duplicate.GetPrimaryViewId() != DB.ElementId.InvalidElementId or not _same_splits(duplicate, heights)):
        raise ValueError('The independent schedule did not preserve the original ordered segment heights.')
    return key, duplicate


def copy_schedule(doc, old, target, point, cache):
    """Caller owns the subtransaction, shared placement data and the per-paste cache."""
    if not isinstance(old, DB.ScheduleSheetInstance):
        raise ValueError('Select an ordinary schedule placement.')
    source = doc.GetElement(old.ScheduleId)
    if (not isinstance(source, DB.ViewSchedule) or source.IsTemplate or old.IsTitleblockRevisionSchedule or
            source.IsInternalKeynoteSchedule or source.IsTitleblockRevisionSchedule or source.Definition.IsFilteredBySheet):
        raise ValueError('Sheet-filtered, internal, and title-block revision schedules cannot be copied as ordinary schedules.')
    if source.AssociatedAssemblyInstanceId != DB.ElementId.InvalidElementId:
        raise ValueError('This schedule belongs to an assembly.')
    if source.Definition.IsKeySchedule:
        raise ValueError('Key schedules are outside the ordinary schedule copy workflow.')
    heights = _split_heights(source)
    index = old.SegmentIndex
    if index < -1 or index > len(heights):
        raise ValueError('The selected schedule placement has an invalid segment index.')
    try:
        key, duplicate = _independent(doc, source, heights, cache)
        placed = DB.ScheduleSheetInstance.Create(doc, target.Id, duplicate.Id, point, index)
        if placed.GetTypeId() != old.GetTypeId():
            changed = placed.ChangeTypeId(old.GetTypeId())
            if changed != DB.ElementId.InvalidElementId:
                placed = doc.GetElement(changed)
        if placed.Rotation != old.Rotation:
            placed.Rotation = old.Rotation
        placed.Point = point
        doc.Regenerate()
    except (ArgumentException, InvalidOperationException) as error:
        raise ValueError('Revit could not copy "{}" with its original splits: {}'.format(source.Name, error))
    # Revit uses either 0 or -1 for an unsplit placement. A split schedule distinguishes both.
    same_index = placed.SegmentIndex == index or (not heights and placed.SegmentIndex in (-1, 0))
    if (not same_index or placed.OwnerViewId != target.Id or placed.ScheduleId != duplicate.Id or
            placed.Rotation != old.Rotation or placed.GetTypeId() != old.GetTypeId() or
            placed.Point.DistanceTo(point) > TOLERANCE):
        raise ValueError('Revit could not preserve the selected schedule placement.')
    cache[key] = duplicate.UniqueId
    return placed
