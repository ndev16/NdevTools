# -*- coding: utf-8 -*-
"""Native Revit Structural Beam Systems for FramePilot flat roof faces.

The flat path deliberately does NOT create loose RAFTER family instances.
A failed BeamSystem is an error, so FramePilot's per-host transaction rolls back
any previously owned framing that would otherwise be replaced.
"""

from ndev_roof_geometry import FramingMember
from ndev_roof_placement import BaseFramingEngine
from ndev_roof_families import activate_symbol
from ndev_roof_tracking import tag_instance
from ndev_roof_config import WORKPLANE_FACES, z_justification_value

# Local-profile distance tolerance in Revit internal feet.
PROFILE_TOL = 0.0001
MIN_AREA_SF = 0.01


def _flat_profile_points(plane):
    """Validate one exterior sketch loop; never bridge an opening unknowingly."""
    loops = getattr(plane, 'boundary_loops_local', None) or []
    if len(loops) != 1:
        raise ValueError(
            'Flat roof face {0}: expected one closed boundary, found {1}. '
            'Roofs with skylight/opening loops are skipped to avoid framing '
            'across voids.'.format(getattr(plane, 'face_index', '?'), len(loops)))
    loop = list(getattr(plane, 'outer_loop_local', None) or loops[0])
    points = []
    for coord in loop:
        x, y = float(coord[0]), float(coord[1])
        if not points or (x-points[-1][0])**2 + (y-points[-1][1])**2 > PROFILE_TOL**2:
            points.append((x, y))
    if len(points) > 1 and (points[0][0]-points[-1][0])**2 + (points[0][1]-points[-1][1])**2 <= PROFILE_TOL**2:
        points.pop()
    if len(points) < 3:
        raise ValueError('Flat roof beam system needs at least three distinct profile corners.')
    area2 = 0.0
    for i, p in enumerate(points):
        q = points[(i+1) % len(points)]
        area2 += p[0]*q[1]-q[0]*p[1]
    if abs(area2) * 0.5 < MIN_AREA_SF:
        raise ValueError('Flat roof face boundary has near-zero area.')
    return points


