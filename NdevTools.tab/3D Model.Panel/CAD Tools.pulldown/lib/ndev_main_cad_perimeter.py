"""Connect measured straight wall axes along a CAD perimeter."""
import math

TOL=1/304.8


def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def direction(axis):
    a,b=axis
    length=distance(a,b)
    return ((b[0]-a[0])/length,(b[1]-a[1])/length)


def along(origin,u,p):
    return (p[0]-origin[0])*u[0]+(p[1]-origin[1])*u[1]


def offset(origin,u,t):
    return (origin[0]+u[0]*t,origin[1]+u[1]*t,origin[2])


def cross(u,v):
    return u[0]*v[1]-u[1]*v[0]


def continuous_perimeter(pairs,lines,width,changes_width=None):
    # width is in feet. Only seed chains from a measured wall/outline pair.
    chains=[dict(p,axis=list(p['axis']),parts=[p]) for p in pairs]
    def merge(first,second):
        a,b=first['axis']
        u=direction((a,b))
        if any(abs(cross(u,(p[0]-a[0],p[1]-a[1])))>TOL for p in second['axis']):
            return False
        lo,hi=sorted(along(a,u,p) for p in second['axis'])
        length=distance(a,b)
        shared=set(first['faces']).intersection(second['faces'])
        outline=any(p.get('guide') in shared for p in first['parts']+second['parts'])
        if max(lo-length,-hi)>width+TOL and not outline:
            return False
        gap=(length,lo) if lo>length else (hi,0)
        if gap[1]-gap[0]>TOL and changes_width and changes_width(tuple(offset(a,u,t) for t in gap)):
            return False
        first['axis']=[offset(a,u,min(0,lo)),offset(a,u,max(length,hi))]
        first['faces']=tuple(sorted(set(first['faces']).union(second['faces'])))
        first['parts'].extend(second['parts'])
        first['perimeter']=True
        return True
    changed=True
    while changed:
        changed=False
        for first in list(chains):
            if first not in chains or not first.get('perimeter'):
                continue
            for second in list(chains):
                if first is not second and merge(first,second):
                    chains.remove(second)
                    changed=True

    # Pair unique nearby endpoints. At a direction change use the intersection
    # of the axes. For a lateral step, use a short perpendicular return.
    options={}
    for i,first in enumerate(chains):
        for j in range(i+1,len(chains)):
            second=chains[j]
            for n,p in enumerate(first['axis']):
                for m,q in enumerate(second['axis']):
                    gap=distance(p,q)
                    if gap>2.25*width:
                        continue
                    u=direction(first['axis']); v=direction(second['axis'])
                    det=cross(u,v)
                    if abs(det)>0.001:
                        joint=offset(p,u,cross((q[0]-p[0],q[1]-p[1]),v)/det)
                        if max(distance(p,joint),distance(q,joint))>2.25*width:
                            continue
                        ends=(joint,joint)
                    else:
                        # Facing ends on parallel, offset runs.
                        t=along(p,u,q)
                        if (1 if n else -1)*t < -TOL or (1 if m else -1)*along(q,v,p)<-TOL:
                            continue
                        if gap>TOL and changes_width and changes_width((p,q)):
                            continue
                        ends=(offset(p,u,t/2),offset(q,u,-t/2))
                    if any(distance(ch['axis'][1-e],end)<width*0.05 for ch,e,end in
                           ((first,n,ends[0]),(second,m,ends[1]))):
                        continue
                    options.setdefault((i,n),[]).append((gap,(j,m),ends))
                    options.setdefault((j,m),[]).append((gap,(i,n),ends[::-1]))
    links=[]
    for end,candidates in options.items():
        candidates.sort(key=lambda x:x[0])
    for end,candidates in options.items():
        gap,other,ends=candidates[0]
        if end>=other or options[other][0][1]!=end:
            continue
        if any(len(options[k])>1 and options[k][1][0]-options[k][0][0]<TOL for k in (end,other)):
            continue
        links.append((end,other,ends))
    active=set(i for i,p in enumerate(chains) if p.get('perimeter'))
    while True:
        before=len(active)
        for (i,n),(j,m),ends in links:
            if i in active or j in active:
                active.update((i,j))
        if len(active)==before: break
    returns=[]
    for (i,n),(j,m),ends in links:
        if i not in active: continue
        chains[i]['axis'][n],chains[j]['axis'][m]=ends
        if distance(*ends)>TOL:
            faces=tuple(sorted(set(chains[i]['faces']).union(chains[j]['faces'])))
            returns.append(dict(axis=ends,faces=faces,perimeter=True,previous_axes=()))
    for i in active:
        chains[i]['perimeter']=True
    # Connected wall-only pieces can belong to the same perimeter side too.
    for first in list(chains):
        if first not in chains or not first.get('perimeter'): continue
        for second in list(chains):
            if second is not first and second.get('perimeter') and merge(first,second):
                chains.remove(second)
    for p in chains:
        p['axis']=tuple(p['axis'])
        parts=p.pop('parts')
        if p.get('perimeter'):
            p['previous_axes']=tuple(q['axis'] for q in parts)
    return chains+returns
