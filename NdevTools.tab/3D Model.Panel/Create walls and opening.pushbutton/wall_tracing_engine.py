# -*- coding: utf-8 -*-
"""Read-only linked-model analysis and isolated host-model creation."""
import clr
import io
import math
import os
import tempfile
import traceback
import uuid
from pyrevit import DB, forms
from Autodesk.Revit.Exceptions import RegenerationFailedException
from wall_tracing_math import TOL, structure_layer, rectangle_bounds, opening_offsets, combine_opening_bounds


def key(element_id):
    return str(element_id.Value if hasattr(element_id, 'Value') else element_id.IntegerValue)


def name(element):
    p = element.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    return (p.AsString() if p else element.Name) or key(element.Id)


def param(element, built_in):
    p = element.get_Parameter(getattr(DB.BuiltInParameter, built_in))
    if p is None:
        raise ValueError('Required parameter is unavailable: ' + built_in)
    return p


def set_param(element, built_in, value):
    p = param(element, built_in)
    # Parameter.Set can return False when the requested value is unchanged.
    if p.StorageType == DB.StorageType.ElementId and p.AsElementId() == value:
        return
    if p.StorageType == DB.StorageType.Integer and p.AsInteger() == value:
        return
    if p.StorageType == DB.StorageType.Double and abs(p.AsDouble()-value) < TOL:
        return
    if p.IsReadOnly or not p.Set(value):
        raise ValueError('Cannot set ' + built_in)


def levels(document):
    return sorted(DB.FilteredElementCollector(document).OfClass(DB.Level), key=lambda l: l.ProjectElevation)


def host_types(document):
    return sorted([t for t in DB.FilteredElementCollector(document).OfClass(DB.WallType)
                   if t.Kind == DB.WallKind.Basic], key=lambda t: name(t).lower())


def collect_walls(document, level_ids):
    groups = dict((i, []) for i in level_ids)
    for wall in DB.FilteredElementCollector(document).OfClass(DB.Wall).WhereElementIsNotElementType():
        p = wall.get_Parameter(DB.BuiltInParameter.WALL_BASE_CONSTRAINT)
        if p and key(p.AsElementId()) in groups:
            groups[key(p.AsElementId())].append(wall)
    return groups


def analyze_type(wall_type):
    result = {'supported': False, 'reason': '', 'material': '', 'thickness': 0.0}
    try:
        if wall_type.Kind != DB.WallKind.Basic:
            raise ValueError('Only Basic Walls are supported.')
        cs = wall_type.GetCompoundStructure()
        if cs is None or not cs.IsVerticallyHomogeneous():
            raise ValueError('Missing or vertically varying compound structure.')
        layers = list(cs.GetLayers())
        i, width, center = structure_layer([(l.Width, l.Function == DB.MaterialFunctionAssignment.Structure) for l in layers])
        material = wall_type.Document.GetElement(layers[i].MaterialId)
        result.update(supported=True, index=i, thickness=width, center=center,
                      material=material.Name if material else 'By category / no material', compound=cs)
    except Exception as error:
        result['reason'] = str(error)
    return result


def check_transform(transform):
    # Horizontal rotations/translations and mirrored links are supported. Tilt/scale are not.
    if (transform.BasisZ.DistanceTo(DB.XYZ.BasisZ) > TOL
            or abs(transform.BasisX.GetLength()-1.0) > TOL
            or abs(transform.BasisY.GetLength()-1.0) > TOL):
        raise ValueError('Tilted or scaled links cannot be traced reliably.')


