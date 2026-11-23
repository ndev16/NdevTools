"""Place explicitly mapped CAD face pairs without external conversion libraries."""
from System import String
from Autodesk.Revit.Exceptions import RegenerationFailedException
from pyrevit import DB
from ndev_main_cad_buttons import (CadTransaction, CadFailures, source_schema, source_key, xyz, point, eid)
from ndev_main_cad_math import line_key
from ndev_main_cad_mapping_math import mapped_pairs
from ndev_main_cad_wall_plan import wall_plan,run_key,join_wall_axes
from ndev_main_cad_corner_joins import traced_walls, enable_wall_end, clean_touching_walls, close_corner_gaps, fit_corner_faces


class NoWallOverlapFailures(CadFailures):
    def PreprocessFailures(self,accessor):
        rollback=False
        for failure in accessor.GetFailureMessages():
            self.messages.append(failure.GetDescriptionText())
            overlap=str(failure.GetFailureDefinitionId().Guid).lower()=='988a6cb2-7050-4a5c-a946-60d652df66c3'
            if overlap or failure.GetSeverity()!=DB.FailureSeverity.Warning:
                rollback=True
            else:
                accessor.DeleteWarning(failure)
        return DB.FailureProcessingResult.ProceedWithRollBack if rollback else DB.FailureProcessingResult.Continue


class WallCornerFailures(NoWallOverlapFailures):
    def PreprocessFailures(self,accessor):
        disjoint=DB.BuiltInFailures.JoinElementsFailures
        for failure in accessor.GetFailureMessages():
            guid=failure.GetFailureDefinitionId().Guid
            if guid in (disjoint.JoiningDisjoint.Guid,disjoint.JoiningDisjointWarn.Guid):
                self.messages.append(failure.GetDescriptionText())
                return DB.FailureProcessingResult.ProceedWithRollBack
        return NoWallOverlapFailures.PreprocessFailures(self,accessor)


def opening_corners(host,c,d,z,sill):
    axis=host.Location.Curve
    points=[]
    for p,dz in ((c,sill),(d,7.)):
        proj=axis.Project(xyz(p,axis.GetEndPoint(0).Z))
        if proj is None or not axis.IsInside(proj.Parameter):
            raise ValueError('CAD opening extends beyond the wall ends.')
        points.append(DB.XYZ(proj.XYZPoint.X,proj.XYZPoint.Y,z+dz))
    return points


def constrain_opening(doc,opening,level,low,high):
    # Wall Tracing sets BOTH level constraints to the host base; the offsets
    # are relative to the level, not to the already-offset wall bottom.
    values=(('WALL_BASE_CONSTRAINT',level.Id),('WALL_HEIGHT_TYPE',level.Id),
            ('WALL_BASE_OFFSET',low-level.ProjectElevation),('WALL_TOP_OFFSET',high-level.ProjectElevation))
    for key,value in values:
        parameter=opening.get_Parameter(getattr(DB.BuiltInParameter,key))
        if parameter is None:
            raise ValueError('Opening constraint is unavailable: '+key)
        current=parameter.AsElementId() if isinstance(value,DB.ElementId) else parameter.AsDouble()
        if current==value: continue
        if parameter.IsReadOnly: raise ValueError('Opening constraint is read-only: '+key)
        parameter.Set(value)
    doc.Regenerate()
    for key,value in values:
        parameter=opening.get_Parameter(getattr(DB.BuiltInParameter,key))
        if isinstance(value,DB.ElementId):
            matches=parameter.AsElementId()==value
        else:
            matches=abs(parameter.AsDouble()-value)<1./304.8
        if not matches: raise ValueError('Revit did not retain opening constraint: '+key)


def selected_cuts(pair,create_doors,create_windows):
    cuts=[]
    if create_doors:
        cuts.extend(('Door',0.,span) for span in pair.get('openings',()))
    if create_windows:
        cuts.extend(('Window',3.,span) for span in pair.get('window_openings',()))
    return cuts


