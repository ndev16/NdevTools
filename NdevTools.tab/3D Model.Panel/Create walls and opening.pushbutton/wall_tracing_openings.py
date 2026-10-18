# -*- coding: utf-8 -*-
"""Insert-first, local wall-cut detection. No anonymous wall-gap discovery.

No insert sweep, solid subtraction, layer section or family-facing test is used.
All coordinates remain in the linked document until the engine creates the cut.
"""
from pyrevit import DB
from wall_tracing_math import TOL, rectangle_bounds, rectangle_metrics, boundary_notches, clip_polygon, cut_match_score


def id_text(eid):
    return str(eid.Value if hasattr(eid,'Value') else eid.IntegerValue)


def solids(geometry):
    if geometry is None:
        return
    for item in geometry:
        if item is None:
            continue
        if isinstance(item,DB.Solid):
            if item.Volume > TOL**3 and item.Faces is not None and item.Faces.Size > 0:
                yield item
        elif isinstance(item,DB.GeometryInstance):
            for solid in solids(item.GetInstanceGeometry()):
                yield solid


def curve_points(curve):
    if isinstance(curve,DB.Line):
        return [curve.GetEndPoint(0),curve.GetEndPoint(1)]
    # A curved edge is retained for diagnostics, never flattened into a chord.
    return list(curve.Tessellate())


def projected_loop(curves, origin, tangent):
    curves=list(curves)
    if not curves:
        raise ValueError('Wall-face loop is empty.')
    points=[]
    curved=False
    for i,curve in enumerate(curves):
        if curve.GetEndPoint(1).DistanceTo(curves[(i+1)%len(curves)].GetEndPoint(0)) > TOL:
            raise ValueError('Wall-face loop is not closed.')
        samples=curve_points(curve)
        curved = curved or not isinstance(curve,DB.Line)
        points.extend((p.Subtract(origin).DotProduct(tangent),p.Z) for p in samples[:-1])
    return points,curved


def classify_loop(loop, context):
    points,curved=projected_loop(loop,context['origin'],context['axis'].Direction)
    if curved:
        raise ValueError('Actual wall-face boundary contains a curved edge.')
    return rectangle_bounds(points)


