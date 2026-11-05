# -*- coding: utf-8 -*-
"""Test schedule-definition copies and segment placements in an unsaved Revit project."""
import imp
import os
import json
import traceback
from System import Double, Enum
from System.Collections.Generic import List
from pyrevit import DB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = __revit__.Application.VersionNumber
REPORT = os.path.join(ROOT, 'diagnostics', 'schedule-copy-{}.json'.format(VERSION))
doc = None
tx = None
report = {'passed': False, 'version': __revit__.Application.VersionNumber, 'checks': []}


def check(label, value):
    if not value:
        raise AssertionError(label)
    report['checks'].append(label)


def limits(view):
    return [view.GetSegmentHeight(i) for i in range(view.GetSegmentCount()-1)]


def same_limits(a,b):
    return len(a)==len(b) and all(abs(x-y)<1e-7 for x,y in zip(a,b))


def copy_item(helper, old, target_sheet, point, cache, commit=True):
    # Exercise the command's per-item transaction/cache contract.
    item = DB.SubTransaction(doc)
    item.Start()
    try:
        placed = helper.copy_schedule(doc, old, target_sheet, point, cache)
        if commit:
            assert item.Commit() == DB.TransactionStatus.Committed
        else:
            item.RollBack()
        return placed
    except Exception:
        if item.GetStatus()==DB.TransactionStatus.Started:
            item.RollBack()
        raise
    finally:
        item.Dispose()