def wall_diagnostics(wall):
    """Read evidence for skipped walls; diagnostic failures must never stop a run."""
    values = []
    for label, built_in, angle in (
            ('Cross-section', 'WALL_CROSS_SECTION', False),
            ('Angle from vertical', 'WALL_SINGLE_SLANT_ANGLE_FROM_VERTICAL', True),
            ('Exterior taper angle', 'WALL_TAPERED_EXTERIOR_INWARD_ANGLE', True),
            ('Interior taper angle', 'WALL_TAPERED_INTERIOR_INWARD_ANGLE', True),
            ('Top attached', 'WALL_TOP_IS_ATTACHED', False),
            ('Bottom attached', 'WALL_BOTTOM_IS_ATTACHED', False),
            ('Location line', 'WALL_KEY_REF_PARAM', False)):
        try:
            p = wall.get_Parameter(getattr(DB.BuiltInParameter, built_in))
            if p is None:
                values.append(label + '=not available')
            elif angle:
                values.append('{}={:.6f} degrees'.format(label, math.degrees(p.AsDouble())))
            else:
                display = p.AsValueString() or ''
                values.append('{}={} (raw={})'.format(label, display, p.AsInteger()))
        except Exception as error:
            values.append('{}=unavailable ({})'.format(label, type(error).__name__))
    try:
        values.append('Expected vertical enum={}'.format(int(DB.WallCrossSection.Vertical)))
        values.append('Curve={}'.format(wall.Location.Curve.GetType().Name))
        values.append('Flipped={}'.format(wall.Flipped))
        values.append('SketchId={}'.format(key(wall.SketchId)))
    except Exception:
        pass
    return '; '.join(values)


def corrected_curve(wall, analysis, transform):
    if not analysis['supported']:
        raise ValueError(analysis['reason'])
    if not isinstance(wall.Location, DB.LocationCurve):
        raise ValueError('Wall has no location curve.')
    curve = wall.Location.Curve
    if not isinstance(curve, DB.Line):
        raise ValueError('Curved walls are skipped: layer-center offset is not verified for this geometry.')
    if abs(curve.Direction.Z) > TOL:
        raise ValueError('Non-horizontal wall axis.')
    cross = wall.get_Parameter(DB.BuiltInParameter.WALL_CROSS_SECTION)
    if cross and cross.AsInteger() != int(DB.WallCrossSection.Vertical):
        raise ValueError('Cross-section is not Vertical; slanted/tapered walls are not supported. '
                         'See cross-section and angle values in the wall diagnostics.')
    for flag in ('WALL_TOP_IS_ATTACHED', 'WALL_BOTTOM_IS_ATTACHED'):
        p = wall.get_Parameter(getattr(DB.BuiltInParameter, flag))
        if p and p.AsInteger():
            raise ValueError('Attached wall profile cannot be reproduced exactly.')
    if hasattr(wall, 'SketchId') and wall.SketchId != DB.ElementId.InvalidElementId:
        raise ValueError('Edited wall profile is unsupported.')
    exterior = wall.Orientation.Normalize()
    if abs(exterior.Z) > TOL or abs(exterior.DotProduct(curve.Direction)) > TOL:
        raise ValueError('Wall exterior direction is not reliable.')
    # Layer order runs exterior -> interior; center is signed toward exterior.
    # Orientation ALREADY includes Wall.Flipped. Negating it for Flipped would
    # double-flip. Never derive exterior solely from the line endpoint order.
    # Revit LocationCurve is the geometric wall center even when WALL_KEY_REF_PARAM
    # uses a face/core. Express both steps explicitly so the reference offset
    # is accounted for, but not incorrectly subtracted from the API centerline.
    # Use enum members directly: constructing a .NET enum from an integer is
    # not portable across the IronPython engines bundled with pyRevit.
    location_lines = (DB.WallLocationLine.WallCenterline,
                      DB.WallLocationLine.CoreCenterline,
                      DB.WallLocationLine.FinishFaceExterior,
                      DB.WallLocationLine.FinishFaceInterior,
                      DB.WallLocationLine.CoreExterior,
                      DB.WallLocationLine.CoreInterior)
    reference_value = param(wall, 'WALL_KEY_REF_PARAM').AsInteger()
    if reference_value < 0 or reference_value >= len(location_lines):
        raise ValueError('Unknown wall location-line setting: {}'.format(reference_value))
    location_line = location_lines[reference_value]
    reference_offset = analysis['compound'].GetOffsetForLocationLine(location_line)
    layer_from_reference = analysis['center'] - reference_offset
    shift = exterior.Multiply(reference_offset + layer_from_reference)
    corrected = curve.CreateTransformed(DB.Transform.CreateTranslation(shift))
    # Offset in source coordinates FIRST, then apply the link placement.
    return corrected.CreateTransformed(transform)


