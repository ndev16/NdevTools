"""Resolve parallel mapped wall footprints, widest Revit type first. Units: feet."""
import math
from ndev_main_cad_mapping_math import below_cutoff

TOL=1.0/304.8

def wall_type_width(symbol,fallback=0.0):
    """Use the CAD width for types which have no single nominal width."""
    try:
        width=float(symbol.Width)
    except (AttributeError,ValueError):
        return fallback
    except Exception:
        # Some system types expose Width but Revit cannot evaluate it.
        return fallback
    return width if width>0 else fallback

def run_key(p):
    return tuple(p['faces']),tuple(tuple(point) for point in p['axis'])


def clipped(axis,lo,hi):
    a,b=axis
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    return tuple(tuple(a[k]+(b[k]-a[k])*t/length for k in range(3)) for t in (lo,hi))


def intersection(axis,other,width,total):
    a,b=axis
    c,d=other
    x,y=b[0]-a[0],b[1]-a[1]
    l=math.hypot(x,y)
    if l<=TOL or math.hypot(d[0]-c[0],d[1]-c[1])<=TOL:
        return None
    u,v=x/l,y/l
    if abs(u*(d[1]-c[1])-v*(d[0]-c[0]))>0.001*math.hypot(d[0]-c[0],d[1]-c[1]):
        return None
    # Compute lateral offset at both ends of the common span (not outside it).
    t=[(p[0]-a[0])*u+(p[1]-a[1])*v for p in other]
    lo,hi=max(0,min(t)),min(l,max(t))
    if hi-lo<=TOL:
        return None
    n=[(p[0]-a[0])*v-(p[1]-a[1])*u for p in other]
    slope=(n[1]-n[0])/(t[1]-t[0])
    start=n[0]-t[0]*slope
    radius=(width+total)/609.6-1e-7
    if abs(slope)<1e-12:
        return (lo,hi) if abs(start)<radius else None
    bounds=sorted((offset-start)/slope for offset in (-radius,radius))
    lo,hi=max(lo,bounds[0]),min(hi,bounds[1])
    return (lo,hi) if hi-lo>TOL else None


def partition(axis,cuts):
    a,b=axis
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    points=sorted(set([0,length]+[t for interval,why in cuts for t in interval]))
    spans=[]
    for lo,hi in zip(points,points[1:]):
        mid=(lo+hi)*0.5
        why=next((msg for (start,end),msg in cuts if start<=mid<=end),'eligible')
        if spans and spans[-1][2]==why:
            spans[-1]=(spans[-1][0],hi,why)
        else:
            spans.append((lo,hi,why))
    return [(axis if lo==0 and hi==length else clipped(axis,lo,hi),why) for lo,hi,why in spans]


def grid_layer(name):
    import re
    return any(re.match(r'^(?:grids?|gridlines?)(?:[0-9]+)?$',part)
               for part in re.split(r'[^a-z0-9]+',name.lower()))


