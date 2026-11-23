"""Independent thickness inventory and filtering for CAD mapping."""
import math


def overlap_on_axis(first,second,tolerance=1.0/304.8):
    a,b=first
    c,d=second
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<=tolerance:
        return False
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    positions=[(p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c,d)]
    return min(length,max(positions))-max(0,min(positions))>tolerance


def supporting_midlines(pair,lines):
    a,b=pair['axis']
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<1e-6:
        return ()
    supported=[]
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    for index,(c,d,layer) in enumerate(lines):
        if index in pair['faces']:
            continue
        other=math.hypot(d[0]-c[0],d[1]-c[1])
        if other<1e-6 or abs(ux*(d[1]-c[1])-uy*(d[0]-c[0]))/other>0.001:
            continue
        if max(abs((p[0]-a[0])*uy-(p[1]-a[1])*ux) for p in (c,d))>1.0/304.8:
            continue
        bounds=sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c,d))
        if min(length,bounds[1])-max(0,bounds[0])>=0.95*length:
            supported.append(index)
    return tuple(supported)


def covers_run(wide,narrow):
    a,b=wide
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<=1e-6:
        return False
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    positions=[(p[0]-a[0])*ux+(p[1]-a[1])*uy for p in narrow]
    tol=1.0/304.8
    return min(positions)>=-tol and max(positions)<=length+tol


def overlapping_bands(first,second,width_sum_mm):
    a,b=first
    c,d=second
    ux,uy=b[0]-a[0],b[1]-a[1]
    vx,vy=d[0]-c[0],d[1]-c[1]
    length=math.hypot(ux,uy)
    other=math.hypot(vx,vy)
    if not length or not other or abs(ux*vy-uy*vx)>0.001*length*other:
        return False
    half_sum=width_sum_mm/(2*304.8)
    return (max(abs((p[0]-a[0])*uy-(p[1]-a[1])*ux) for p in (c,d))/length
            < half_sum-1.0/304.8 and overlap_on_axis(first,second))


def matching_wall_type(width_mm, types, tolerance_mm=0.1):
    """Width-only suggestions; ties use stable names and remain user editable.

    types contains (unique_id, width_in_mm, display_name).
    """
    matches=[(abs(width_mm-w),label.lower(),uid) for uid,w,label in types
             if abs(width_mm-w)<=tolerance_mm+1e-6]
    return (min(matches)[2],len(matches)) if matches else (None,0)


def below_cutoff(width_mm, enabled, cutoff_mm):
    # Equality stays included; ignore floating point noise from DWG transforms.
    return bool(enabled) and round(width_mm, 6) < round(cutoff_mm, 6)


def short_face_cap(a,c,ux,uy,lo,hi,source):
    """A real CAD edge joins both faces at one end of their common length."""
    lateral=(c[1]-a[1])*ux-(c[0]-a[0])*uy
    tolerance=1./304.8
    for station in (lo,hi):
        x,y=a[0]+ux*station,a[1]+uy*station
        opposite=(x-uy*lateral,y+ux*lateral)
        for p,q,layer in source:
            if abs(p[2]-a[2])>tolerance or abs(q[2]-a[2])>tolerance: continue
            for start,end in ((p,q),(q,p)):
                if math.hypot(x-start[0],y-start[1])<=tolerance and math.hypot(opposite[0]-end[0],opposite[1]-end[1])<=tolerance:
                    return True
    return False


def is_end_cap(face,opposite,source):
    """Both ends turn into two transverse faces on the same side of a jamb."""
    a,b=face
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    side=1 if (opposite[1]-a[1])*ux-(opposite[0]-a[0])*uy>0 else -1
    def turns_at(end):
        for p,q,layer in source:
            for start,finish in ((p,q),(q,p)):
                if abs(start[2]-end[2])>1./304.8 or math.hypot(start[0]-end[0],start[1]-end[1])>1./304.8:
                    continue
                x,y=finish[0]-start[0],finish[1]-start[1]
                if side*(y*ux-x*uy)>=length-1./304.8 and abs(x*ux+y*uy)<1./304.8:
                    return True
        return False
    return turns_at(a) and turns_at(b)