def validate(doc, link, configurations):
    if not link.IsValidObject or link.GetLinkDocument() is None:
        raise ValueError('The architectural link is unloaded or inaccessible.')
    check_transform(link.GetTotalTransform())
    if not configurations:
        raise ValueError('Select at least one linked level.')
    linked = link.GetLinkDocument()
    for config in configurations:
        if config.get('combine_openings', False):
            combine_opening_bounds([], config.get('maximum_gap', 0.0))
        if not isinstance(linked.GetElement(config['source_level']), DB.Level):
            raise ValueError('A selected linked level no longer exists.')
        bottom, top = doc.GetElement(config['bottom']), doc.GetElement(config['top'])
        if not isinstance(bottom, DB.Level) or not isinstance(top, DB.Level):
            raise ValueError('Select host bottom and top levels for every level.')
        if top.ProjectElevation <= bottom.ProjectElevation + TOL:
            raise ValueError('Host top level must be above host bottom level: ' + config['label'])
        for target in config['mapping'].values():
            if target is None:
                continue
            wt = doc.GetElement(target)
            if not isinstance(wt, DB.WallType) or wt.Kind != DB.WallKind.Basic:
                raise ValueError('Mapped host Basic Wall type no longer exists.')


def duplicate(candidates, curve, target, bottom, top):
    a, b = curve.GetEndPoint(0), curve.GetEndPoint(1)
    for wall in candidates:
        if wall.GetTypeId() != target:
            continue
        try:
            if (param(wall, 'WALL_BASE_CONSTRAINT').AsElementId() != bottom
                    or param(wall, 'WALL_HEIGHT_TYPE').AsElementId() != top):
                continue
            c = wall.Location.Curve
            if not isinstance(c, DB.Line):
                continue
            x, y = c.GetEndPoint(0), c.GetEndPoint(1)
            # Plan comparison: level constraints own the vertical extent.
            dist = lambda p, q: ((p.X-q.X)**2 + (p.Y-q.Y)**2)**0.5
            if ((dist(a,x) < TOL and dist(b,y) < TOL)
                    or (dist(a,y) < TOL and dist(b,x) < TOL)):
                return wall
        except Exception:
            continue
    return None


def insert_ids(wall):
    ids = dict((key(i), i) for i in wall.FindInserts(True, False, True, True))
    for i in wall.GetDependentElements(DB.ElementClassFilter(DB.Opening)):
        ids[key(i)] = i
    return list(ids.values())


def create_opening(doc, host, source, bounds, transform, bottom_level, base_z, top_z):
    left, right, low, high = bounds
    if right-left <= TOL or high-low <= TOL:
        raise ValueError('Opening has zero width or height.')
    if left < -TOL or right > source.Location.Curve.Length + TOL:
        raise ValueError('Opening extends outside the source wall axis.')
    src_axis = source.Location.Curve
    a = src_axis.GetEndPoint(0).Add(src_axis.Direction.Multiply(left))
    b = src_axis.GetEndPoint(0).Add(src_axis.Direction.Multiply(right))
    a = transform.OfPoint(DB.XYZ(a.X, a.Y, low))
    b = transform.OfPoint(DB.XYZ(b.X, b.Y, high))
    if a.Z < base_z-TOL or b.Z > top_z+TOL:
        raise ValueError('Opening is outside the mapped host wall vertical extent.')
    # Project XY onto the new structural centerline, retaining actual source Z.
    axis = host.Location.Curve
    pa, pb = axis.Project(a).XYZPoint, axis.Project(b).XYZPoint
    a, b = DB.XYZ(pa.X,pa.Y,a.Z), DB.XYZ(pb.X,pb.Y,b.Z)
    # Re-runs can fill missing cuts on a matched existing wall. Never duplicate
    # an existing rectangular opening at the same along-wall/elevation bounds.
    for existing_id in host.GetDependentElements(DB.ElementClassFilter(DB.Opening)):
        existing = doc.GetElement(existing_id)
        if isinstance(existing, DB.Opening) and existing.IsRectBoundary:
            p, q = list(existing.BoundaryRect)
            def signature(x, y):
                u = [v.Subtract(axis.GetEndPoint(0)).DotProduct(axis.Direction) for v in (x,y)]
                return min(u), max(u), min(x.Z,y.Z), max(x.Z,y.Z)
            if all(abs(x-y) <= TOL for x,y in zip(signature(a,b),signature(p,q))):
                return None
    opening = doc.Create.NewOpening(host, a, b)
    # BOTH constraints refer to host bottom. The host wall top never participates.
    low_offset, high_offset = opening_offsets(a.Z,b.Z,bottom_level.ProjectElevation)
    set_param(opening, 'WALL_BASE_CONSTRAINT', bottom_level.Id)
    set_param(opening, 'WALL_HEIGHT_TYPE', bottom_level.Id)
    set_param(opening, 'WALL_BASE_OFFSET', low_offset)
    set_param(opening, 'WALL_TOP_OFFSET', high_offset)
    doc.Regenerate()
    if (param(opening, 'WALL_BASE_CONSTRAINT').AsElementId() != bottom_level.Id
            or param(opening, 'WALL_HEIGHT_TYPE').AsElementId() != bottom_level.Id
            or abs(param(opening, 'WALL_BASE_OFFSET').AsDouble()-low_offset) > TOL
            or abs(param(opening, 'WALL_TOP_OFFSET').AsDouble()-high_offset) > TOL):
        raise ValueError('Revit did not retain the required opening level/offset references.')
    return opening