def area(points):
    return abs(sum(p[0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*p[1]
                   for i,p in enumerate(points)))/2.0


def candidate(points,edges,mode,curved=False):
    item=dict(points=points,raw_edges=edges,raw_points=len(points),mode=mode,
              insert_ids=[],result='NON_RECTANGULAR',valid=False,reason='',bounds=None,
              sides=[0,0,0,0],rectangle_valid=False)
    if points:
        xs,zs=zip(*points)
        bounds=min(xs),max(xs),min(zs),max(zs)
        item['bounds']=bounds
        item['sides']=[sum(abs(p[axis]-value)<=TOL for p in points)
                       for axis,value in ((0,bounds[0]),(0,bounds[1]),(1,bounds[2]),(1,bounds[3]))]
    try:
        if curved:
            raise ValueError('Wall-face loop contains a genuine curved edge.')
        item['bounds']=rectangle_bounds(points)
        item['valid']=True
        item['rectangle_valid']=True
        item['result']='BOUNDARY_NOTCH' if mode=='outer-notch' else 'PENDING'
        item['reason']='PASS: every segment follows a rectangle side; closed perimeter and area verified.'
    except Exception as error:
        item['reason']=str(error)
    return item


def box_points(box):
    if box is None:
        return []
    return [box.Transform.OfPoint(DB.XYZ(x,y,z)) for x in (box.Min.X,box.Max.X)
            for y in (box.Min.Y,box.Max.Y) for z in (box.Min.Z,box.Max.Z)]


def real_inserts(wall):
    """API wall relationship first; spatial fallback requires an explicit void cut."""
    records={}
    ids=list(wall.FindInserts(True,False,True,True))
    ids.extend(wall.GetDependentElements(DB.ElementClassFilter(DB.Opening)))
    for eid in ids:
        element=wall.Document.GetElement(eid)
        if isinstance(element,(DB.FamilyInstance,DB.Opening)):
            records[id_text(eid)]=(element,'HOSTED_INSERT')
    try:
        corners=box_points(wall.get_BoundingBox(None))
        if corners:
            low=DB.XYZ(min(p.X for p in corners)-TOL,min(p.Y for p in corners)-TOL,min(p.Z for p in corners)-TOL)
            high=DB.XYZ(max(p.X for p in corners)+TOL,max(p.Y for p in corners)+TOL,max(p.Z for p in corners)+TOL)
            nearby=(DB.FilteredElementCollector(wall.Document).OfClass(DB.FamilyInstance)
                    .WherePasses(DB.BoundingBoxIntersectsFilter(DB.Outline(low,high))))
            for element in nearby:
                if id_text(element.Id) in records:
                    continue
                try:
                    # Spatial overlap alone is not proof of a cutting element.
                    if DB.InstanceVoidCutUtils.InstanceVoidCutExists(wall,element):
                        records[id_text(element.Id)]=(element,'CUTTING_ELEMENT_FALLBACK')
                except Exception:
                    continue
    except Exception:
        pass  # Hosted inserts remain usable when spatial/void-cut APIs are unavailable.
    return list(records.values())


def project_extent(element,origin,tangent):
    points=box_points(element.get_BoundingBox(None))
    if not points:
        raise ValueError('Insert has no spatial extent.')
    xs=[p.Subtract(origin).DotProduct(tangent) for p in points]
    return min(xs),max(xs),min(p.Z for p in points),max(p.Z for p in points)


def projected_geometry_extent(element,origin,tangent):
    """Retry invalid projected bounds using actual instance geometry, never facing."""
    points=[]
    options=DB.Options()
    options.DetailLevel=DB.ViewDetailLevel.Fine
    for solid in solids(element.get_Geometry(options)):
        for edge in solid.Edges:
            points.extend(edge.AsCurve().Tessellate())
    if not points:
        raise ValueError('No insert geometry available for extent retry.')
    xs=[p.Subtract(origin).DotProduct(tangent) for p in points]
    return min(xs),max(xs),min(p.Z for p in points),max(p.Z for p in points)


def face_data(wall,origin,tangent,normal):
    """Read reusable side-face topology only AFTER real inserts were found.

    No gaps/candidates are extracted here. Candidate classification is scoped to
    each insert's window in local_candidates.
    """
    options=DB.Options(); options.DetailLevel=DB.ViewDetailLevel.Fine
    options.ComputeReferences=True
    faces=[]
    for solid in solids(wall.get_Geometry(options)):
        for face in solid.Faces:
            if (face is not None and isinstance(face,DB.PlanarFace) and face.Area>TOL*TOL
                    and abs(abs(face.FaceNormal.DotProduct(normal))-1)<TOL):
                faces.append(face)
    if not faces:
        raise ValueError('No usable vertical planar side face.')
    major=max([f for f in faces if f.FaceNormal.DotProduct(normal)>0] or faces,key=lambda f:f.Area)
    depth=major.Origin.Subtract(origin).DotProduct(normal)
    regions=[]
    for face in faces:
        if (face.FaceNormal.DotProduct(major.FaceNormal)<1-TOL or
                abs(face.Origin.Subtract(origin).DotProduct(normal)-depth)>TOL):
            continue
        loops=[]
        for loop in face.GetEdgesAsCurveLoops():
            curves=list(loop)
            points,curved=projected_loop(curves,origin,tangent)
            loops.append(dict(points=points,curved=curved,edges=len(curves)))
        if loops:
            loops.sort(key=lambda r:area(r['points']),reverse=True)
            regions.append(loops)
    if not regions:
        raise ValueError('Side-face perimeter unavailable.')
    return regions


def wall_envelope(wall):
    def p(name): return wall.get_Parameter(getattr(DB.BuiltInParameter,name))
    base=wall.Document.GetElement(p('WALL_BASE_CONSTRAINT').AsElementId())
    top=wall.Document.GetElement(p('WALL_HEIGHT_TYPE').AsElementId())
    low=base.ProjectElevation+p('WALL_BASE_OFFSET').AsDouble()
    high=top.ProjectElevation+p('WALL_TOP_OFFSET').AsDouble() if isinstance(top,DB.Level) else low+p('WALL_USER_HEIGHT_PARAM').AsDouble()
    return 0,wall.Location.Curve.Length,low,high


def touches(bounds,envelope):
    return [abs(a-b)<=TOL for a,b in zip(bounds,envelope)]


def within(bounds,window):
    return (bounds[0]>=window[0]-TOL and bounds[1]<=window[1]+TOL and
            bounds[2]>=window[2]-TOL and bounds[3]<=window[3]+TOL)


def local_candidates(regions,extent,envelope):
    """Only discover missing regions within this real insert's small search window."""
    padding=4*TOL
    window=(max(envelope[0],extent[0]-padding),min(envelope[1],extent[1]+padding),
            max(envelope[2],extent[2]-padding),min(envelope[3],extent[3]+padding))
    if window[1]-window[0]<=TOL or window[3]-window[2]<=TOL:
        return []
    found=[]
    clipped=[]
    raw_count=0
    local_points=[]
    for region in regions:
        local_region=[]
        for index,loop in enumerate(region):
            points=loop['points']
            piece=clip_polygon(points,window)
            if len(piece)<3 or area(piece)<=TOL*TOL:
                if index==0:
                    break
                continue
            local_region.append(piece)
            raw_count+=loop['edges']; local_points.extend(piece)
            if index>0:
                item=candidate(points,loop['edges'],'INNER_LOOP',loop['curved'])
                if item['bounds'] and within(item['bounds'],window):
                    found.append(item)
            # Curves cannot be treated as orthogonal notch evidence.
            if loop['curved']:
                local_region=[]
                break
        if local_region:
            clipped.append(local_region)
    if not clipped:
        return found
    try:
        for bounds,rectangular in boundary_notches(clipped,window):
            flags=touches(bounds,envelope)
            if not any(flags):
                continue
            # A window edge is not a real cut boundary. Reject cropped candidates
            # rather than create an opening from the insert's bounding box.
            if any(abs(bounds[i]-window[i])<=TOL and not flags[i] for i in range(4)):
                continue
            l,r,b,t=bounds
            item=candidate([(l,b),(r,b),(r,t),(l,t)],raw_count,'OUTER_NOTCH')
            item['raw_points']=len(local_points)
            item['sides']=[sum(abs(p[a]-v)<=TOL for p in local_points) for a,v in ((0,l),(0,r),(1,b),(1,t))]
            if not rectangular:
                item.update(valid=False,result='NON_RECTANGULAR',reason='Insert-local missing region is concave or irregular.')
            # Full-height end gaps are wall join/end conditions even when an
            # insert's frame happens to overlap them. Be conservative.
            width,height,_=rectangle_metrics(bounds)
            iw,ih,_=rectangle_metrics(extent)
            if ((flags[0] or flags[1]) and height>=0.95*(envelope[3]-envelope[2])
                    or width<=TOL or min(width,iw)/max(width,iw)<0.5):
                item.update(valid=False,result='WALL_JOIN_OR_BOUNDARY',reason='Wall-end/full-height gap or notch width inconsistent with real insert.')
            found.append(item)
    except Exception:
        # A local diagonal/curved notch is unresolved; independent inner loops
        # remain usable. No full-wall gap scan is attempted as a fallback.
        pass
    return found


def scan_wall_openings(wall):
    try:
        inserts=real_inserts(wall)
    except Exception as error:
        item=candidate([],0,'HOSTED_INSERT')
        item.update(result='GEOMETRY_FAILURE',reason='Could not enumerate actual inserts: '+str(error))
        return [item]
    if not inserts:
        return []  # Critical: no anonymous wall-gap candidates or report rows.
    axis=wall.Location.Curve
    origin,tangent,normal=axis.GetEndPoint(0),axis.Direction,wall.Orientation.Normalize()
    rows=[]; accepted=[]; regions=None
    for element,method in inserts:
        item=candidate([],0,method)
        item.update(insert_ids=[id_text(element.Id)],discovery=method,insert_extent=None,
                    overlap=(0,0),touches=[False]*4,category='',family='',type_name='')
        try:
            item['category']=element.Category.Name if element.Category else ''
            symbol=wall.Document.GetElement(element.GetTypeId())
            if symbol:
                item['family']=getattr(symbol,'FamilyName','')
                parameter=symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                item['type_name']=parameter.AsString() if parameter else ''
        except Exception:
            pass
        try:
            extent=project_extent(element,origin,tangent)
            item['insert_extent']=extent
            if min(extent[1]-extent[0],extent[3]-extent[2])<=TOL:
                item['extent_retry']='INVALID_PROJECTED_INSERT_EXTENT: retried using actual geometry.'
                try:
                    extent=projected_geometry_extent(element,origin,tangent)
                except Exception as error:
                    item.update(result='INVALID_PROJECTED_INSERT_EXTENT',reason='No reliable insert-local search window after actual geometry retry: '+str(error))
                    rows.append(item); continue
            item['insert_extent']=extent
            if min(extent[1]-extent[0],extent[3]-extent[2])<=TOL:
                item.update(result='INVALID_PROJECTED_INSERT_EXTENT',reason='Actual geometry still gives negligible projected width/height; no search window can be justified.')
                rows.append(item); continue
            if regions is None:
                regions=face_data(wall,origin,tangent,normal)
            envelope=wall_envelope(wall)
            candidates=local_candidates(regions,extent,envelope)
            ranked=[]
            for cut in candidates:
                if cut['bounds']:
                    score,x,z=cut_match_score(cut['bounds'],extent)
                    if score>=0:
                        ranked.append((cut['valid'],score,x,z,cut))
            if not ranked:
                item.update(result='NO_MATCHING_CUT',reason='No complete validated cut boundary in this insert search window.')
            else:
                valid,score,x,z,cut=max(ranked,key=lambda row:(row[0],row[1]))
                metadata=dict((k,v) for k,v in item.items() if k in
                              ('insert_ids','discovery','insert_extent','category','family','type_name','extent_retry'))
                item=cut
                item.update(metadata)
                item['overlap']=(x,z); item['touches']=touches(item['bounds'],envelope)
                if item['valid']:
                    if any(all(abs(a-b)<=TOL for a,b in zip(item['bounds'],previous)) for previous in accepted):
                        item.update(valid=False,result='DUPLICATE',reason='Actual continuous cut already associated with another insert on this wall.')
                    else:
                        accepted.append(item['bounds'])
        except Exception as error:
            item.update(valid=False,result='GEOMETRY_FAILURE',reason='Insert-local cut scan: {}: {}'.format(type(error).__name__,error))
        rows.append(item)
    return rows


def diagnostic_text(item,source_id,host_id):
    bounds=item.get('bounds')
    width,height,center=rectangle_metrics(bounds) if bounds else (None,None,None)
    return ('Source Wall ID: {} | Destination Wall ID: {} | Insert ID: {}\n'
            'Category: {} | Family: {} | Type: {}\nDiscovery: {} | Detection method: {}\n'
            'Insert minX,maxX,minZ,maxZ: {} | Cut minX,maxX,minZ,maxZ: {}\n'
            'Raw edges: {} | Raw points: {} | Width: {} | Height: {} | Center: {}\n'
            'X/Z overlap ratios: {} | Touches start/end/bottom/top: {}\n'
            'Rectangle validation: {} | Result: {} | Creation result: {}\nReason: {} {}').format(
                source_id,host_id,','.join(item['insert_ids']) or '-',item.get('category',''),
                item.get('family',''),item.get('type_name',''),item.get('discovery',''),item['mode'],
                item.get('insert_extent'),bounds,item['raw_edges'],item['raw_points'],width,height,center,
                item.get('overlap'),item.get('touches'),'PASS' if item.get('rectangle_valid',item['valid']) else 'FAIL',
                item['result'],item['result'],item['reason'],item.get('extent_retry','')) + (
            '\nPrimary geometry: {} | Primary failure: {} | Fallback attempted: {}\n'
            'Width source/parameter/value: {} / {} / {}\nHeight source/parameter/value: {} / {} / {}\n'
            'Bottom source/parameter: {} / {} | Center source: {}\nHost validation: {} | Final detection method: {}').format(
                item.get('primary_geometry',''),item.get('primary_failure',''),item.get('fallback_attempted','NO'),
                item.get('width_source','NONE'),item.get('width_parameter',''),item.get('width_value'),
                item.get('height_source','NONE'),item.get('height_parameter',''),item.get('height_value'),
                item.get('bottom_source','NONE'),item.get('bottom_parameter',''),item.get('center_source','NONE'),
                item.get('host_validation',''),item.get('detection_source','NONE'))