def opening_join_guards(runs,wall_height):
    if wall_height<=7.+1e-8: return []
    guards=[]
    for row,symbol,pairs,held in runs:
        pair=pairs[0]
        for end in pair.get('join_axis',pair['axis']):
            # Keep short CAD returns available when cuts are enabled on a later
            # Place. The host and its corner treatment are independent of which
            # openings the user chooses to cut today.
            for cut in list(pair.get('openings',()))+list(pair.get('window_openings',())):
                if any((p[0]-end[0])**2+(p[1]-end[1])**2 <= (2*row['width_mm']/304.8)**2 for p in cut):
                    guards.append(end)
                    break
    return guards


def near_guard(point,guards):
    return any((point.X-p[0])**2+(point.Y-p[1])**2<=(1./304.8)**2 for p in guards)


def finish_wall_joins(doc,walls,guards,result):
    new_walls={eid(element_id) for element_id in result['ids']}
    for wall in walls:
        if eid(wall.Id) not in new_walls: continue
        if wall.Pinned or wall.GroupId!=DB.ElementId.InvalidElementId: continue
        for end in (0,1):
            if DB.WallUtils.IsWallJoinAllowedAtEnd(wall,end):continue
            if near_guard(wall.Location.Curve.GetEndPoint(end),guards):
                # The unstable automatic join stays off. The shared-face pass
                # below can still clean this corner without moving the opening.
                continue
            reason=enable_wall_end(doc,wall,end,WallCornerFailures)
            if reason:
                result['warnings'].append('Wall {} end {}: {}'.format(eid(wall.Id),end+1,reason))
    cleaned,notes=clean_touching_walls(doc,walls,WallCornerFailures)
    result['corner_joins']=cleaned
    result['warnings'].extend(notes)
    checked,fixed,notes=fit_corner_faces(doc,walls,guards,WallCornerFailures)
    result.update(flush_corners=checked,face_repairs=fixed)
    result['warnings'].extend(notes)


def place(doc, kind, cad, rows, choices, bottom, top, bottom_offset,
          top_offset, exclude=False, cutoff_mm=0, create_doors=True, create_windows=True):
    args=(doc,kind,cad,rows,choices,bottom,top,bottom_offset,top_offset,exclude,cutoff_mm)
    if kind!='Walls':
        return _place(*args)
    if bottom is None or top is None or cad.Document!=doc:
        raise ValueError('Choose the drawing and wall levels in this project.')
    if top.ProjectElevation+top_offset<=bottom.ProjectElevation+bottom_offset:
        raise ValueError('The wall top must be above its bottom. On the same level, set Top offset higher than Bottom offset.')
    plan=wall_plan(rows,choices,exclude,cutoff_mm,min_run=doc.Application.ShortCurveTolerance)
    group=DB.TransactionGroup(doc,'Trace mapped walls')
    group.Start()
    try:
        lower=_place_independent(args,plan,create_doors,create_windows)
        if group.Assimilate()!=DB.TransactionStatus.Committed:
            raise ValueError('Revit did not commit the mapped walls.')
        return lower
    finally:
        if group.GetStatus()==DB.TransactionStatus.Started:
            group.RollBack()
        group.Dispose()


def _place_independent(args,plan,create_doors,create_windows):
    join_wall_axes(plan)
    runs=[(row,symbol,[pair],0) for row,symbol,pairs,held in plan for pair in pairs]
    if len(runs)>2000:
        raise ValueError('Limit each placement to 2000 candidates.')
    result=dict(created=0,existing=0,rejected=0,consolidated=0,openings=0,ids=[],warnings=[],outcomes={},
                ambiguous=sum(held for row,symbol,pairs,held in plan))
    def attempt(batch):
        try:
            done=_place(*(args+(batch,)))
        except RegenerationFailedException:
            raise
        except Exception as error:
            if len(batch)>1:
                mid=len(batch)//2
                attempt(batch[:mid])
                attempt(batch[mid:])
                return
            if batch:
                reason=' / '.join(sorted(set(str(error).splitlines())))
                result['outcomes'][run_key(batch[0][2][0])]=('rejected: '+reason,None)
                result['rejected']+=1
            return
        collect(done)
    def collect(done):
        for field in ('created','existing','consolidated','openings'):
            result[field]+=done.get(field,0)
        result['ids'].extend(done['ids'])
        result['warnings'].extend(done['warnings'])
        result['outcomes'].update(done['outcomes'])
    if runs:
        attempt(runs)
        doc,kind,cad=args[:3]
        walls=traced_walls(doc,cad,result['outcomes'])
        bottom,top,base_offset,top_offset=args[5:9]
        guards=opening_join_guards(runs,top.ProjectElevation+top_offset-bottom.ProjectElevation-base_offset)
        result['extended_corner_ends'],notes=close_corner_gaps(doc,walls,guards,WallCornerFailures)
        result['warnings'].extend(notes)
        if create_doors or create_windows:
            cut_plan={run_key(pair):selected_cuts(pair,create_doors,create_windows)
                      for row,symbol,pairs,held in runs for pair in pairs}
            cut_wall_openings(args,runs,result,guards,cut_plan)
        finish_wall_joins(doc,walls,guards,result)
    return result