class RollbackErrors(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        for failure in accessor.GetFailureMessages():
            if failure.GetSeverity() == DB.FailureSeverity.Error:
                return DB.FailureProcessingResult.ProceedWithRollBack
        return DB.FailureProcessingResult.Continue


def transaction(doc, title):
    tx = DB.Transaction(doc, title)
    tx.Start()
    options = tx.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(RollbackErrors())
    options.SetClearAfterRollback(True)
    tx.SetFailureHandlingOptions(options)
    return tx


def commit(tx):
    if tx.Commit() != DB.TransactionStatus.Committed:
        raise RuntimeError('Revit rejected a creation transaction.')


def align_host_orientation(doc, host, source_orientation, transform):
    # Orientation queries the exterior face. Newly created/constrained walls do
    # not necessarily have faces until regeneration, even inside a transaction.
    doc.Regenerate()
    if host.Orientation.DotProduct(transform.OfVector(source_orientation)) < 0:
        host.Flip()
        doc.Regenerate()


def allow_wall_joins(wall):
    """Allow Revit to clean up both wall ends; do not force geometry joins."""
    for end in (0, 1):
        DB.WallUtils.AllowWallJoinAtEnd(wall, end)


def repair_selected_joins(doc, walls):
    """Explicit repair for selected host walls from earlier tool runs."""
    tx = transaction(doc, 'NdevTools - Allow joins on selected walls')
    repaired, failures = 0, []
    try:
        for wall in walls:
            sub = DB.SubTransaction(doc)
            sub.Start()
            try:
                allow_wall_joins(wall)
                doc.Regenerate()
                if sub.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit rejected the wall join change.')
                repaired += 1
            except RegenerationFailedException:
                raise
            except Exception as error:
                if sub.GetStatus() == DB.TransactionStatus.Started:
                    sub.RollBack()
                failures.append('Wall {}: {}'.format(key(wall.Id), error))
        commit(tx)
    except Exception:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        raise
    return repaired, failures


def execute(doc, link, configs, progress=None):
    validate(doc, link, configs)
    source_doc, transform = link.GetLinkDocument(), link.GetTotalTransform()
    grouped = collect_walls(source_doc, [key(c['source_level']) for c in configs])
    result = dict(levels=len(configs), found=sum(len(v) for v in grouped.values()), created=0,
                  none=0, unsupported=0, duplicates=0, detected=0, openings=0,
                  skipped_openings=0, errors=0, details=[], wall_map={})
    def log(config, wall, reason, insert=None):
        result['details'].append((config['label'], name(wall.WallType), key(wall.Id),
                                  key(insert.Id) if insert else '', str(reason), wall_diagnostics(wall)))
    existing = list(DB.FilteredElementCollector(doc).OfClass(DB.Wall).WhereElementIsNotElementType())
    created = []
    opening_targets = []
    missing_destinations = []
    processed = 0
    def tick(value, maximum):
        if progress:
            if progress.cancelled:
                raise RuntimeError('Cancelled. All walls and openings from this run were rolled back.')
            progress.update_progress(value, max(1, maximum))
    group = DB.TransactionGroup(doc, 'NdevTools - Wall Tracing')
    group.Start()
    tx = None
    try:
        tx = transaction(doc, 'Create structural walls')
        for config in configs:
            bottom, top = doc.GetElement(config['bottom']), doc.GetElement(config['top'])
            for source in grouped[key(config['source_level'])]:
                tick(processed, result['found'] * 2)
                processed += 1
                target = config['mapping'].get(key(source.GetTypeId()))
                if target is None:
                    result['none'] += 1
                    log(config, source, 'None mapping: wall and openings skipped.')
                    continue
                try:
                    curve = corrected_curve(source, analyze_type(source.WallType), transform)
                    base_offset = param(source, 'WALL_BASE_OFFSET').AsDouble()
                    source_top = source_doc.GetElement(param(source, 'WALL_HEIGHT_TYPE').AsElementId())
                    top_offset = param(source, 'WALL_TOP_OFFSET').AsDouble() if isinstance(source_top, DB.Level) else 0.0
                    base_z, top_z = bottom.ProjectElevation + base_offset, top.ProjectElevation + top_offset
                    if top_z <= base_z + doc.Application.ShortCurveTolerance:
                        raise ValueError('Mapped wall has non-positive height after source offsets.')
                except ValueError as error:
                    result['unsupported'] += 1
                    log(config, source, error)
                    continue
                except Exception as error:
                    # API/interop failures are errors, not unsupported geometry.
                    result['errors'] += 1
                    log(config, source, 'Wall preparation: {}: {}'.format(type(error).__name__, error))
                    continue
                matched = duplicate(existing, curve, target, bottom.Id, top.Id)
                if matched is not None:
                    result['duplicates'] += 1
                    log(config, source, 'Existing host wall {} reused for missing openings; wall creation skipped.'.format(key(matched.Id)))
                    actual_base = bottom.ProjectElevation + param(matched, 'WALL_BASE_OFFSET').AsDouble()
                    actual_top = top.ProjectElevation + param(matched, 'WALL_TOP_OFFSET').AsDouble()
                    opening_targets.append((config, source, matched, bottom, actual_base, actual_top))
                    result['wall_map'][key(source.Id)] = key(matched.Id)
                    continue
                sub = DB.SubTransaction(doc)
                stage = 'start wall subtransaction'
                try:
                    sub.Start()
                    a,b = curve.GetEndPoint(0),curve.GetEndPoint(1)
                    curve = DB.Line.CreateBound(DB.XYZ(a.X,a.Y,bottom.ProjectElevation), DB.XYZ(b.X,b.Y,bottom.ProjectElevation))
                    stage = 'Wall.Create'
                    host = DB.Wall.Create(doc, curve, target, bottom.Id, top_z-base_z, base_offset, False, True)
                    # Keep ends stable only while validating centerlines and placing
                    # openings. Enable both ends after all geometry has been created.
                    stage = 'temporarily disable wall joins during construction'
                    DB.WallUtils.DisallowWallJoinAtEnd(host, 0)
                    DB.WallUtils.DisallowWallJoinAtEnd(host, 1)
                    stage = 'set wall location line and level constraints'
                    set_param(host, 'WALL_KEY_REF_PARAM', int(DB.WallLocationLine.WallCenterline))
                    set_param(host, 'WALL_HEIGHT_TYPE', top.Id)
                    set_param(host, 'WALL_TOP_OFFSET', top_offset)
                    set_param(host, 'WALL_BASE_OFFSET', base_offset)
                    stage = 'regenerate geometry and align exterior orientation'
                    align_host_orientation(doc, host, source.Orientation, transform)
                    stage = 'verify created centerline'
                    actual = host.Location.Curve
                    # Compare XY; Revit may normalize LocationCurve Z to the base offset.
                    for i in (0,1):
                        p,q = actual.GetEndPoint(i),curve.GetEndPoint(i)
                        if ((p.X-q.X)**2+(p.Y-q.Y)**2)**0.5 > TOL:
                            raise ValueError('Created host centerline differs from the intended curve.')
                    stage = 'commit wall subtransaction'
                    if sub.Commit() != DB.TransactionStatus.Committed:
                        raise ValueError('Wall subtransaction failed.')
                    result['created'] += 1
                    result['wall_map'][key(source.Id)] = key(host.Id)
                    existing.append(host)
                    created.append((config, source, host, bottom, base_z, top_z))
                    opening_targets.append((config, source, host, bottom, base_z, top_z))
                except RegenerationFailedException:
                    raise  # Revit requires aborting the enclosing transaction.
                except Exception as error:
                    if sub.GetStatus() == DB.TransactionStatus.Started:
                        sub.RollBack()
                    result['errors'] += 1
                    log(config, source, 'Wall creation [{}]: {}: {}\n{}'.format(
                        stage, type(error).__name__, error, traceback.format_exc()))
                    missing_destinations.append(source)
        commit(tx)
        tx = transaction(doc, 'Create rectangular openings')
        doc.Regenerate()
        from wall_tracing_openings import scan_wall_openings, diagnostic_text
        for source in missing_destinations:
            for item in scan_wall_openings(source):
                item['result'] = 'NO_DESTINATION_WALL'
                result.setdefault('opening_diagnostics', []).append(
                    diagnostic_text(item, key(source.Id), '-'))
        for config, source, host, bottom, base_z, top_z in opening_targets:
            tick(processed, result['found'] + len(opening_targets))
            processed += 1
            candidates = scan_wall_openings(source)
            from wall_tracing_fallback import apply_parameter_fallbacks
            candidates = apply_parameter_fallbacks(source, candidates)
            jobs = []
            for item in candidates:
                if item['valid']:
                    result['detected'] += 1
                    jobs.append((item['bounds'], [item]))
                elif item['result'] != 'DUPLICATE':
                    result['skipped_openings'] += 1
            if config.get('combine_openings', False):
                # Preserve existing geometry-only combination. A fallback must
                # never enlarge or replace a successful geometry result.
                fallback_jobs = [job for job in jobs if job[1][0].get('detection_source') == 'PARAMETER_FALLBACK']
                originals = [job for job in jobs if job[1][0].get('detection_source') != 'PARAMETER_FALLBACK']
                jobs = [(envelope, [originals[i][1][0] for i in members])
                        for envelope,members in combine_opening_bounds(
                            [job[0] for job in originals],config['maximum_gap'])]
                jobs.extend(fallback_jobs)
            for bounds, members in jobs:
                tick(processed, result['found'] + len(opening_targets))
                sub = DB.SubTransaction(doc)
                try:
                    sub.Start()
                    opening = create_opening(doc, host, source, bounds, transform, bottom, base_z, top_z)
                    if sub.Commit() != DB.TransactionStatus.Committed:
                        raise ValueError('Opening subtransaction failed.')
                    if opening is not None:
                        result['openings'] += 1
                    else:
                        result['existing_openings'] = result.get('existing_openings', 0) + 1
                    for item in members:
                        item['result'] = 'CREATED' if opening is not None else 'EXISTING'
                        if len(members) > 1:
                            item['reason'] += ' Combined output bounds: {}'.format(bounds)
                except RegenerationFailedException:
                    raise
                except Exception as error:
                    if sub.GetStatus() == DB.TransactionStatus.Started:
                        sub.RollBack()
                    result['errors'] += 1
                    for item in members:
                        item.update(result='GEOMETRY_FAILURE',reason=item['reason']+' Creation: '+str(error))
            for item in candidates:
                message = diagnostic_text(item,key(source.Id),key(host.Id))
                result.setdefault('opening_diagnostics',[]).append(message)
                if item['result'] not in ('CREATED','EXISTING','DUPLICATE'):
                    log(config,source,'{}: {}'.format(item['result'],item['reason']))

        commit(tx)
        tx = transaction(doc, 'Allow joins on traced walls')
        for config, source, host, bottom, base_z, top_z in created:
            sub = DB.SubTransaction(doc)
            sub.Start()
            try:
                allow_wall_joins(host)
                doc.Regenerate()
                if sub.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Revit rejected the wall join change.')
            except RegenerationFailedException:
                raise
            except Exception as error:
                if sub.GetStatus() == DB.TransactionStatus.Started:
                    sub.RollBack()
                result['errors'] += 1
                log(config, source, 'Allow wall joins: {}'.format(error))
        commit(tx)
        tick(result['found'] + len(opening_targets), result['found'] + len(opening_targets))
        if group.Assimilate() != DB.TransactionStatus.Committed:
            raise RuntimeError('Revit did not commit the creation group.')
    except Exception:
        if tx and tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        raise
    return result


def report(result, output):
    labels = [('Selected levels','levels'), ('Architectural walls found','found'),
              ('Structural walls created','created'), ('Walls skipped - None mapping','none'),
              ('Walls skipped - unsupported geometry','unsupported'), ('Duplicate walls skipped','duplicates'),
              ('Rectangular openings detected','detected'), ('Rectangular openings created','openings'),
              ('Unsupported/non-rectangular openings skipped','skipped_openings'), ('Errors','errors')]
    summary = '\n'.join('{}: {}'.format(label,result[k]) for label,k in labels)
    summary += '\nExisting rectangular openings retained: {}'.format(result.get('existing_openings', 0))
    output.print_md('## NdevTools - Wall Tracing')
    print(summary)
    if result['details']:
        output.print_table(result['details'], columns=['Linked level','Source wall type','Source wall ID','Insert ID','Reason','Wall diagnostics'])
    for diagnostic in result.get('opening_diagnostics', []):
        print(diagnostic)
    if result['wall_map']:
        output.print_table(sorted(result['wall_map'].items()), columns=['Source linked wall ID','Created/reused host wall ID'])
    reasons = {}
    for level, wall_type, wall_id, insert_id, reason, diagnostics in result['details']:
        if reason.startswith(('None mapping:', 'Combination group:')):
            continue
        # Keep stack traces in expanded/saved details, not in the compact dialog.
        short_reason = reason.split('\n', 1)[0]
        reasons[short_reason] = reasons.get(short_reason, 0) + 1
    if reasons:
        summary += '\n\nMain skip/error reasons:\n' + '\n'.join(
            '{} item(s): {}'.format(count, reason)
            for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:5])
    details = [summary, '\nPER-ITEM DIAGNOSTICS (IDs refer to the linked model)']
    for level, wall_type, wall_id, insert_id, reason, diagnostics in result['details']:
        details.append('\nLevel: {}\nWall type: {}\nSource wall ID: {}\nInsert ID: {}\nReason: {}\n{}'.format(
            level, wall_type, wall_id, insert_id or '-', reason, diagnostics))
    details.extend(['\nOPENING CANDIDATE DIAGNOSTICS'] + result.get('opening_diagnostics', []))
    full_report = '\n\n'.join(details)
    try:
        directory = os.path.join(tempfile.gettempdir(), 'NdevTools-WallTracing')
        if not os.path.isdir(directory):
            os.makedirs(directory)
        path = os.path.join(directory, 'wall-tracing-{}.txt'.format(uuid.uuid4().hex[:12]))
        with io.open(path, 'w', encoding='utf-8') as stream:
            stream.write(full_report if isinstance(full_report, type(u'')) else full_report.decode('utf-8'))
        print('Full diagnostic report: ' + path)
        summary += '\n\nFull diagnostic report saved to:\n' + path
    except Exception as error:
        summary += '\n\nCould not save diagnostic report: {}'.format(error)
    forms.alert(summary + '\n\nExpand details below for each wall ID, type, reason and parameter values. '
                'The same information is in the pyRevit output window.',
                expanded=full_report, title='Wall Tracing')
