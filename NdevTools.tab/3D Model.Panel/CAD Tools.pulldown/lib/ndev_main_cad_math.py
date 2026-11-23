"""Independent CAD geometry helpers; lengths are in Revit internal feet.

Double-line projections adapted from Horizun CadTopologyRules.FindDoubleLines
(v4.0.0, Apache-2.0). No Horizun runtime code or assemblies are loaded.
"""
import math


def line_key(a, b, precision=5):
    return tuple(sorted((tuple(round(v, precision) for v in a),
                         tuple(round(v, precision) for v in b))))


def symbol_clusters(lines, radius, minimum_marks=2):
    """Midpoint clusters using distance-connected components (source reference:
    CadTopologyRules.ClusterPoints and FromPointClusters). Orientation is supplied
    separately: a cluster centre cannot establish a column's rotation.
    """
    mids = [tuple((a[k]+b[k])/2.0 for k in range(3)) for a, b in lines]
    used, clusters = set(), []
    for i in range(len(mids)):
        if i in used:
            continue
        members, queue = [], [i]
        used.add(i)
        while queue:
            current = queue.pop()
            members.append(current)
            for j in range(len(mids)):
                if j not in used and math.hypot(mids[current][0]-mids[j][0], mids[current][1]-mids[j][1]) <= radius:
                    used.add(j)
                    queue.append(j)
        if len(members) >= minimum_marks:
            center = tuple(sum(mids[j][k] for j in members)/len(members) for k in range(3))
            clusters.append((center, len(members)))
    return clusters


def paired_axes(lines, width, tolerance):
    """Pair parallel faces over their shared span, including unequal lengths.

    Ambiguous face assignments are left for review rather than silently merged.
    Returns axes and the count of unmatched/ambiguous source lines.
    """
    candidates = {}
    for i, (a, b) in enumerate(lines):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        if length <= tolerance:
            continue
        ux, uy = dx/length, dy/length
        for j in range(i+1, len(lines)):
            c, d = lines[j]
            vx, vy = d[0]-c[0], d[1]-c[1]
            other = math.hypot(vx, vy)
            if other <= tolerance or abs(ux*vy-uy*vx)/other > 0.001:
                continue
            if ux*vx+uy*vy < 0:
                c, d = d, c
            lo = max(0.0, (c[0]-a[0])*ux+(c[1]-a[1])*uy)
            hi = min(length, (d[0]-a[0])*ux+(d[1]-a[1])*uy)
            gap = abs(((c[0]+d[0])/2-a[0])*uy-((c[1]+d[1])/2-a[1])*ux)
            if hi-lo > tolerance and (hi-lo)/min(length, other) >= 0.6 and abs(gap-width) <= tolerance:
                vx, vy = vx/other, vy/other
                # Reversed endpoints above also reverse their direction.
                if ux*vx+uy*vy < 0:
                    vx, vy = -vx, -vy
                ends = []
                for t in (lo, hi):
                    at = (a[0]+ux*t, a[1]+uy*t, a[2])
                    along_b = (at[0]-c[0])*vx+(at[1]-c[1])*vy
                    bt = (c[0]+vx*along_b, c[1]+vy*along_b, c[2])
                    ends.append(tuple((at[k]+bt[k])/2.0 for k in range(3)))
                axis = tuple(ends)
                candidates.setdefault(i, []).append((j, axis))
                candidates.setdefault(j, []).append((i, axis))
    axes, used = [], set()
    for i, matches in candidates.items():
        if len(matches) != 1 or i in used:
            continue
        j, axis = matches[0]
        if len(candidates.get(j, [])) == 1:
            used.update((i, j))
            axes.append(axis)
    return axes, len(lines)-len(used)


def rectangle_center(points, tolerance):
    pts = list(points)
    if len(pts) == 5 and sum((pts[0][i]-pts[-1][i])**2 for i in range(3)) <= tolerance**2:
        pts.pop()
    if len(pts) != 4:
        return None
    edges = [tuple(pts[(j+1)%4][k]-pts[j][k] for k in range(3)) for j in range(4)]
    lengths = [math.sqrt(sum(v*v for v in e)) for e in edges]
    if min(lengths) <= tolerance:
        return None
    for j in range(4):
        if abs(sum(edges[j][k]*edges[(j+1)%4][k] for k in range(3))) > lengths[j]*lengths[(j+1)%4]*0.001:
            return None
    return tuple(sum(p[k] for p in pts)/4.0 for k in range(3)), math.atan2(edges[0][1], edges[0][0])


def closed_rectangles(lines):
    """Only isolated four-edge loops; branched outlines remain unmatched."""
    nodes, edges = {}, {}
    for a, b in lines:
        aa = tuple(round(v, 5) for v in a)
        bb = tuple(round(v, 5) for v in b)
        if aa == bb:
            continue
        nodes.setdefault(aa, set()).add(bb)
        nodes.setdefault(bb, set()).add(aa)
        edges[aa] = a
        edges[bb] = b
    visited, result = set(), []
    for start in nodes:
        if start in visited:
            continue
        component, queue = set(), [start]
        while queue:
            current = queue.pop()
            if current in component:
                continue
            component.add(current)
            queue.extend(nodes[current]-component)
        visited.update(component)
        if len(component) != 4 or any(len(nodes[n]) != 2 for n in component):
            continue
        ring, previous, current = [], None, start
        for unused in range(4):
            ring.append(edges[current])
            next_node = next(n for n in nodes[current] if n != previous)
            previous, current = current, next_node
        shape = rectangle_center(ring, 0.003)
        if shape:
            result.append(shape)
    return result
