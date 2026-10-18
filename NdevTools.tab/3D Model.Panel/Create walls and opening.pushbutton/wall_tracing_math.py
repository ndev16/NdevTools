# -*- coding: utf-8 -*-
"""Pure numerical rules; lengths are Revit internal feet."""
TOL = 1.0e-4


def combine_opening_bounds(bounds_list, maximum_gap):
    """Group along-wall intervals transitively; return envelope and member indexes.

    Call separately for each wall. Horizontal clear gap is clamped to zero for
    overlapping intervals; sill/head differences do not prevent combination.
    """
    import math
    if math.isnan(maximum_gap) or math.isinf(maximum_gap) or maximum_gap < 0:
        raise ValueError('Maximum Gap must be a finite, non-negative length.')
    groups = []
    for index, bounds in sorted(enumerate(bounds_list), key=lambda item: (item[1][0], item[1][1])):
        left, right, bottom, top = bounds
        if right <= left or top <= bottom:
            raise ValueError('Cannot combine an opening with invalid extents.')
        if groups and max(0.0, left-groups[-1][0][1]) <= maximum_gap:
            previous, members = groups[-1]
            groups[-1] = ((min(previous[0],left), max(previous[1],right),
                           min(previous[2],bottom), max(previous[3],top)), members+[index])
        else:
            groups.append((tuple(bounds), [index]))
    return groups


def suggest_wall_type(thickness, candidates):
    """Return a width-based UI suggestion, not a material/structural equivalence.

    Candidates are (index, width). Stable ordering breaks equal-width ties;
    the user reviews the actual type in the mapping dropdown before creation.
    """
    valid = [(index, width) for index, width in candidates if width > TOL]
    if thickness <= TOL or not valid:
        return None, False
    index, width = min(valid, key=lambda item: (abs(item[1]-thickness), item[0]))
    return index, abs(width-thickness) <= TOL


def structure_layer(layers):
    """(width, is_structure) in exterior-to-interior order. Never use names."""
    candidates = [i for i, layer in enumerate(layers) if layer[1] and layer[0] > TOL]
    if not candidates:
        raise ValueError('No positive-width Structure [1] layer.')
    index = max(candidates, key=lambda i: layers[i][0])
    total = sum(layer[0] for layer in layers)
    center = total / 2.0 - sum(layers[i][0] for i in range(index)) - layers[index][0] / 2.0
    return index, layers[index][0], center


def simplify_profile(points, tolerance=TOL):
    """Remove tiny edges and collinear vertices within a fixed distance budget."""
    import math
    points = list(points)
    if any(not all(not math.isnan(v) and not math.isinf(v) for v in p) for p in points):
        raise ValueError('Cut profile contains non-finite coordinates.')
    changed = True
    while changed and len(points) > 3:
        changed = False
        for i, b in enumerate(points):
            a, c = points[i-1], points[(i+1) % len(points)]
            dx, dy = c[0]-a[0], c[1]-a[1]
            length2 = dx*dx+dy*dy
            if length2 <= tolerance*tolerance:
                continue
            t = ((b[0]-a[0])*dx+(b[1]-a[1])*dy)/length2
            distance = abs(dx*(b[1]-a[1])-dy*(b[0]-a[0]))/math.sqrt(length2)
            if 0 <= t <= 1 and distance <= tolerance:
                points.pop(i)
                changed = True
                break
    return points


def rectangle_bounds(points, tolerance=TOL):
    """Validate the entire closed boundary; no edge/corner-count requirement."""
    import math
    points = list(points)
    if len(points) < 3 or any(not all(not math.isnan(v) and not math.isinf(v) for v in p) for p in points):
        raise ValueError('Empty or invalid cut boundary.')
    xs,zs = zip(*points)
    left,right,bottom,top = min(xs),max(xs),min(zs),max(zs)
    if right-left <= tolerance or top-bottom <= tolerance:
        raise ValueError('Cut has negligible width or height.')
    perimeter,area2 = 0.0,0.0
    for i,(x,z) in enumerate(points):
        u,v = points[(i+1)%len(points)]
        length = math.hypot(u-x,v-z)
        on_side = (max(abs(x-left),abs(u-left)) <= tolerance or
                   max(abs(x-right),abs(u-right)) <= tolerance or
                   max(abs(z-bottom),abs(v-bottom)) <= tolerance or
                   max(abs(z-top),abs(v-top)) <= tolerance)
        if not on_side and length > tolerance:
            raise ValueError('Boundary segment leaves all four rectangle sides.')
        perimeter += length
        area2 += (x-left)*(v-bottom)-(u-left)*(z-bottom)
    expected = 2*(right-left+top-bottom)
    if abs(perimeter-expected) > 8*tolerance or abs(abs(area2)/2-(right-left)*(top-bottom)) > expected*tolerance:
        raise ValueError('Boundary has missing sides, backtracking, or non-rectangular area.')
    return left,right,bottom,top


