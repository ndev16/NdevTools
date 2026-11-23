# -*- coding: utf-8 -*-
"""Standalone CAD conversion commands. No MCP or external process dependency."""
import math
import json
from System import Guid, String
from pyrevit import DB, forms, revit
from ndev_main_cad_math import line_key, paired_axes, rectangle_center, closed_rectangles, symbol_clusters


class CadFailures(DB.IFailuresPreprocessor):
    def __init__(self):
        self.messages = []

    def PreprocessFailures(self, accessor):
        errors = False
        for failure in accessor.GetFailureMessages():
            self.messages.append(failure.GetDescriptionText())
            if failure.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(failure)
            else:
                errors = True
        return DB.FailureProcessingResult.ProceedWithRollBack if errors else DB.FailureProcessingResult.Continue


class CadTransaction(object):
    """Do not let Pending/RolledBack transactions appear to have succeeded."""
    def __init__(self, doc, title):
        self.transaction = DB.Transaction(doc, title)
        self.failures = CadFailures()

    def __enter__(self):
        self.transaction.Start()
        options = self.transaction.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(self.failures)
        options.SetClearAfterRollback(True)
        self.transaction.SetFailureHandlingOptions(options)
        return self

    def __exit__(self, kind, value, trace):
        try:
            if kind is not None:
                self.transaction.RollBack()
            elif self.transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Revit did not commit the conversion.\n'+'\n'.join(self.failures.messages))
        finally:
            if self.transaction.GetStatus() == DB.TransactionStatus.Started:
                self.transaction.RollBack()
            self.transaction.Dispose()
        return False


def source_schema():
    key = Guid('fd48e0d6-b51c-496b-bd66-548b409cfdbc')
    schema = DB.ExtensibleStorage.Schema.Lookup(key)
    if schema is None:
        builder = DB.ExtensibleStorage.SchemaBuilder(key)
        builder.SetSchemaName('NdevCadSourceV1')
        builder.SetReadAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
        builder.SetWriteAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
        builder.AddSimpleField('SourceKey', String)
        schema = builder.Finish()
    return schema


def source_key(kind, cad, key):
    return json.dumps([kind, cad.UniqueId, key], separators=(',', ':'))


def eid(value):
    return value.Value if hasattr(value, 'Value') else value.IntegerValue


def name(element):
    return DB.Element.Name.GetValue(element)


def pick(items, title):
    choices = {}
    for item in items:
        label = '{} [{}]'.format(name(item), eid(item.Id))
        if isinstance(item, DB.FamilySymbol):
            label = '{} : {}'.format(item.FamilyName, label)
        choices[label] = item
    selected = forms.SelectFromList.show(sorted(choices), title=title, multiselect=False)
    return choices.get(selected)


def number(prompt, default):
    answer = forms.ask_for_string(default=str(default), prompt=prompt, title='CAD to BIM')
    if answer is None:
        return None
    value = float(answer)
    if math.isnan(value) or math.isinf(value):
        raise ValueError('Enter a finite number.')
    return value / 304.8


def read_cad(doc, cad):
    layers = {}
    def walk(geometry, inherited=None):
        for obj in geometry:
            style = doc.GetElement(obj.GraphicsStyleId)
            layer = style.GraphicsStyleCategory.Name if style else inherited
            if layer == '0' and inherited:
                layer = inherited
            if isinstance(obj, DB.GeometryInstance):
                # Instance geometry is already transformed; do not transform twice.
                walk(obj.GetInstanceGeometry(), layer)
            elif isinstance(obj, (DB.Curve, DB.PolyLine)) and layer:
                layers.setdefault(layer, []).append(obj)
    options = DB.Options()
    options.IncludeNonVisibleObjects = False
    if cad.ViewSpecific:
        options.View = doc.GetElement(cad.OwnerViewId)
    geometry = cad.get_Geometry(options)
    if geometry is not None:
        walk(geometry)
    return layers


