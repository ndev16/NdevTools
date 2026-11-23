"""Finish CAD wall corners using Wall Tracing's end-join and shared-face cleanup."""
import json
import math

from Autodesk.Revit.Exceptions import RegenerationFailedException
from System import String
from pyrevit import DB

from ndev_main_cad_buttons import CadTransaction, eid, source_schema
from ndev_main_cad_wall_plan import intersection


TOL=1./304.8


def corner_moves(first,second):
    """Wall Tracing's bounded, outward-only moves to the common XY intersection."""
    p,q=first['points'],second['points']
    u,v=p[1]-p[0],q[1]-q[0]
    la,lb=math.hypot(u.X,u.Y),math.hypot(v.X,v.Y)
    cross=u.X*v.Y-u.Y*v.X
    if min(la,lb)<=TOL or abs(cross)<0.1*la*lb: return []
    delta=q[0]-p[0]
    t=(delta.X*v.Y-delta.Y*v.X)/cross
    s=(delta.X*u.Y-delta.Y*u.X)/cross
    limit=min(1.,(first['width']+second['width'])/2.+1./12.)
    moves=[]
    for record,station,length in ((first,t*la,la),(second,s*lb,lb)):
        if station < -limit-TOL or station > length+limit+TOL: return []
        if station < -TOL or station > length+TOL:
            end=int(station>length)
            point=DB.XYZ(p[0].X+t*u.X,p[0].Y+t*u.Y,record['points'][end].Z)
            moves.append((record,end,point,record['points'][end].DistanceTo(point)))
    return moves


def close_corner_gaps(doc,walls,guards,failures):
    records=[]
    face_nodes={frozenset((eid(n[0].Id),eid(n[3].Id))):n for n in _elbows(walls)}
    for wall in walls:
        curve=wall.Location.Curve
        if isinstance(curve,DB.Line):
            records.append(dict(wall=wall,curve=curve,points=[curve.GetEndPoint(i) for i in (0,1)],
                                width=wall.Width,box=wall.get_BoundingBox(None)))
    options={}
    junctions=[]
    for i,first in enumerate(records):
        for second in records[i+1:]:
            a,b=first['box'],second['box']
            if a is None or b is None or min(a.Max.Z,b.Max.Z)<=max(a.Min.Z,b.Min.Z)+TOL: continue
            if any(getattr(a.Max,k)+2.+TOL<getattr(b.Min,k) or getattr(b.Max,k)+2.+TOL<getattr(a.Min,k)
                   for k in ('X','Y')): continue
            # Do not reach past a junction already occupied by either wall.
            moves=corner_moves(first,second)
            if not moves: continue
            node=face_nodes.get(frozenset((eid(first['wall'].Id),eid(second['wall'].Id))))
            if node is not None and _corner_solid_ok(node): continue
            if any(not free_extension(record,end,point,records,guards) for record,end,point,distance in moves): continue
            junctions.append(moves)
            for record,end,point,distance in moves:
                options.setdefault((eid(record['wall'].Id),end),[]).append((distance,point))
    preferred={}
    for key,choices in options.items():
        choices.sort(key=lambda choice:choice[0])
        distance,target=choices[0]
        if all(d>distance+TOL or point.DistanceTo(target)<=TOL for d,point in choices[1:]):
            preferred[key]=target
    notes=[]
    moved=0
    for moves in junctions:
        if any((eid(r['wall'].Id),e) not in preferred or preferred[eid(r['wall'].Id),e].DistanceTo(p)>TOL
               for r,e,p,d in moves): continue
        moves=[move for move in moves if move[0]['wall'].Location.Curve.GetEndPoint(move[1]).DistanceTo(move[2])>TOL]
        if not moves: continue
        try:
            inserts={}
            for record,end,target,distance in moves:
                for element_id in record['wall'].FindInserts(True,True,True,True):
                    element=doc.GetElement(element_id)
                    points=insert_points(element)
                    if not points:
                        raise ValueError('Wall {} has an insert whose position cannot be verified.'.format(
                            eid(record['wall'].Id)))
                    inserts[eid(element_id)]=(element,points)
            tx=CadTransaction(doc,'Extend traced ends to wall corner')
            tx.failures=failures()
            with tx:
                for record,end,target,distance in moves:
                    wall=record['wall']
                    ends=[wall.Location.Curve.GetEndPoint(i) for i in (0,1)]
                    ends[end]=target
                    wall.Location.Curve=DB.Line.CreateBound(*ends)
                doc.Regenerate()
                if any(r['wall'].Location.Curve.GetEndPoint(e).DistanceTo(p)>TOL for r,e,p,d in moves):
                    raise ValueError('Revit did not retain the corner endpoints.')
                for element,original in inserts.values():
                    current=insert_points(element)
                    if len(current)!=len(original) or any(a.DistanceTo(b)>TOL for a,b in zip(original,current)):
                        raise ValueError('The extension would move an existing opening or insert.')
            moved+=len(moves)
        except RegenerationFailedException:
            raise
        except Exception as error:
            notes.append('Corner extension needs review: '+str(error))
    return moved,notes