class FlatRoofBeamSystemEngine(BaseFramingEngine):
    """Plan each flat face and create a true native Revit BeamSystem."""

    def calculate_members_from_info(self, host_info, require_flat=False):
        planes = getattr(host_info, 'planes', None) or [host_info]
        if not planes:
            raise ValueError('No supported top faces were found for this host.')
        members = []
        for plane in planes:
            if plane.normal.Z <= 0.01:
                raise ValueError('The host must have an upward-facing planar surface.')
            if require_flat and plane.normal.Z < 0.9998:
                raise ValueError('Flat Truss mode requires a level roof face.')
            profile = _flat_profile_points(plane)
            # Dummy start/end are never used for individual beam creation.
            first = plane.point_at(profile[0][0], profile[0][1],
                                   -plane.target_layer_depth)
            second = plane.point_at(profile[1][0], profile[1][1],
                                    -plane.target_layer_depth)
            member = FramingMember(FramingMember.STUD, first, second)
            member.member_type = 'FLAT_BEAM_SYSTEM'
            member.family_name = self.config.stud_family_name
            member.type_name = self.config.stud_type_name
            member.host_kind = host_info.kind
            member.host_id = host_info.element_id
            member.plane = plane
            member.field_loop_local = profile
            member.spacing = self.config.stud_spacing_ft
            # The Work Plane is the actual face-depth reference, not a label.
            # Bottom = host underside; Top = host upper face.
            member.workplane_depth = _workplane_depth(
                plane, getattr(self.config, 'workplane_face', 'bottom'))
            members.append(member)
        return members

    def place_members(self, members, host_info):
        from System.Collections.Generic import List
        from Autodesk.Revit.DB import (
            Curve, Line, Plane, SketchPlane, BeamSystem,
            LayoutRuleFixedDistance, BeamSystemJustifyType,
        )
        try:
            from Autodesk.Revit.DB.Structure import StructuralFramingUtils
        except ImportError:
            StructuralFramingUtils = None

        placed = []
        self._justification_warnings = []
        for member in members:
            if member.member_type != 'FLAT_BEAM_SYSTEM':
                raise ValueError('Flat beam-system engine received an unexpected framing role.')
            plane = member.plane
            # Flattening the roof geometry here would be wrong: use its actual
            # planar top face as the 2D sketch plane.
            profile = List[Curve]()
            world_points = [
                plane.point_at(x, y, member.workplane_depth - plane.target_layer_depth)
                for x, y in member.field_loop_local
            ]
            for i, start in enumerate(world_points):
                end = world_points[(i+1) % len(world_points)]
                if start.DistanceTo(end) <= PROFILE_TOL:
                    raise ValueError('Flat roof beam-system profile contains a zero-length edge.')
                profile.Add(Line.CreateBound(start, end))
            revit_plane = Plane.CreateByNormalAndOrigin(plane.normal, world_points[0])
            sketch = SketchPlane.Create(self.doc, revit_plane)
            direction = plane.y_axis.Normalize()  # same axis as former scanline rafters
            symbol = self._resolve_symbol(member)
            if symbol is None:
                raise ValueError('Selected rafter Structural Framing family/type is not loaded.')
            activate_symbol(self.doc, symbol)

            # Native Revit 2022 BeamSystem.Create, not NewFamilyInstance.
            system = BeamSystem.Create(self.doc, profile, sketch, direction, False)
            if system is None:
                raise RuntimeError('Revit did not create the flat roof Structural Beam System.')
            system.BeamType = symbol
            system.LayoutRule = LayoutRuleFixedDistance(
                member.spacing, BeamSystemJustifyType.DirectionLine)

            # Sketch plane is already at the requested top/bottom host face.
            # Keep Beam System elevation at 0 relative to that plane.
            self.doc.Regenerate()
            beams = [self.doc.GetElement(element_id)
                     for element_id in system.GetBeamIds()]
            beams = [beam for beam in beams if beam is not None]
            if not beams:
                raise RuntimeError('Beam System was created but produced no rafters. '
                                   'The roof transaction has been rolled back.')

            # Both the native system and its constituent beams are tracked in
            # invisible Extensible Storage. Comments are written by script.py.
            tag_instance(system, host_info, member)
            for beam in beams:
                tag_instance(beam, host_info, member)
                if not _set_beam_z_justification(beam, self.config.z_justification):
                    self._justification_warnings.append(
                        'Beam {0}: Revit does not permit setting Z Justification; '
                        'check the member in Properties.'.format(beam.Id.IntegerValue))
                if StructuralFramingUtils is not None:
                    for end_index in (0, 1):
                        try:
                            StructuralFramingUtils.DisallowJoinAtEnd(beam, end_index)
                        except Exception:
                            pass
            placed.append(system)
            placed.extend(beams)
        return placed


def _workplane_depth(plane, face):
    if face not in WORKPLANE_FACES:
        raise ValueError('Choose Top or Bottom for the framing workplane.')
    if face == 'top':
        return 0.0
    layers = getattr(plane, 'layers', None) or []
    depth = sum(max(0.0, float(getattr(layer, 'width', 0.0) or 0.0))
                for layer in layers)
    if depth <= 1e-9:
        raise ValueError('Cannot determine host thickness for BOTTOM work plane. '
                         'Check the host compound structure.')
    return depth


def _set_beam_z_justification(beam, face):
    """Revit Z Justification: Top=0, Center=1, Origin=2, Bottom=3.

    Some Revit beam-system members lock this parameter; report those explicitly.
    """
    from Autodesk.Revit.DB import BuiltInParameter
    try:
        mode = beam.get_Parameter(BuiltInParameter.YZ_JUSTIFICATION)
        if mode is not None and not mode.IsReadOnly:
            mode.Set(0)  # Uniform
        param = beam.get_Parameter(BuiltInParameter.Z_JUSTIFICATION)
        expected = z_justification_value(face)
        if param is None:
            return False
        if not param.IsReadOnly:
            param.Set(expected)
        return param.AsInteger() == expected
    except Exception:
        return False


def _apply_system_elevation(system, offset):
    """Use the Revit BeamSystem elevation property, fail rather than misplace."""
    try:
        system.Elevation = offset
        return
    except Exception:
        pass
    # Avoid locale-dependent LookupParameter names.
    from Autodesk.Revit.DB import BuiltInParameter
    parameter = system.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM)
    if parameter is not None and not parameter.IsReadOnly and parameter.Set(offset):
        return
    raise RuntimeError('Could not set the flat Beam System roof-layer elevation.')