def point_in_polygon(point, polygon):
    x,z = point
    inside = False
    for i,(a,b) in enumerate(polygon):
        c,d = polygon[(i+1)%len(polygon)]
        if (b > z) != (d > z) and x < (c-a)*(z-b)/(d-b)+a:
            inside = not inside
    return inside


def clip_polygon(points, window):
    """Clip a face polygon to an insert search window, not to a proposed opening."""
    result=list(points)
    for axis,bound,keep_greater in ((0,window[0],True),(0,window[1],False),
                                  (1,window[2],True),(1,window[3],False)):
        output=[]
        for i,b in enumerate(result):
            a=result[i-1]
            ina=a[axis]>=bound if keep_greater else a[axis]<=bound
            inb=b[axis]>=bound if keep_greater else b[axis]<=bound
            if ina != inb:
                fraction=(bound-a[axis])/(b[axis]-a[axis])
                output.append((a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1])))
            if inb:
                output.append(b)
        result=output
        if not result:
            break
    return result


def cut_match_score(cut, insert):
    """Overlap, center distance and width/height similarity; no orientation gate."""
    import math
    cw,ch,cc=rectangle_metrics(cut)
    iw,ih,ic=rectangle_metrics(insert)
    if min(cw,ch,iw,ih)<=TOL:
        return -1.0,0.0,0.0
    x=max(0,min(cut[1],insert[1])-max(cut[0],insert[0]))/min(cw,iw)
    z=max(0,min(cut[3],insert[3])-max(cut[2],insert[2]))/min(ch,ih)
    if min(x,z)<=0:
        return -1.0,x,z
    distance=math.hypot(cc[0]-ic[0],cc[1]-ic[1])/max(math.hypot(iw,ih),TOL)
    return 2*x+2*z+min(cw,iw)/max(cw,iw)+min(ch,ih)/max(ch,ih)-distance,x,z


def boundary_notches(face_regions, envelope, tolerance=TOL, include_inner=False):
    """Exact orthogonal cell decomposition of the union of cut side faces.

    Each region is [outer_loop, hole_loop, ...]. Only missing components touching
    the expected wall envelope are returned. Diagonal/curved boundaries do not
    receive a bounding-box approximation.
    """
    left,right,bottom,top = envelope
    points = [p for region in face_regions for loop in region for p in loop]
    for region in face_regions:
        for loop in region:
            for i,(x,z) in enumerate(loop):
                u,v = loop[(i+1)%len(loop)]
                if abs(x-u)>tolerance and abs(z-v)>tolerance:
                    raise ValueError('Outer-notch scan has a diagonal/curved boundary.')
    def coordinates(values):
        out=[]
        for v in sorted(values):
            if not out or v-out[-1]>tolerance:
                out.append(v)
        return out
    xs=coordinates([left,right]+[max(left,min(right,p[0])) for p in points])
    zs=coordinates([bottom,top]+[max(bottom,min(top,p[1])) for p in points])
    if (len(xs)-1)*(len(zs)-1)>20000:
        raise ValueError('Wall-face grid exceeds safe complexity limit.')
    missing=set()
    for i in range(len(xs)-1):
        for j in range(len(zs)-1):
            mid=((xs[i]+xs[i+1])/2,(zs[j]+zs[j+1])/2)
            occupied=any(point_in_polygon(mid,r[0]) and not any(point_in_polygon(mid,h) for h in r[1:]) for r in face_regions)
            if not occupied:
                missing.add((i,j))
    results=[]
    while missing:
        seed=missing.pop(); component={seed}; queue=[seed]
        while queue:
            i,j=queue.pop()
            for neighbor in ((i-1,j),(i+1,j),(i,j-1),(i,j+1)):
                if neighbor in missing:
                    missing.remove(neighbor); component.add(neighbor); queue.append(neighbor)
        if not include_inner and not any(i in (0,len(xs)-2) or j in (0,len(zs)-2) for i,j in component):
            continue
        min_i,max_i=min(i for i,j in component),max(i for i,j in component)
        min_j,max_j=min(j for i,j in component),max(j for i,j in component)
        bounds=(xs[min_i],xs[max_i+1],zs[min_j],zs[max_j+1])
        rectangular=len(component)==(max_i-min_i+1)*(max_j-min_j+1)
        results.append((bounds,rectangular))
    return results


def rectangle_metrics(bounds):
    left,right,bottom,top = bounds
    return right-left, top-bottom, ((left+right)/2.0,(bottom+top)/2.0)


def opening_offsets(bottom, top, host_bottom):
    if top - bottom <= TOL:
        raise ValueError('Opening top must be above bottom.')
    return bottom-host_bottom, top-host_bottom