def insert_points(element):
    if element is None or not element.IsValidObject: return []
    if isinstance(element,DB.Opening) and element.IsRectBoundary:
        return list(element.BoundaryRect)
    location=element.Location
    if isinstance(location,DB.LocationPoint): return [location.Point]
    if isinstance(location,DB.LocationCurve): return [location.Curve.GetEndPoint(i) for i in (0,1)]
    return []


def free_extension(record,end,target,records,guards):
    wall=record['wall']
    start=record['points'][end]
    if wall.Pinned or wall.GroupId!=DB.ElementId.InvalidElementId: return False
    if any(math.hypot(start.X-g[0],start.Y-g[1])<=TOL for g in guards): return False
    def xy(p): return p.X,p.Y,0.
    for other in records:
        if other is record: continue
        pts=other['points']
        at_level=DB.XYZ(start.X,start.Y,pts[0].Z)
        if other['curve'].Distance(at_level)<=TOL: return False
        if intersection((xy(start),xy(target)),tuple(xy(p) for p in pts),
                        record['width']*304.8,other['width']*304.8):
            return False
    return True


def traced_walls(doc,cad,outcomes):
    """Only repair a selected run's walls that were created from this drawing."""
    ids={element_id for _,element_id in outcomes.values() if element_id is not None}
    schema=source_schema()
    field=schema.GetField('SourceKey')
    walls=[]
    for element_id in sorted(ids):
        wall=doc.GetElement(DB.ElementId(element_id))
        if not isinstance(wall,DB.Wall): continue
        entity=wall.GetEntity(schema)
        if not entity.IsValid(): continue
        try:
            source=json.loads(entity.Get[String](field))
        except (ValueError,TypeError):
            continue
        if source[:2]==['Walls',cad.UniqueId]:
            walls.append(wall)
    return walls


def joined_at_end(wall):
    location=wall.Location
    return {eid(neighbor.Id) for end in (0,1) for neighbor in location.ElementsAtJoin[end]}


def enable_wall_end(doc,wall,end,failures):
    """Use Wall Tracing's default, butt, then miter attempts in separate transactions."""
    styles=[None]+[getattr(DB.JoinType,name) for name in ('Abut','Miter') if hasattr(DB.JoinType,name)]
    reasons=[]
    for style in styles:
        tx=CadTransaction(doc,'Join traced wall end')
        tx.failures=failures()
        try:
            with tx:
                DB.WallUtils.AllowWallJoinAtEnd(wall,end)
                if style is not None and wall.Location.get_JoinType(end)!=style:
                    wall.Location.set_JoinType(end,style)
                doc.Regenerate()
                if not DB.WallUtils.IsWallJoinAllowedAtEnd(wall,end):
                    raise ValueError('Revit did not retain the wall-end join.')
            return None
        except RegenerationFailedException:
            raise
        except Exception as error:
            reasons.append(str(error))
    return reasons[-1]