def cut_wall_openings(args,runs,result,guards,cut_plan):
    doc,kind,cad,rows,choices,bottom,top,base_offset,top_offset,exclude,cutoff=args
    for row,symbol,pairs,held in runs:
        pair=pairs[0]
        element_id=result['outcomes'].get(run_key(pair),('',None))[1]
        cuts=cut_plan[run_key(pair)]
        if element_id is None or not cuts:
            continue
        host=doc.GetElement(DB.ElementId(element_id))
        if host is None or host.GetTypeId()!=symbol.Id or not host.GetEntity(source_schema()).IsValid():
            continue
        # Read this committed host, including an existing traced wall whose
        # actual constraints may differ from the current mapping choices.
        base=doc.GetElement(host.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId())
        upper=doc.GetElement(host.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId())
        z=base.ProjectElevation+host.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET).AsDouble()
        height=(upper.ProjectElevation+host.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()-z
                if upper is not None else host.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM).AsDouble())
        if height<=7.+1e-8:
            result['warnings'].append('Skipped openings on wall {}: wall height {:.2f} ft is not above 7 ft.'.format(element_id,height))
            continue
        a,b=host.Location.Curve.GetEndPoint(0),host.Location.Curve.GetEndPoint(1)
        axis=(point(a),point(b))
        from ndev_main_cad_wall_plan import intersection
        for kind,sill,(c,d) in cuts:
            width=((c[0]-d[0])**2+(c[1]-d[1])**2)**0.5
            span=intersection(axis,(c,d),1,1)
            if not span or span[1]-span[0]<width-1.0/304.8:
                continue
            try:
                existing=[doc.GetElement(i) for i in host.GetDependentElements(DB.ElementClassFilter(DB.Opening))]
                corners=opening_corners(host,c,d,z,sill)
                c,d=point(corners[0]),point(corners[1])
                def same_plan(op):
                    if not isinstance(op,DB.Opening) or not op.IsRectBoundary: return False
                    ends=list(op.BoundaryRect)
                    if len(ends)!=2: return False
                    near=lambda v,p: ((v.X-p[0])**2+(v.Y-p[1])**2)**0.5<1.0/304.8
                    return (near(ends[0],c) and near(ends[1],d)) or (near(ends[0],d) and near(ends[1],c))
                def same_opening(op):
                    if not same_plan(op): return False
                    heights=[p.Z for p in op.BoundaryRect]
                    return abs(min(heights)-(z+sill))<1.0/304.8 and abs(max(heights)-(z+7))<1.0/304.8
                prior=[op for op in existing if same_plan(op)]
                if prior:
                    if not any(same_opening(op) for op in prior):
                        result['warnings'].append('{} on wall {} at {}: existing opening has different elevations.'.format(kind,element_id,c))
                    continue
                for op in existing:
                    if not isinstance(op,DB.Opening) or not op.IsRectBoundary: continue
                    p,q=list(op.BoundaryRect)
                    if (min(p.Z,q.Z)<z+7.-1./304.8 and max(p.Z,q.Z)>z+sill+1./304.8 and
                            intersection((c,d),(point(p),point(q)),1,1)):
                        raise ValueError('An existing opening overlaps this cut. No duplicate was created.')
                with CadTransaction(doc,'Cut CAD '+kind.lower()+' opening'):
                    for end in (0,1):
                        if near_guard(host.Location.Curve.GetEndPoint(end),guards) and DB.WallUtils.IsWallJoinAllowedAtEnd(host,end):
                            DB.WallUtils.DisallowWallJoinAtEnd(host,end)
                    opening=doc.Create.NewOpening(host,corners[0],corners[1])
                    constrain_opening(doc,opening,base,corners[0].Z,corners[1].Z)
                    if not same_opening(opening):
                        raise ValueError('Opening dimensions did not match its CAD mark.')
                result['openings']+=1
                key=kind.lower()+'_openings'
                result[key]=result.get(key,0)+1
            except RegenerationFailedException:
                raise
            except Exception as error:
                result['warnings'].append('Opening on wall {} at {}: {}'.format(element_id,c,error))