def xyz(p, z):
    return DB.XYZ(p[0], p[1], z)


def point(p):
    return (p.X, p.Y, p.Z)


def source_lines(objects):
    result = {}
    for obj in objects:
        if not isinstance(obj, (DB.Line, DB.PolyLine)):
            continue
        points = list(obj.GetCoordinates()) if isinstance(obj, DB.PolyLine) else [obj.GetEndPoint(0), obj.GetEndPoint(1)]
        for a, b in zip(points, points[1:]):
            aa, bb = point(a), point(b)
            if math.hypot(aa[0]-bb[0], aa[1]-bb[1]) > 0.01:
                result[line_key(aa, bb)] = (aa, bb)
    return list(result.values())


def run(kind):
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert('Open a project before converting CAD.', exitscript=True)
    if kind=='Grids':
        from ndev_main_cad_grid_mapping import show
        show(doc)
        return
    cad = pick(list(DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance)), 'Select linked or imported DWG')
    if cad is None:
        forms.alert('Link or import your DWG into the project, then run this command.')
        return
    layers = read_cad(doc, cad)
    selected = forms.SelectFromList.show(sorted(layers), multiselect=True,
        title='CAD to {} | Select source layers'.format(kind))
    if not selected:
        return
    objects = [obj for layer in selected for obj in layers[layer]]
    level, symbol, z, height, top = None, None, 0.0, None, None
    wall_joins = None
    if kind != 'Grids':
        level = pick(list(DB.FilteredElementCollector(doc).OfClass(DB.Level)), 'Select target level')
        if level is None:
            return
        offset = number('Offset from target level (mm)', 0)
        if offset is None:
            return
        z = level.Elevation + offset
        if kind == 'Walls':
            types = [t for t in DB.FilteredElementCollector(doc).OfClass(DB.WallType)
                     if t.Kind == DB.WallKind.Basic]
        else:
            category = DB.BuiltInCategory.OST_StructuralFraming if kind == 'Beams' else DB.BuiltInCategory.OST_StructuralColumns
            types = list(DB.FilteredElementCollector(doc).OfCategory(category).OfClass(DB.FamilySymbol))
        symbol = pick(types, 'Select {} type'.format(kind))
        if symbol is None:
            return
        if kind == 'Columns':
            top = pick([l for l in DB.FilteredElementCollector(doc).OfClass(DB.Level)
                        if l.Elevation > z], 'Select column top level')
            if top is None:
                return
        if kind == 'Walls':
            height = number('Height above base (mm)', 3000)
            if height is None:
                return
            if height <= 0:
                raise ValueError('Height must be greater than zero.')
            wall_joins = forms.CommandSwitchWindow.show(['Keep wall ends unjoined', 'Automatic wall joins'],
                                                       message='Wall end joins')
            if wall_joins is None:
                return
    deferred = sum(1 for obj in objects if not isinstance(obj, (DB.Line, DB.PolyLine)))
    if kind == 'Columns':
        positions = {}
        mode = forms.CommandSwitchWindow.show(['Rectangular outlines', 'Column symbols (clusters)'], message='How are columns drawn?')
        if mode is None:
            return
        if mode == 'Column symbols (clusters)':
            lines = source_lines(objects)
            if len(lines) > 5000:
                raise ValueError('Select fewer than 5000 symbol marks per run.')
            radius = number('Maximum distance joining column symbol marks (mm)', 600)
            if radius is None:
                return
            if radius <= 0:
                raise ValueError('Cluster radius must be positive.')
            rotation = forms.ask_for_string(default='0', prompt='Column rotation in degrees (symbols do not establish orientation)', title='Column rotation')
            if rotation is None:
                return
            angle = float(rotation)*math.pi/180.0
            if math.isnan(angle) or math.isinf(angle):
                raise ValueError('Column rotation must be finite.')
            groups = symbol_clusters(lines, radius)
            for center, marks in groups:
                positions[tuple(round(v, 5) for v in center[:2])] = (center, angle)
            deferred = len(lines)-sum(marks for center, marks in groups)
        for obj in objects:
            if mode != 'Rectangular outlines':
                continue
            if not isinstance(obj, DB.PolyLine):
                deferred += 1
                continue
            shape = rectangle_center([point(p) for p in obj.GetCoordinates()], 0.003)
            if shape:
                center, angle = shape
                positions[tuple(round(v, 5) for v in center[:2])] = (center, angle)
            else:
                deferred += 1
        if mode == 'Rectangular outlines':
            for center, angle in closed_rectangles(source_lines(objects)):
                positions[tuple(round(v, 5) for v in center[:2])] = (center, angle)
        candidates = list(positions.values())
    else:
        candidates = source_lines(objects)
        if kind in ('Walls', 'Beams'):
            mode = forms.CommandSwitchWindow.show(['Paired faces', 'Centerlines'], message='How are {} drawn?'.format(kind.lower()))
            if mode is None:
                return
            if mode == 'Paired faces':
                if len(candidates) > 2000:
                    raise ValueError('Select fewer than 2000 wall face segments per run.')
                width = symbol.Width if kind == 'Walls' else number('Distance between beam faces (mm)', 300)
                if width is None:
                    return
                if width <= 0:
                    raise ValueError('Face spacing must be greater than zero.')
                candidates, unmatched = paired_axes(candidates, width, 3.0/304.8)
                deferred += unmatched
    category = {'Walls': DB.BuiltInCategory.OST_Walls,
                'Beams': DB.BuiltInCategory.OST_StructuralFraming,
                'Columns': DB.BuiltInCategory.OST_StructuralColumns,
                'Grids': DB.BuiltInCategory.OST_Grids}[kind]
    schema = source_schema()
    field = schema.GetField('SourceKey')
    existing, tracked = set(), set()
    for element in DB.FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
        entity = element.GetEntity(schema)
        if entity.IsValid():
            tracked.add(entity.Get[String](field))
        location = element.Location
        if kind == 'Columns' and isinstance(location, DB.LocationPoint):
            existing.add(tuple(round(v, 5) for v in point(location.Point)))
        else:
            curve = element.Curve if isinstance(element, DB.Grid) else location.Curve if isinstance(location, DB.LocationCurve) else None
            if isinstance(curve, DB.Line):
                existing.add(line_key(point(curve.GetEndPoint(0)), point(curve.GetEndPoint(1))))
    pending = []
    for candidate in candidates:
        if kind == 'Columns':
            key = tuple(round(v, 5) for v in (candidate[0][0], candidate[0][1], z))
        else:
            a, b = candidate
            key = line_key((a[0], a[1], z), (b[0], b[1], z))
        if key not in existing and source_key(kind, cad, key) not in tracked:
            pending.append(candidate)
            existing.add(key)
    if not pending:
        forms.alert('No new supported geometry found. Existing placements are skipped.\nUnmatched source objects: {}'.format(deferred))
        return
    if len(pending) > 2000:
        raise ValueError('Select a smaller set of layers: maximum 2000 placements per run.')
    message = ('Create {} {}?\n\nUnmatched source objects: {}.\n'
               'Columns use the chosen outline/symbol reading; beams and grids use straight lines.\n'
               'Chosen families and levels control sizes and elevations.').format(len(pending), kind.lower(), deferred)
    if not forms.alert(message, yes=True, no=True):
        return
    created = []
    with CadTransaction(doc, 'CAD to {}'.format(kind)) as operation:
        if isinstance(symbol, DB.FamilySymbol) and not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        for candidate_index, candidate in enumerate(pending):
            if kind == 'Columns':
                center, angle = candidate
                origin = xyz(center, z)
                element = doc.Create.NewFamilyInstance(origin, symbol, level, DB.Structure.StructuralType.Column)
                element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).Set(level.Id)
                element.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(top.Id)
                element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).Set(z-level.Elevation)
                element.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).Set(0.0)
                DB.ElementTransformUtils.RotateElement(doc, element.Id, DB.Line.CreateBound(origin, origin+DB.XYZ.BasisZ), angle)
            else:
                a, b = candidate
                curve = DB.Line.CreateBound(xyz(a, z), xyz(b, z))
                if kind == 'Walls':
                    element = DB.Wall.Create(doc, curve, symbol.Id, level.Id, height, z-level.Elevation, False, True)
                    if wall_joins == 'Keep wall ends unjoined':
                        DB.WallUtils.DisallowWallJoinAtEnd(element, 0)
                        DB.WallUtils.DisallowWallJoinAtEnd(element, 1)
                elif kind == 'Beams':
                    element = doc.Create.NewFamilyInstance(curve, symbol, level, DB.Structure.StructuralType.Beam)
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(element, 0)
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(element, 1)
            if kind == 'Columns':
                key = tuple(round(v, 5) for v in (candidate[0][0], candidate[0][1], z))
            else:
                key = line_key((candidate[0][0], candidate[0][1], z),
                               (candidate[1][0], candidate[1][1], z))
            entity = DB.ExtensibleStorage.Entity(schema)
            entity.Set[String](field, source_key(kind, cad, key))
            element.SetEntity(entity)
            created.append(element.Id)
        doc.Regenerate()
        if any(doc.GetElement(element_id) is None for element_id in created):
            raise ValueError('Revit did not retain every created element. Conversion rolled back.')
        for element_id, candidate in zip(created, pending):
            element = doc.GetElement(element_id)
            tolerance = 1.0/304.8
            if kind == 'Columns':
                expected = xyz(candidate[0], z)
                actual = element.Location.Point
                if math.hypot(actual.X-expected.X, actual.Y-expected.Y) > tolerance:
                    raise ValueError('Column placement did not match the planned point.')
                # As in the reference source's GovernedBaseZ, a level-based
                # instance's LocationPoint is not its physical base plane.
                base_id = element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId()
                base_offset = element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).AsDouble()
                if base_id != level.Id or abs(doc.GetElement(base_id).Elevation+base_offset-z) > tolerance:
                    raise ValueError('Column base constraint did not match the chosen level and offset.')
                if element.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).AsElementId() != top.Id:
                    raise ValueError('Column top level did not match the chosen level.')
            else:
                curve = element.Curve if kind == 'Grids' else element.Location.Curve
                expected = [xyz(candidate[0], z), xyz(candidate[1], z)]
                actual = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
                if kind == 'Walls':
                    expected = [DB.XYZ(p.X,p.Y,0) for p in expected]
                    actual = [DB.XYZ(p.X,p.Y,0) for p in actual]
                    if abs(element.get_Parameter(DB.BuiltInParameter.WALL_BASE_OFFSET).AsDouble()-(z-level.Elevation)) > tolerance:
                        raise ValueError('Wall base offset did not match the chosen value.')
                if kind == 'Walls' and wall_joins == 'Automatic wall joins':
                    axis = DB.Line.CreateUnbound(expected[0], (expected[1]-expected[0]).Normalize())
                    error = max(axis.Distance(p) for p in actual)
                else:
                    error = min(max(actual[0].DistanceTo(expected[0]), actual[1].DistanceTo(expected[1])),
                                max(actual[1].DistanceTo(expected[0]), actual[0].DistanceTo(expected[1])))
                if error > tolerance:
                    raise ValueError('{} placement differs from the planned geometry by {:.1f} mm.'.format(kind, error*304.8))
            if not element.GetEntity(schema).IsValid():
                raise ValueError('CAD source tracking could not be read back.')
    forms.alert('Created {} {}. Unmatched source objects: {}.\n{}'.format(
        len(created), kind.lower(), deferred, '\n'.join(set(operation.failures.messages))))