def clean_touching_walls(doc,walls,failures):
    """Check the native end joins, then join touching faces in either order."""
    bounded=[]
    warnings=[]
    cleaned=0
    for wall in walls:
        if wall.Pinned or wall.GroupId!=DB.ElementId.InvalidElementId: continue
        box=wall.get_BoundingBox(None)
        if box is not None:
            bounded.append((wall,box,joined_at_end(wall)))
    for index,(first,a,first_neighbors) in enumerate(bounded):
        for second,b,second_neighbors in bounded[index+1:]:
            if any(getattr(a.Max,axis)+1.e-4<getattr(b.Min,axis) or
                   getattr(b.Max,axis)+1.e-4<getattr(a.Min,axis) for axis in ('X','Y','Z')):
                continue
            if min(a.Max.Z,b.Max.Z)-max(a.Min.Z,b.Min.Z)<=1.e-4: continue
            if (eid(first.Id) in second_neighbors or eid(second.Id) in first_neighbors or
                    DB.JoinGeometryUtils.AreElementsJoined(doc,first,second)):
                continue
            # A bounding box may cross an angled wall without its solid touching.
            # Confirm real contact before accepting a join or reporting a failure.
            if not centerlines_meet(first.Location.Curve,second.Location.Curve): continue
            for left,right in ((first,second),(second,first)):
                tx=CadTransaction(doc,'Clean traced wall corner')
                tx.failures=failures()
                try:
                    with tx:
                        DB.JoinGeometryUtils.JoinGeometry(doc,left,right)
                        doc.Regenerate()
                        if not DB.JoinGeometryUtils.AreElementsJoined(doc,first,second):
                            raise ValueError('Wall faces did not join.')
                    cleaned+=1
                    break
                except RegenerationFailedException:
                    raise
                except Exception as error:
                    reason=str(error)
            else:
                warnings.append('Corner between walls {} and {} needs review: {}'.format(
                    eid(first.Id),eid(second.Id),reason))
    return cleaned,warnings


def centerlines_meet(first,second):
    """At an L, T or straight continuation, an endpoint lies on its neighbor."""
    tolerance=1./304.8
    for curve,other in ((first,second),(second,first)):
        for end in (0,1):
            p=curve.GetEndPoint(end)
            q=DB.XYZ(p.X,p.Y,other.GetEndPoint(0).Z)
            if other.Distance(q)<=tolerance: return True
    return False


def _elbows(walls):
    """Use the original CAD vertex even after a previous butt repair moved an end."""
    field=source_schema().GetField('SourceKey')
    buckets={};seen=set();nodes=[]
    for w in walls:
        c=w.Location.Curve
        if not isinstance(c,DB.Line) or w.WallType.Kind!=DB.WallKind.Basic: continue
        pts=[c.GetEndPoint(i) for i in (0,1)]
        original=json.loads(w.GetEntity(source_schema()).Get[String](field))[2]
        nominal=[DB.XYZ(*p) for p in original]
        if (nominal[1]-nominal[0]).DotProduct(pts[1]-pts[0])<0: nominal.reverse()
        for end in (0,1):
            direction=(pts[1-end]-pts[end]).Normalize()
            for vertex in (pts[end],nominal[end]):
                x,y=int(math.floor(vertex.X/TOL)),int(math.floor(vertex.Y/TOL))
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        for old,e,u,previous in buckets.get((x+dx,y+dy),()):
                            key=(eid(old.Id),e,eid(w.Id),end)
                            if old.Id==w.Id or key in seen or math.hypot(vertex.X-previous.X,vertex.Y-previous.Y)>TOL: continue
                            sin=abs(u.X*direction.Y-u.Y*direction.X)
                            if sin<.15: continue
                            # A changed trace can still have an old tracking key.
                            # Only treat it as its original elbow if both actual
                            # axes still lie there, and both ends are locally near.
                            valid=True
                            for member,i,limit in ((old,e,w.Width*.5/sin),(w,end,old.Width*.5/sin)):
                                line=member.Location.Curve;p=line.GetEndPoint(i)
                                delta=DB.XYZ(vertex.X-p.X,vertex.Y-p.Y,0)
                                if delta.GetLength()>limit+2*TOL or abs(delta.X*line.Direction.Y-delta.Y*line.Direction.X)>TOL:
                                    valid=False;break
                            if not valid: continue
                            a,b=old.get_BoundingBox(None),w.get_BoundingBox(None)
                            z=min(a.Max.Z,b.Max.Z) if a and b else 0
                            if not a or not b or z-max(a.Min.Z,b.Min.Z)<.06: continue
                            seen.add(key)
                            nodes.append((old,e,u,w,end,direction,DB.XYZ(vertex.X,vertex.Y,z-.025),sin))
                buckets.setdefault((x,y),[]).append((w,end,direction,vertex))
    boxes=[(w,w.get_BoundingBox(None)) for w in walls]
    contexts=[]
    for node in nodes:
        a,e,u,b,f,v,o,sin=node
        radius=(a.Width+b.Width)*.52/sin
        others=[w for w,box in boxes if w.Id not in (a.Id,b.Id) and box is not None and
                box.Min.X-radius<=o.X<=box.Max.X+radius and box.Min.Y-radius<=o.Y<=box.Max.Y+radius and
                box.Min.Z<o.Z<box.Max.Z]
        contexts.append(node+(others,))
    return contexts