def _place(doc, kind, cad, rows, choices, bottom, top, bottom_offset,
           top_offset, exclude, cutoff_mm, accepted_override=None):
    if kind not in ('Walls', 'Beams'):
        raise ValueError('This mapping placement supports walls and beams.')
    if cad.Document != doc or top is None:
        raise ValueError('Choose a drawing and levels from this project.')
    level = bottom if kind == 'Walls' else top
    if level is None:
        raise ValueError('Choose a bottom level.')
    z = (level.ProjectElevation if kind=='Walls' else level.Elevation) + (bottom_offset if kind == 'Walls' else top_offset)
    height = (top.ProjectElevation if kind=='Walls' else top.Elevation) + top_offset - z
    if kind == 'Walls' and height <= 0:
        raise ValueError('The top constraint must be above the bottom constraint.')
    accepted=accepted_override if accepted_override is not None else mapped_pairs(rows,choices,exclude,cutoff_mm)
    schema = source_schema()
    field = schema.GetField('SourceKey')
    category = DB.BuiltInCategory.OST_Walls if kind == 'Walls' else DB.BuiltInCategory.OST_StructuralFraming
    existing, tracked = {}, {}
    previous_segments={}
    outcomes={}
    for element in DB.FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
        entity = element.GetEntity(schema)
        if entity.IsValid():
            tracked[entity.Get[String](field)]=eid(element.Id)
        location = element.Location
        if isinstance(location, DB.LocationCurve) and isinstance(location.Curve, DB.Line):
            curve = location.Curve
            a, b = point(curve.GetEndPoint(0)), point(curve.GetEndPoint(1))
            if kind == 'Walls':
                base = doc.GetElement(element.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId())
                if base:
                    wall_z = base.ProjectElevation + element.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET).AsDouble()
                    a, b = (a[0], a[1], wall_z), (b[0], b[1], wall_z)
            existing[line_key(a, b)]=eid(element.Id)
            if kind=='Walls' and entity.IsValid() and base and base.Id==level.Id and abs(wall_z-z)<1e-6:
                key=line_key(a,b)
                if entity.Get[String](field)==source_key(kind,cad,key):
                    previous_segments[key]=element
    pending = []
    skipped = 0
    replacements={}
    extend_ends={}
    for row, symbol, pairs, ambiguous in accepted:
        if symbol.Document != doc:
            raise ValueError('A mapped type belongs to another project.')
        for pair in pairs:
            a, b = pair['axis']
            key = line_key((a[0], a[1], z), (b[0], b[1], z))
            original_key=key
            a,b=pair.get('join_axis',pair['axis'])
            key=line_key((a[0],a[1],z),(b[0],b[1],z))
            tag = source_key(kind, cad, key)
            old=previous_segments.get(original_key)
            if old is not None and key!=original_key and key not in existing and tag not in tracked:
                if (old.Pinned or old.GroupId!=DB.ElementId.InvalidElementId or old.GetTypeId()!=symbol.Id or
                    old.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()!=top.Id or
                    abs(old.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()-top_offset)>1e-6 or
                    old.FindInserts(True,True,True,True).Count):
                    raise ValueError('Review existing wall {} before extending its ends.'.format(eid(old.Id)))
                extend_ends[eid(old.Id)]=(old,a,b,tag)
                existing[key]=eid(old.Id)
                previous_segments[key]=old
            if pair.get('perimeter'):
                for c,d in pair.get('previous_axes',()):
                    old_key=line_key((c[0],c[1],z),(d[0],d[1],z))
                    old=previous_segments.get(old_key)
                    if old is None or old_key in (key,original_key):
                        continue
                    if (old.Pinned or old.GroupId!=DB.ElementId.InvalidElementId or old.GetTypeId()!=symbol.Id
                            or old.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()!=top.Id
                            or abs(old.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()-top_offset)>1e-6
                            or old.FindInserts(True,True,True,True).Count):
                        raise ValueError('Existing traced wall {} has constraints or inserts requiring review.'.format(eid(old.Id)))
                    replacements[eid(old.Id)]=old.Id
            if key in existing or tag in tracked:
                # A previous pass may deliberately have released this end,
                # or the neighboring wall's end, to keep a valid doorway.
                # A duplicate must never re-enable that join.
                skipped += 1
                outcomes[run_key(pair)]=('already present' if existing.get(key) or tracked.get(tag) else 'duplicate in this run',tracked.get(tag) or existing.get(key))
                continue
            existing[key]=None
            pending.append((symbol, a, b, tag,run_key(pair)))
    if len(pending) > 2000:
        raise ValueError('Limit each placement to 2000 candidates.')
    created = []
    warnings = []
    if pending or replacements or extend_ends:
        transaction=CadTransaction(doc, 'CAD mapped '+kind.lower())
        if kind=='Walls':
            transaction.failures=NoWallOverlapFailures()
        with transaction as operation:
            for element_id,(wall,a,b,tag) in extend_ends.items():
                if element_id in replacements: continue
                wall.Location.Curve=DB.Line.CreateBound(xyz(a,z),xyz(b,z))
                entity=wall.GetEntity(schema)
                entity.Set[String](field,tag)
                wall.SetEntity(entity)
            for old_id in replacements.values():
                deleted=doc.Delete(old_id)
                if any(i!=old_id for i in deleted):
                    raise ValueError('Consolidating traced wall {} would remove dependent elements. Rolled back.'.format(eid(old_id)))
            for symbol, a, b, tag, faces in pending:
                curve = DB.Line.CreateBound(xyz(a, z), xyz(b, z))
                if kind == 'Walls':
                    element = DB.Wall.Create(doc, curve, symbol.Id, level.Id, height,
                                             bottom_offset, False, True)
                    for end in (0,1):
                        DB.WallUtils.DisallowWallJoinAtEnd(element,end)
                    element.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).Set(top.Id)
                    element.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).Set(top_offset)
                else:
                    if not symbol.IsActive:
                        symbol.Activate()
                        doc.Regenerate()
                    element = doc.Create.NewFamilyInstance(curve, symbol, level, DB.Structure.StructuralType.Beam)
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(element, 0)
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(element, 1)
                entity = DB.ExtensibleStorage.Entity(schema)
                entity.Set[String](field, tag)
                element.SetEntity(entity)
                created.append(element.Id)
                outcomes[faces]=('created',eid(element.Id))
            doc.Regenerate()
            tolerance = 1.0/304.8
            for element_id, (symbol, a, b, tag, faces) in zip(created, pending):
                element = doc.GetElement(element_id)
                if element is None or element.GetTypeId() != symbol.Id:
                    raise ValueError('Revit did not retain the mapped type.')
                actual = [element.Location.Curve.GetEndPoint(i) for i in (0, 1)]
                expected = [xyz(a, z), xyz(b, z)]
                if kind == 'Walls':
                    if (element.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId() != top.Id or
                        abs(element.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()-top_offset) > tolerance or
                        abs(element.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET).AsDouble()-bottom_offset) > tolerance):
                        raise ValueError('Wall constraints did not match the mapping.')
                    actual = [DB.XYZ(p.X,p.Y,0) for p in actual]
                    expected = [DB.XYZ(p.X,p.Y,0) for p in expected]
                error = min(max(actual[0].DistanceTo(expected[0]),actual[1].DistanceTo(expected[1])),
                            max(actual[0].DistanceTo(expected[1]),actual[1].DistanceTo(expected[0])))
                if error > tolerance or not element.GetEntity(schema).IsValid():
                    raise ValueError('Placement did not match the mapped centerline. Changes rolled back.')
        warnings = operation.failures.messages
    return {'created': len(created), 'ids': created, 'existing': skipped,'outcomes':outcomes,'consolidated':len(replacements),
            'ambiguous': sum(d for r,t,p,d in accepted), 'warnings': warnings}