def thickness_inventory(lines, min_mm=25, max_mm=600, min_overlap_mm=300, diagnostics=None,
                        min_shared_fraction=0.6,cross_layer_only=False,short_wall_faces=False,cap_lines=None,
                        supported_widths=()):
    """Inventory possible bands; this does not assert that a band is material.

    Each input is (start, end, layer). Retain face identities for ambiguity review
    after the user has mapped the thickness groups they actually want.
    """
    rows = {}
    def mark(i,j,reason):
        if diagnostics is not None:
            for index in (i,j):
                counts=diagnostics.setdefault(index,{})
                counts[reason]=counts.get(reason,0)+1
    if len(lines) > 2500:
        raise ValueError('Select fewer CAD layers: the scan is limited to 2500 straight segments.')
    for i, (a,b,layer_a) in enumerate(lines):
        dx,dy = b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        if length <= 1e-6:
            continue
        ux,uy=dx/length,dy/length
        for j in range(i+1,len(lines)):
            c,d,layer_b=lines[j]
            if cross_layer_only and layer_a==layer_b:
                continue
            vx,vy=d[0]-c[0],d[1]-c[1]
            other=math.hypot(vx,vy)
            if other <= 1e-6 or abs(ux*vy-uy*vx)/other > 0.001:
                continue
            if ux*vx+uy*vy < 0:
                c,d=d,c
                vx,vy=-vx,-vy
            lo=max(0.0,(c[0]-a[0])*ux+(c[1]-a[1])*uy)
            hi=min(length,(d[0]-a[0])*ux+(d[1]-a[1])*uy)
            overlap=hi-lo
            width=abs(((c[0]+d[0])/2-a[0])*uy-((c[1]+d[1])/2-a[1])*ux)*304.8
            # A complete short return can terminate at one face of a longer
            # wall. Two short end caps across a doorway are not wall faces.
            complete_short=(short_wall_faces and 1.0<overlap*304.8<min_overlap_mm
                            and min_mm-1e-6<=width<=max_mm+1e-6
                            and max(a[2],b[2],c[2],d[2])-min(a[2],b[2],c[2],d[2])<=1.0/304.8
                            and min(length,other)-overlap<=1.0/304.8
                            and (overlap*304.8>=width-1.0 or
                                 (max(length,other)*304.8>width+1.0 and
                                  short_face_cap(a,c,ux,uy,lo,hi,lines if cap_lines is None else cap_lines))))
            if complete_short and overlap*304.8<width-1.0:
                face,mate=((a,b),c) if length<=other else ((c,d),a)
                if is_end_cap(face,mate,lines if cap_lines is None else cap_lines):
                    mark(i,j,'wall end cap between perpendicular faces')
                    continue
            if (overlap*304.8 < min_overlap_mm and not complete_short) or overlap/min(length,other) < min_shared_fraction:
                if overlap>0:
                    mark(i,j,'parallel but insufficient shared length')
                continue
            if width < min_mm-1e-6 or width > max_mm+1e-6:
                mark(i,j,'parallel but spacing outside scan range')
                continue
            vx,vy=vx/other,vy/other
            ends=[]
            for t in (lo,hi):
                p=(a[0]+ux*t,a[1]+uy*t,a[2])
                q=(p[0]-c[0])*vx+(p[1]-c[1])*vy
                ends.append(((p[0]+c[0]+vx*q)/2,(p[1]+c[1]+vy*q)/2,(a[2]+c[2])/2))
            # Only collapse numerical noise. Distinct measured widths must not
            # share an averaged bucket across the user's exclusion cutoff.
            key=int(round(width*1000000))
            row=rows.setdefault(key,{'key':key,'widths':[],'pairs':[],'layers':set()})
            row['widths'].append(width)
            row['pairs'].append({'faces':(i,j),'axis':tuple(ends),
                                 'needs_width_evidence':complete_short and overlap*304.8<width-1.0})
            row['layers'].update((layer_a,layer_b))
    result=[]
    if sum(len(r['pairs']) for r in rows.values())>5000:
        raise ValueError('Too many competing face pairs. Select fewer source layers or a narrower spacing range.')
    # Do not introduce a new thickness solely by measuring the distance between
    # a jamb and another short cross-stroke. Use a measured wall or a loaded
    # wall type as corroboration when the overlap is shorter than the width.
    confirmed=list(supported_widths)+[k/1e6 for k,row in rows.items()
                                      if any(not p['needs_width_evidence'] for p in row['pairs'])]
    for key in sorted(rows):
        row=rows[key]
        row['width_mm']=sum(row.pop('widths'))/len(row['pairs'])
        supported=any(abs(w-row['width_mm'])<=0.1 for w in confirmed)
        retained=[]
        for pair in row['pairs']:
            if pair.pop('needs_width_evidence') and not supported:
                mark(pair['faces'][0],pair['faces'][1],'short end faces without a corroborating wall thickness')
                continue
            mark(pair['faces'][0],pair['faces'][1],'candidate')
            retained.append(pair)
        row['pairs']=retained
        if not retained: continue
        for pair in row['pairs']:
            pair['midline_faces']=supporting_midlines(pair,lines)
            pair['centerline_support']=bool(pair['midline_faces'])
        result.append(row)
    return result


def mapped_pairs(rows, choices, enabled=False, cutoff_mm=0, decisions=None):
    """None mappings and excluded widths never take part in tracing.

    Reuse on disjoint lengths is allowed. A drawn midline can support a full
    width over competing half-width interpretations. Other overlapping uses
    remain withheld; mapping alone is not proof of wall topology.
    """
    active=[r for r in rows if choices.get(r['key']) is not None
            and not below_cutoff(r['width_mm'],enabled,cutoff_mm)]
    entries=[(row,pair) for row in active for pair in row['pairs']]
    # An explicitly drawn longitudinal midline supports the full-width pair;
    # do not also interpret that midline as two half-width walls.
    superseded=set()
    for i,(row,pair) in enumerate(entries):
        for other,wide in entries:
            if (wide.get('centerline_support') and abs(other['width_mm']-2*row['width_mm'])<0.1
                    and set(pair['faces']).intersection(wide['faces'])
                    and set(pair['faces']).intersection(wide.get('midline_faces',()))
                    and covers_run(wide['axis'],pair['axis'])):
                superseded.add(i)
                break
    for row in active:
        row['resolved_alternatives']=sum(1 for i,(r,p) in enumerate(entries) if r is row and i in superseded)
    entries=[entry for i,entry in enumerate(entries) if i not in superseded]
    competing=set()
    for i,(row,pair) in enumerate(entries):
        for j in range(i+1,len(entries)):
            other,second=entries[j]
            if ((set(pair['faces']).intersection(second['faces'])
                    and overlap_on_axis(pair['axis'],second['axis']))
                    or overlapping_bands(pair['axis'],second['axis'],row['width_mm']+other['width_mm'])):
                competing.update((id(pair),id(second)))
                if decisions is not None:
                    for p,q in ((pair,second),(second,pair)):
                        reason='conflict with faces {}'.format(q['faces'])
                        decisions[id(p)]=(decisions.get(id(p),'')+'; '+reason).strip('; ')
    result=[]
    for row in active:
        pairs=[p for r,p in entries if r is row and id(p) not in competing]
        result.append((row,choices[row['key']],pairs,sum(1 for r,p in entries if r is row and id(p) in competing)))
    return result