def _corner_solid_ok(node):
    first,e,u,second,f,v,o,sin,others=node
    opts=DB.Options();opts.DetailLevel=DB.ViewDetailLevel.Fine
    solids=[s for w in (first,second) for s in w.get_Geometry(opts) if isinstance(s,DB.Solid) and s.Volume>0]
    neighboring=None
    ab=second.Width*.5/sin;ba=first.Width*.5/sin
    opt=DB.SolidCurveIntersectionOptions()
    try:
        # In this local basis (+,+) is the inside turn and (-,-) the outside.
        # Sample on both sides of the two face intersections, excluding the exact
        # surface where Revit may classify a point either way.
        for x,y,expected in ((-.98,-.98,True),(.98,.98,True),(-.98,.98,True),(.98,-.98,True),
                             (-.5,-.5,True),(-1.02,-1.02,False),(1.02,1.02,False)):
            p=o+u*(x*ab)+v*(y*ba)
            ray=DB.Line.CreateBound(p-DB.XYZ.BasisZ*.01,p+DB.XYZ.BasisZ*.01)
            present=any(s.IntersectWithCurve(ray,opt).SegmentCount for s in solids)
            if expected and not present and others:
                if neighboring is None:
                    neighboring=[s for w in others for s in w.get_Geometry(opts) if isinstance(s,DB.Solid) and s.Volume>0]
                present=any(s.IntersectWithCurve(ray,opt).SegmentCount for s in neighboring)
            if present!=expected:return False
        return True
    finally: opt.Dispose()


def _corner_inserts(doc,walls):
    points={}
    for w in walls:
        for id_ in w.FindInserts(True,True,True,True):
            positions=insert_points(doc.GetElement(id_))
            if not positions: raise ValueError('An insert position could not be verified.')
            points[eid(id_)]=positions
    return points