def add_perimeter_pairs(merged, lines, diagnostics, low, high, overlap, selected=None,known_widths=()):
    """Fill uncovered face intervals from the nearest parallel non-grid line on each side."""
    from ndev_main_cad_mapping_math import thickness_inventory
    selected=set(selected if selected is not None else [lines[0][2]] if lines else [])
    confirmed=list(known_widths)+[r['width_mm'] for r in merged.values()]
    same_layer={}
    for row in merged.values():
        for pair in row['pairs']:
            i,j=pair['faces']
            same_layer.setdefault(i,[]).append(j)
            same_layer.setdefault(j,[]).append(i)
    for i,(a,b,layer) in enumerate(lines):
        length=math.hypot(b[0]-a[0],b[1]-a[1])
        if layer not in selected or grid_layer(layer) or length<=TOL:
            continue
        ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
        def stations(other):
            c,d,k=lines[other]
            left,right=sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c,d))
            side=1 if (c[1]-a[1])*ux-(c[0]-a[0])*uy>0 else -1
            return side,max(0,left),min(length,right)
        used={1:[], -1:[]}
        for j in same_layer.get(i,[]):
            side,left,right=stations(j)
            used[side].append((left,right))
        choices=[]
        radius=high/304.8
        for j,(c,d,other) in enumerate(lines):
            if other==layer or grid_layer(other):
                continue
            if max(c[0],d[0])<min(a[0],b[0])-radius or min(c[0],d[0])>max(a[0],b[0])+radius or max(c[1],d[1])<min(a[1],b[1])-radius or min(c[1],d[1])>max(a[1],b[1])+radius:
                continue
            if max(a[2],b[2],c[2],d[2])-min(a[2],b[2],c[2],d[2])>TOL:
                continue
            for measured in thickness_inventory([lines[i],lines[j]],low,high,overlap,min_shared_fraction=0,short_wall_faces=True,cap_lines=lines,supported_widths=confirmed):
                choices.append((measured['width_mm'],j,measured['pairs'][0]))
        for width,j,pair in sorted(choices,key=lambda item:(item[0],item[1])):
            side,left,right=stations(j)
            axis=pair['axis']
            cuts=[((max(left,start)-left,min(right,end)-left),'nearer face')
                  for start,end in used[side] if min(right,end)>max(left,start)]
            used[side].append((left,right))
            nearby=[k for k in merged if abs(k*1e-6-width)<=0.1]
            key=min(nearby,key=lambda k:abs(k*1e-6-width)) if nearby else int(round(width,1)*1e6)
            target=merged.get(key)
            if target:
                for old in target['pairs']:
                    interval=intersection(axis,old['axis'],1,1)
                    if interval:
                        cuts.append((interval,'already measured'))
            for part,reason in partition(axis,cuts):
                c,d=part
                part_length=math.hypot(d[0]-c[0],d[1]-c[1])
                # The short-face exception only applies to the measured pair,
                # not to a short sliver left after a nearer face won.
                if reason!='eligible' or (part_length*304.8+1e-5<overlap and part_length<right-left-TOL):
                    continue
                if target is None:
                    target=merged.setdefault(key,dict(key=key,width_mm=width,pairs=[],layers=set()))
                target['pairs'].append(dict(pair,axis=part,faces=(i,j),perimeter=True,guide=j))
                target['layers'].update((layer,lines[j][2]))
                for face in (i,j):
                    counts=diagnostics.setdefault(face,{})
                    counts['candidate']=counts.get('candidate',0)+1
    for row in merged.values():
        connect_measured_runs(row,lines,merged.values())


def connect_measured_runs(row,lines,rows=()):
    from ndev_main_cad_perimeter import continuous_perimeter
    from ndev_main_cad_openings import attach_openings,opening_spans,window_spans
    gaps=attach_openings(row,lines,rows)
    pairs=row['pairs']
    width=row['width_mm']/304.8
    for i,first in enumerate(pairs):
        a,b=first['axis']
        length=math.hypot(b[0]-a[0],b[1]-a[1])
        if length<=TOL: continue
        ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
        for other in pairs[i+1:]:
            points=other['axis']
            if any(abs((p[0]-a[0])*uy-(p[1]-a[1])*ux)>TOL for p in points):
                continue
            lo,hi=sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in points)
            gap=max(lo-length,-hi)
            shared=set(first['faces']).intersection(other['faces'])
            if gap < -TOL or (gap>width+TOL and not shared):
                continue
            first['perimeter']=other['perimeter']=True
            if shared:
                first.setdefault('guide',min(shared))
    if any(p.get('perimeter') for p in pairs):
        def changes_width(gap):
            length=math.hypot(gap[1][0]-gap[0][0],gap[1][1]-gap[0][1])
            for other in rows:
                if abs(other['width_mm']-row['width_mm'])<=0.1: continue
                for candidate in other['pairs']:
                    axis=candidate['axis']
                    span=intersection(gap,axis,row['width_mm'],other['width_mm'])
                    if not span or span[1]-span[0]<length-2*TOL: continue
                    # A distinct thickness that starts and ends at this gap is a plan transition.
                    if abs(math.hypot(axis[1][0]-axis[0][0],axis[1][1]-axis[0][1])-length)<=2*TOL:
                        return True
            return False
        row['pairs']=continuous_perimeter(pairs,lines,width,changes_width)
    for pair in row['pairs']:
        axis=pair['axis']
        spans=opening_spans(axis,width,lines)
        # A jamb-to-jamb gap is known from the two adjacent source pieces.
        for gap in gaps:
            interval=intersection(axis,gap,1,1)
            if interval:
                spans.append(clipped(axis,*interval))
        pair['openings']=[span for span in spans if all(
            min(math.hypot(q[0]-end[0],q[1]-end[1]) for end in axis)>TOL for q in span)]
        windows=window_spans(axis,width,lines)
        pair['window_openings']=windows
        # Glass in a gap marks a window, not a second floor-height cut.
        pair['openings']=[door for door in pair['openings']
                          if not any(intersection(door,w,1,1) for w in windows)]



