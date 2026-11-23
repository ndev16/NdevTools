"""Recognize wall opening symbols in plan, in Revit internal feet."""
import math

TOL=1.0/304.8
# A bare gap has no symbol giving its purpose. Infer ordinary single/double
# doorways only. Jambs or a drawn X can identify a wider opening.
BARE_DOOR_LIMIT=8.0


def window_spans(axis,width,lines,allow_at_ends=False):
    """Localized parallel marker(s) strictly between the two wall faces."""
    from ndev_main_cad_wall_plan import grid_layer
    a,b=axis
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<=TOL: return []
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    intervals=[]
    for c,d,layer in lines:
        if grid_layer(layer) or max(abs(c[2]-a[2]),abs(d[2]-a[2]))>TOL: continue
        side=[(p[1]-a[1])*ux-(p[0]-a[0])*uy for p in (c,d)]
        if max(abs(v) for v in side)>=width/2.-TOL: continue
        lo,hi=sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c,d))
        if hi-lo<=TOL or abs(side[0]-side[1])>0.001*(hi-lo): continue
        if lo < -TOL or hi>length+TOL: continue
        if not allow_at_ends and (lo<=TOL or hi>=length-TOL): continue
        intervals.append((max(lo,0.),min(hi,length)))
    merged=[]
    for lo,hi in sorted(intervals):
        if merged and lo<=merged[-1][1]+TOL: merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
        else: merged.append((lo,hi))
    def point(t): return (a[0]+ux*t,a[1]+uy*t,a[2])
    return [(point(lo),point(hi)) for lo,hi in merged]


def faces_stop_at(pair,point,lines):
    """Both actual source faces terminate at this jamb station."""
    a,b=pair['axis']
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<=TOL or len(pair['faces'])!=2: return False
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    return all(min(abs((p[0]-point[0])*ux+(p[1]-point[1])*uy)
                   for p in lines[index][:2])<=TOL for index in pair['faces'])

def opening_spans(axis,width,lines):
    from ndev_main_cad_wall_plan import grid_layer
    a,b=axis
    length=math.hypot(b[0]-a[0],b[1]-a[1])
    if length<=TOL:
        return []
    ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
    diagonals={}
    jambs=set()
    for c,d,layer in lines:
        if grid_layer(layer) or max(abs(c[2]-a[2]),abs(d[2]-a[2]))>TOL: continue
        points=sorted(((p[0]-a[0])*ux+(p[1]-a[1])*uy,
                       (p[1]-a[1])*ux-(p[0]-a[0])*uy) for p in (c,d))
        (lo,v),(hi,w)=points
        if lo<-TOL or hi>length+TOL or v*w>=0:
            continue
        if max(abs(abs(v)-width/2),abs(abs(w)-width/2))>TOL:
            continue
        if hi-lo<=TOL:
            jambs.add(round((lo+hi)/2,4))
        else:
            diagonals.setdefault((round(lo,4),round(hi,4)),set()).add(v>0)
    spans=[s for s,signs in diagonals.items() if len(signs)==2]
    # The supplied axis can itself be the missing stretch between two wall runs.
    if any(abs(j)<=TOL for j in jambs) and any(abs(j-length)<=TOL for j in jambs):
        spans.append((0,length))
    def pt(t):
        return (a[0]+ux*t,a[1]+uy*t,a[2])
    return [(pt(max(0,lo)),pt(min(length,hi))) for lo,hi in sorted(set(spans))]


def attach_openings(row,lines,rows):
    from ndev_main_cad_wall_plan import intersection,clipped
    width=row['width_mm']/304.8
    parts=list(row['pairs'])
    bridges=[]
    for i,first in enumerate(parts):
        axis=first['axis']
        for second in parts[i+1:]:
            other=second['axis']
            if intersection(axis,other,1,1):
                continue
            a,b=axis
            length=math.hypot(b[0]-a[0],b[1]-a[1])
            if length<=TOL: continue
            ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
            if any(abs((p[0]-a[0])*uy-(p[1]-a[1])*ux)>TOL for p in other): continue
            stations=sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in other)
            lo,hi=(length,stations[0]) if stations[0]>length else (stations[1],0)
            if hi-lo<=TOL: continue
            gap=clipped(axis,lo,hi)
            # A gap must be between consecutive runs, in the same wall band.
            glass=window_spans(gap,width,lines,allow_at_ends=True)
            glazed=any(math.hypot(d[0]-c[0],d[1]-c[1])>=hi-lo-2*TOL for c,d in glass)
            def blocks(other_row,p):
                if p is first or p is second or not intersection(gap,p['axis'],1,1): return False
                if not glazed or other_row['width_mm']>=row['width_mm']-0.1: return True
                # Two glazing strokes can themselves be measured as a narrow
                # pair. Both must lie entirely inside this gap and wall band.
                for index in p['faces']:
                    for point in lines[index][:2]:
                        station=(point[0]-a[0])*ux+(point[1]-a[1])*uy
                        lateral=(point[1]-a[1])*ux-(point[0]-a[0])*uy
                        if not (lo-TOL<=station<=hi+TOL and abs(lateral)<width/2-TOL):
                            return True
                return False
            if any(blocks(other_row,p) for other_row in rows for p in other_row['pairs']):
                continue
            spans=opening_spans(gap,width,lines)
            marked=any(math.hypot(d[0]-c[0],d[1]-c[1])>=hi-lo-2*TOL for c,d in spans)
            if not marked:
                p,q=(gap if stations[0]>length else gap[::-1])
                if ((not glazed and hi-lo>BARE_DOOR_LIMIT) or not faces_stop_at(first,p,lines)
                        or not faces_stop_at(second,q,lines)):
                    continue
            if abs(axis[0][2]-other[0][2])>TOL:
                continue
            first['perimeter']=second['perimeter']=True
            bridges.append(dict(axis=gap,faces=tuple(sorted(set(first['faces']+second['faces']))),
                                perimeter=True,opening_bridge=True,midline_faces=()))
    row['pairs'].extend(bridges)
    return [p['axis'] for p in bridges]