try:
    helper=imp.load_source('move_views_qa_schedule_copy', os.path.join(ROOT,'sheet_schedule_copy.py'))
    doc=__revit__.Application.NewProjectDocument(DB.UnitSystem.Imperial)
    tx=DB.Transaction(doc,'Build disposable schedule test')
    tx.Start()
    sheets=[DB.ViewSheet.Create(doc,DB.ElementId.InvalidElementId) for i in range(40)]
    source_sheet, target_sheet=sheets[:2]
    schedule=DB.ViewSchedule.CreateSheetList(doc)
    schedule.Name='Ndev QA Split Sheets'
    for bip in (DB.BuiltInParameter.SHEET_NUMBER, DB.BuiltInParameter.SHEET_NAME):
        field=next(f for f in schedule.Definition.GetSchedulableFields() if f.ParameterId==DB.ElementId(bip))
        schedule.Definition.AddField(field)
    field_ids=[f.FieldId for f in [schedule.Definition.GetField(i) for i in range(schedule.Definition.GetFieldCount())]]
    schedule.Definition.AddSortGroupField(DB.ScheduleSortGroupField(field_ids[0]))
    plain=doc.GetElement(schedule.Duplicate(DB.ViewDuplicateOption.Duplicate))
    plain.Name='Ndev QA Unsplit Sheets'
    doc.Regenerate()
    heights=List[Double]()
    heights.Add(.32)
    heights.Add(.49)
    schedule.Split(heights)
    doc.Regenerate()
    first=DB.ScheduleSheetInstance.Create(doc,source_sheet.Id,schedule.Id,DB.XYZ(.12,.9,0),0)
    last=DB.ScheduleSheetInstance.Create(doc,source_sheet.Id,schedule.Id,DB.XYZ(.59,.6,0),2)
    normal=DB.ScheduleSheetInstance.Create(doc,source_sheet.Id,plain.Id,DB.XYZ(.45,.2,0))
    first.Rotation=next(r for r in Enum.GetValues(first.Rotation.GetType()) if r!=first.Rotation)
    assert tx.Commit()==DB.TransactionStatus.Committed
    tx.Dispose();tx=None
    original_heights=limits(schedule)
    original_ids=[s.UniqueId for s in (first,last,normal)]
    check('Three source segments have ordered unequal fixed heights and an automatic last segment',
          schedule.GetSegmentCount()==3 and same_limits(original_heights,[.32,.49]))
    tx=DB.Transaction(doc,'Exercise schedule copy placements')
    tx.Start()
    stock=DB.SubTransaction(doc)
    stock.Start()
    try:
        native=doc.GetElement(schedule.Duplicate(DB.ViewDuplicateOption.Duplicate))
        doc.Regenerate()
        report['stock_duplicate_segment_count']=native.GetSegmentCount()
        report['stock_duplicate_fixed_heights_ft']=limits(native)
    finally:
        stock.RollBack();stock.Dispose()
    report['source_fixed_heights_ft']=original_heights
    before_count=DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).GetElementCount()
    cache={}
    failed=copy_item(helper,first,target_sheet,DB.XYZ(2,.7,0),cache,False)
    stale_uid=next(iter(cache.values()))
    check('Previously cached definition rolls back with a failed item', doc.GetElement(stale_uid) is None)
    p0,p2=DB.XYZ(2,.7,0),DB.XYZ(2.5,.5,0)
    copied_last=copy_item(helper,last,target_sheet,p2,cache)
    copied_first=copy_item(helper,first,target_sheet,p0,cache)
    dup=doc.GetElement(copied_last.ScheduleId)
    check('Two selected, noncontiguous segments use one new independent definition',
          dup.Id!=schedule.Id and copied_first.ScheduleId==dup.Id and
          DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).GetElementCount()==before_count+1)
    check('Recovered stale cache and preserved segment indices, rotation, and picked sheet locations',
          dup.UniqueId!=stale_uid and copied_last.SegmentIndex==2 and copied_first.SegmentIndex==0 and
          copied_first.Rotation==first.Rotation and copied_first.GetTypeId()==first.GetTypeId() and
          copied_last.Point.DistanceTo(p2)<1e-6 and copied_first.Point.DistanceTo(p0)<1e-6)
    check('Duplicated schedule has all three segments, field headings, sort settings, and original fixed height limits',
          dup.GetSegmentCount()==3 and same_limits(limits(dup),original_heights) and
          dup.Definition.GetSortGroupFieldCount()==schedule.Definition.GetSortGroupFieldCount() and
          [dup.Definition.GetField(i).ColumnHeading for i in range(dup.Definition.GetFieldCount())]==
          [schedule.Definition.GetField(i).ColumnHeading for i in range(schedule.Definition.GetFieldCount())])
    instances=[s for s in DB.FilteredElementCollector(doc,target_sheet.Id).OfClass(DB.ScheduleSheetInstance) if s.ScheduleId==dup.Id]
    check('Only requested segments are placed',sorted(s.SegmentIndex for s in instances)==[0,2])
    same=copy_item(helper,first,source_sheet,DB.XYZ(.3,.8,0),{})
    check('Second paste on the source sheet creates another independent definition',
          same.OwnerViewId==source_sheet.Id and same.ScheduleId!=schedule.Id and same.ScheduleId!=dup.Id)
    unsplit=copy_item(helper,normal,target_sheet,DB.XYZ(1.2,.2,0),{})
    check('Plain schedule also has a new definition and a whole-schedule placement',
          unsplit.ScheduleId!=plain.Id and doc.GetElement(unsplit.ScheduleId).GetSegmentCount()==1 and unsplit.SegmentIndex in (-1,0))
    dup.SetSegmentHeight(0,.39)
    doc.Regenerate()
    check('Changing copy segment size leaves originals and their placements intact',
          same_limits(limits(schedule),original_heights) and all(doc.GetElement(u) is not None for u in original_ids))
    assert tx.Commit()==DB.TransactionStatus.Committed
    tx.Dispose();tx=None
    report['passed']=True
except Exception:
    report['error']=traceback.format_exc()
finally:
    if tx is not None:
        if tx.GetStatus()==DB.TransactionStatus.Started:tx.RollBack()
        tx.Dispose()
    if doc:doc.Close(False)
    if not os.path.isdir(os.path.dirname(REPORT)):
        os.makedirs(os.path.dirname(REPORT))
    with open(REPORT,'w') as f:json.dump(report,f,indent=2)