def _face_repair(doc,node,mode,failures):
    a,e,u,b,f,v,o,sin,others=node
    before=_corner_inserts(doc,(a,b))
    group=DB.TransactionGroup(doc,'Verify exterior wall corner');group.Start()
    try:
        tx=CadTransaction(doc,'Fit wall faces at CAD corner');tx.failures=failures()
        with tx:
            if mode=='miter':
                for wall,end in ((a,e),(b,f)):
                    wall.Location.set_JoinType(end,DB.JoinType.Miter)
            else:
                wall,end,direction,neighbor,other_end,other_dir=(a,e,u,b,f,v) if mode%2==0 else (b,f,v,a,e,u)
                pts=[wall.Location.Curve.GetEndPoint(i) for i in (0,1)]
                # Only right angles have a square end exactly coincident with
                # the opposite outside face. Never use a square cap on a slope.
                far=DB.XYZ(o.X,o.Y,pts[end].Z)-direction*(neighbor.Width*.5)
                if DB.WallUtils.IsWallJoinAllowedAtEnd(wall,end):
                    DB.WallUtils.DisallowWallJoinAtEnd(wall,end)
                pts[end]=far
                wall.Location.Curve=DB.Line.CreateBound(*pts)
                if mode>=2:
                    # If overlapping ends cannot regenerate, fit the second cap
                    # to the first wall's inner face instead. The two solids then
                    # share a face with no sliver of overlapping material.
                    pts=[neighbor.Location.Curve.GetEndPoint(i) for i in (0,1)]
                    near=DB.XYZ(o.X,o.Y,pts[other_end].Z)+other_dir*(wall.Width*.5)
                    if (pts[1-other_end]-near).DotProduct(other_dir)<=doc.Application.ShortCurveTolerance:
                        raise ValueError('The short return would be consumed by this corner.')
                    if DB.WallUtils.IsWallJoinAllowedAtEnd(neighbor,other_end):
                        DB.WallUtils.DisallowWallJoinAtEnd(neighbor,other_end)
                    pts[other_end]=near
                    neighbor.Location.Curve=DB.Line.CreateBound(*pts)
                doc.Regenerate()
                if not DB.JoinGeometryUtils.AreElementsJoined(doc,wall,neighbor) and (
                        neighbor.Id not in [n.Id for n in wall.Location.ElementsAtJoin[end]] and
                        wall.Id not in [n.Id for n in neighbor.Location.ElementsAtJoin[other_end]]):
                    try: DB.JoinGeometryUtils.JoinGeometry(doc,wall,neighbor)
                    except RegenerationFailedException:raise
                    except Exception: DB.JoinGeometryUtils.JoinGeometry(doc,neighbor,wall)
            doc.Regenerate()
            if not _corner_solid_ok(node):raise ValueError('The inside or outside wall face did not meet.')
        # Revit can change joins when the transaction commits. Check committed
        # solids and insert positions before keeping the repair.
        after=_corner_inserts(doc,(a,b))
        if not _corner_solid_ok(node) or set(after)!=set(before) or any(
                len(original)!=len(after[k]) or any(p.DistanceTo(q)>TOL for p,q in zip(original,after[k]))
                for k,original in before.items()):
            raise ValueError('The committed corner or an existing opening moved.')
        if group.Assimilate()!=DB.TransactionStatus.Committed: raise ValueError('Corner repair did not commit.')
    finally:
        if group.GetStatus()==DB.TransactionStatus.Started: group.RollBack()
        group.Dispose()


def fit_corner_faces(doc,walls,guards,failures):
    """Finish actual L corners; do not connect doors, open ends or through-wall T's."""
    fixed=checked=0;notes=[]
    # Working with immutable candidate vertices avoids enumeration across regenerations.
    for node in _elbows(walls):
        a,e,u,b,f,v,o,sin,others=node
        try:
            if _corner_solid_ok(node):checked+=1;continue
            for w,end,other in ((a,e,b),(b,f,a)):
                if w.Pinned or w.GroupId!=DB.ElementId.InvalidElementId:
                    raise ValueError('The endpoint is constrained.')
            if any(n.Id not in (a.Id,b.Id) for w,i in ((a,e),(b,f)) for n in w.Location.ElementsAtJoin[i]):
                continue  # Through-wall or multiway junction, not a two-wall exterior elbow.
            protected=any(math.hypot(o.X-g[0],o.Y-g[1])<=TOL for g in guards)
            allowed=[DB.WallUtils.IsWallJoinAllowedAtEnd(w,i) for w,i in ((a,e),(b,f))]
            modes=[]
            if all(allowed) and not protected:modes.append('miter')
            if abs(u.DotProduct(v))<1.e-5:
                order=sorted((0,1),key=lambda i:(allowed[i],(a,b)[i].FindInserts(True,True,True,True).Count))
                modes+=order+[2+i for i in order]
            reasons=[]
            for mode in modes:
                try:
                    _face_repair(doc,node,mode,failures)
                    fixed+=1;checked+=1;break
                except RegenerationFailedException: raise
                except Exception as error:
                    reason=str(error)
                    if reason not in reasons: reasons.append(reason)
            else:raise ValueError(' / '.join(reasons) if reasons else 'No safe corner fit at this angle.')
        except RegenerationFailedException:raise
        except Exception as error:
            notes.append('Exterior corner of walls {} and {} needs review: {}'.format(eid(a.Id),eid(b.Id),error))
    return checked,fixed,notes