def join_wall_axes(accepted):
    """Extend an end that reaches a neighbour's face to that wall's axis."""
    runs=[(pair,wall_type_width(symbol,row['width_mm']/304.8)) for row,symbol,pairs,held in accepted for pair in pairs]
    for pair,width in runs:
        a,b=pair['axis']
        length=math.hypot(b[0]-a[0],b[1]-a[1])
        if length<=TOL:
            continue
        ends=[]
        for end,origin in enumerate((a,b)):
            sign=1 if end else -1
            ux,uy=sign*(b[0]-a[0])/length,sign*(b[1]-a[1])/length
            hits=[]
            for other,w in runs:
                if other is pair: continue
                c,d=other['axis']
                vx,vy=d[0]-c[0],d[1]-c[1]
                size=math.hypot(vx,vy)
                if size<=TOL: continue
                vx,vy=vx/size,vy/size
                det=ux*vy-uy*vx
                if abs(det)<0.05: continue
                dx,dy=c[0]-origin[0],c[1]-origin[1]
                reach=(dx*vy-dy*vx)/det
                along=(dx*uy-dy*ux)/det
                if -TOL<=reach<=w/(2*abs(det))+TOL and -width/2-TOL<=along<=size+width/2+TOL:
                    hits.append(max(0,reach))
            travel=min(hits) if hits else 0
            ends.append((origin[0]+travel*ux,origin[1]+travel*uy,origin[2]))
        pair['join_axis']=tuple(ends)

    # A corner join must not put back a stretch which wall_plan already
    # assigned to a parallel wall. Keep the original endpoint in that case.
    blocked=set()
    for i,(first,w) in enumerate(runs):
        for j in range(i):
            second,v=runs[j]
            if not intersection(first['join_axis'],second['join_axis'],w*304.8,v*304.8):
                continue
            for current,width,other,other_width in ((first,w,second,v),(second,v,first,w)):
                for end in (0,1):
                    extension=(current['axis'][end],current['join_axis'][end])
                    if intersection(extension,other['join_axis'],width*304.8,other_width*304.8):
                        blocked.add((id(current),end))
    for pair,width in runs:
        pair['join_axis']=tuple(pair['axis'][end] if (id(pair),end) in blocked else pair['join_axis'][end]
                                for end in (0,1))

def wall_plan(rows,choices,exclude=False,cutoff_mm=0,details=None,min_run=TOL):
    """Details contains a partition of every input candidate, including skips."""
    if details is None:
        details=[]
    active=[]
    by_width={}
    def record(row,p,axis,why):
        part=dict(p,axis=axis)
        details.append((row,part,why))
        return part
    for row in rows:
        symbol=choices.get(row['key'])
        if symbol is None or below_cutoff(row['width_mm'],exclude,cutoff_mm):
            why='below cutoff' if below_cutoff(row['width_mm'],exclude,cutoff_mm) else 'no mapping'
            for p in row['pairs']:
                record(row,p,p['axis'],why)
            continue
        traced=[]
        active.append([row,symbol,traced,0])
        width=wall_type_width(symbol,row['width_mm']/304.8)*304.8
        by_width.setdefault(round(width,6),[]).extend((active[-1],p) for p in row['pairs'])
    occupied=[]
    for width in sorted(by_width,reverse=True):
        batch=by_width[width]
        survivors=[]
        for entry,p in batch:
            cuts=[]
            for axis,w,faces in occupied:
                interval=intersection(p['axis'],axis,width,w)
                if interval:
                    cuts.append((interval,'thicker {:.2f} in wall takes priority (faces {})'.format(w/25.4,faces)))
            for axis,why in partition(p['axis'],cuts):
                if why=='eligible':
                    survivors.append((entry,dict(p,axis=axis)))
                else:
                    record(entry[0],p,axis,why)
        held=set()
        for i,(entry,p) in enumerate(survivors):
            cuts=[]
            for j,(other,q) in enumerate(survivors):
                if i==j:
                    continue
                interval=intersection(p['axis'],q['axis'],width,width)
                if interval:
                    cuts.append((interval,'equal-width conflict with faces {}'.format(q['faces'])))
            for axis,why in partition(p['axis'],cuts):
                a,b=axis
                if why=='eligible' and math.hypot(b[0]-a[0],b[1]-a[1])<=min_run:
                    why='remainder below minimum Revit curve length'
                part=record(entry[0],p,axis,why)
                if why=='eligible':
                    entry[2].append(part)
                if why.startswith('equal-width') and (id(entry),p['faces']) not in held:
                    held.add((id(entry),p['faces']))
                    entry[3]+=1
                if why=='eligible' or why.startswith('equal-width'):
                    occupied.append((axis,width,p['faces']))
    return active
