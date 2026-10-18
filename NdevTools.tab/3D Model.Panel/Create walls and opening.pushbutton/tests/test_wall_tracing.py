"""Offline regression tests. Revit API fakes do not replace in-Revit acceptance."""
import math
import os
import sys
import types
import unittest
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from wall_tracing_math import structure_layer, rectangle_bounds, opening_offsets, suggest_wall_type, combine_opening_bounds, boundary_notches


class XYZ:
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z
    def Add(self, p):
        return XYZ(self.X+p.X, self.Y+p.Y, self.Z+p.Z)
    def Subtract(self, p):
        return XYZ(self.X-p.X, self.Y-p.Y, self.Z-p.Z)
    def Multiply(self, s):
        return XYZ(self.X*s, self.Y*s, self.Z*s)
    def DotProduct(self, p):
        return self.X*p.X+self.Y*p.Y+self.Z*p.Z
    def GetLength(self):
        return math.sqrt(self.DotProduct(self))
    def Normalize(self):
        return self.Multiply(1/self.GetLength())
    def DistanceTo(self, p):
        return self.Subtract(p).GetLength()
XYZ.BasisZ = XYZ(0,0,1)


class Transform:
    def __init__(self, angle=0, translation=None, mirror=False):
        c,s = math.cos(angle), math.sin(angle)
        self.BasisX = XYZ(c,s,0)
        self.BasisY = XYZ(-s,c,0).Multiply(-1 if mirror else 1)
        self.BasisZ = XYZ.BasisZ
        self.translation = translation or XYZ(0,0,0)
    def OfVector(self,p):
        return self.BasisX.Multiply(p.X).Add(self.BasisY.Multiply(p.Y)).Add(self.BasisZ.Multiply(p.Z))
    def OfPoint(self,p):
        return self.OfVector(p).Add(self.translation)
    @staticmethod
    def CreateTranslation(p):
        return Transform(translation=p)


class Line:
    def __init__(self,a,b):
        self.a,self.b = a,b
        self.Direction = b.Subtract(a).Normalize()
        self.Length = a.DistanceTo(b)
    def GetEndPoint(self,i):
        return self.a if i == 0 else self.b
    def CreateTransformed(self,t):
        return Line(t.OfPoint(self.a),t.OfPoint(self.b))
    def Project(self,p):
        point = self.a.Add(self.Direction.Multiply(p.Subtract(self.a).DotProduct(self.Direction)))
        return types.SimpleNamespace(XYZPoint=point)


class LocationCurve:
    def __init__(self, curve):
        self.Curve = curve


class Parameter:
    def __init__(self,value,storage='integer'):
        self.value,self.StorageType,self.IsReadOnly = value,storage,False
    def AsInteger(self): return self.value
    def AsDouble(self): return self.value
    def AsElementId(self): return self.value
    def AsValueString(self): return str(self.value)
    def Set(self,value):
        changed = self.value != value
        self.value = value
        return changed


class Params:
    def __getattr__(self,name): return name


class Wall:
    def __init__(self,flip=False,reverse=False,reference=0):
        a,b = XYZ(0,0,0),XYZ(10,0,0)
        self.Location = LocationCurve(Line(b,a) if reverse else Line(a,b))
        self.Orientation = XYZ(0,-1 if flip else 1,0)
        self.Flipped = flip
        self.SketchId = -1
        self.params = {'WALL_KEY_REF_PARAM':Parameter(reference),
                       'WALL_BASE_CONSTRAINT':Parameter(10,'id'),
                       'WALL_HEIGHT_TYPE':Parameter(20,'id')}
    def get_Parameter(self,p): return self.params.get(p)
    def GetTypeId(self): return 1
    def GetDependentElements(self, filter): return []


class Opening:
    pass


db = types.SimpleNamespace(XYZ=XYZ,Line=Line,LocationCurve=LocationCurve,Transform=Transform,
    WallLocationLine=types.SimpleNamespace(WallCenterline=0,CoreCenterline=1,
        FinishFaceExterior=2,FinishFaceInterior=3,CoreExterior=4,CoreInterior=5),
    BuiltInParameter=Params(),ElementId=types.SimpleNamespace(InvalidElementId=-1),
    IFailuresPreprocessor=object,Opening=Opening,FamilyInstance=type('FamilyInstance',(),{}),
    ElementClassFilter=lambda cls: cls,
    WallCrossSection=types.SimpleNamespace(Vertical=0),
    StorageType=types.SimpleNamespace(ElementId='id',Integer='integer',Double='double'))
sys.modules['clr'] = types.ModuleType('clr')
sys.modules['pyrevit'] = types.SimpleNamespace(DB=db,forms=None)
sys.modules['Autodesk'] = types.ModuleType('Autodesk')
sys.modules['Autodesk.Revit'] = types.ModuleType('Revit')
sys.modules['Autodesk.Revit.Exceptions'] = types.SimpleNamespace(RegenerationFailedException=type('RegenerationFailedException',(Exception,),{}))
import wall_tracing_engine as engine
sys.modules['System'] = types.ModuleType('System')
sys.modules['System.Collections'] = types.ModuleType('Collections')
sys.modules['System.Collections.Generic'] = types.SimpleNamespace(List=list)
import wall_tracing_openings as cut_geometry
import wall_tracing_fallback as parameter_fallback


class GeometryTests(unittest.TestCase):
    def test_door_window_fallback_positions_and_host_rejection(self):
        class Level:
            def __init__(self,z): self.ProjectElevation=z
        class Location:
            Point=XYZ(5,0,2)
        class Length(Parameter):
            HasValue=True
            Definition=types.SimpleNamespace(GetDataType=lambda:'length')
        replacements=dict(ElementId=int,Level=Level,LocationPoint=Location,
            BuiltInCategory=types.SimpleNamespace(OST_Doors=100,OST_Windows=101),SpecTypeId=types.SimpleNamespace(Length='length'))
        prior=dict((k,getattr(db,k,None)) for k in replacements)
        try:
            for k,v in replacements.items(): setattr(db,k,v)
            wall=types.SimpleNamespace(Id=1,Width=1,Orientation=XYZ(0,1,0),Location=LocationCurve(Line(XYZ(0,0,0),XYZ(10,0,0))))
            wall_params=dict(WALL_BASE_CONSTRAINT=Parameter(10,'id'),WALL_HEIGHT_TYPE=Parameter(20,'id'),
                             WALL_BASE_OFFSET=Parameter(0,'double'),WALL_TOP_OFFSET=Parameter(0,'double'))
            wall.get_Parameter=lambda name:wall_params.get(name)
            symbol=types.SimpleNamespace(get_Parameter=lambda name:None,GetParameters=lambda name:[])
            wall.Document=types.SimpleNamespace(GetElement=lambda eid:{10:Level(0),20:Level(12),30:symbol}.get(eid))
            instance=db.FamilyInstance(); instance.Host=wall; instance.Location=Location()
            instance.Category=types.SimpleNamespace(Id=100); instance.GetTypeId=lambda:30
            values=dict(DOOR_WIDTH=Length(3,'double'),DOOR_HEIGHT=Length(7,'double'))
            instance.get_Parameter=lambda name:values.get(name)
            item={}
            self.assertEqual(parameter_fallback.parameter_bounds(wall,instance,item),(3.5,6.5,2,9))
            self.assertEqual(item['bottom_source'],'INSTANCE_LOCATION')
            instance.Category.Id=101; instance.LevelId=10
            values.update(WINDOW_WIDTH=Length(4,'double'),WINDOW_HEIGHT=Length(4,'double'),INSTANCE_SILL_HEIGHT_PARAM=Length(3,'double'))
            self.assertEqual(parameter_fallback.parameter_bounds(wall,instance,item),(3,7,3,7))
            self.assertEqual(item['bottom_source'],'SILL_HEIGHT')
            instance.Host=types.SimpleNamespace(Id=2)
            with self.assertRaises(parameter_fallback.FallbackFailure) as caught:
                parameter_fallback.parameter_bounds(wall,instance,{})
            self.assertEqual(caught.exception.status,'AMBIGUOUS_HOST')
        finally:
            for k,v in prior.items():
                if v is None: delattr(db,k)
                else: setattr(db,k,v)
    def test_geometry_success_and_duplicate_never_enter_parameter_fallback(self):
        old=parameter_fallback.resolve_insert
        try:
            parameter_fallback.resolve_insert=lambda *args:self.fail('Successful geometry must bypass parameters')
            success=dict(valid=True,result='PENDING',reason='PASS',bounds=(0,3,0,7))
            duplicate=dict(valid=False,result='DUPLICATE',reason='Already found',bounds=(0,3,0,7))
            parameter_fallback.apply_parameter_fallbacks(None,[success,duplicate])
            for item in (success,duplicate):
                self.assertEqual(item['fallback_attempted'],'NO')
                self.assertEqual(item['detection_source'],'GEOMETRY')
                self.assertEqual(item['bounds'],(0,3,0,7))
        finally:
            parameter_fallback.resolve_insert=old

    def test_parameter_priority_and_length_validation(self):
        old=getattr(db,'SpecTypeId',None)
        db.SpecTypeId=types.SimpleNamespace(Length='length')
        class Length(Parameter):
            HasValue=True
            Definition=types.SimpleNamespace(GetDataType=lambda:'length')
        try:
            inst=types.SimpleNamespace(get_Parameter=lambda name:Length(3,'double'),GetParameters=lambda name:[Length(9,'double')])
            symbol=types.SimpleNamespace(get_Parameter=lambda name:Length(4,'double'))
            self.assertEqual(parameter_fallback.dimension(inst,symbol,['DOOR_WIDTH'],['Width']),(3,'INSTANCE_BUILTIN','DOOR_WIDTH'))
            inst.get_Parameter=lambda name:None
            self.assertEqual(parameter_fallback.dimension(inst,symbol,['DOOR_WIDTH'],['Width']),(4,'TYPE_BUILTIN','DOOR_WIDTH'))
            symbol.get_Parameter=lambda name:None
            self.assertEqual(parameter_fallback.dimension(inst,symbol,['DOOR_WIDTH'],['Width']),(9,'INSTANCE_PARAMETER','Width'))
            for bad in (0,-2,float('nan'),float('inf')):
                self.assertIsNone(parameter_fallback.length_value(Length(bad,'double')))
            p=Length(3,'double'); p.Definition=types.SimpleNamespace(GetDataType=lambda:'angle')
            self.assertIsNone(parameter_fallback.length_value(p))
        finally:
            if old is None: delattr(db,'SpecTypeId')
            else: db.SpecTypeId=old

    def test_fallback_failure_preserves_primary_reason(self):
        old=parameter_fallback.resolve_insert
        try:
            def ambiguous(*args): raise parameter_fallback.FallbackFailure('AMBIGUOUS_HOST','Unconfirmed wall')
            parameter_fallback.resolve_insert=ambiguous
            item=dict(valid=False,result='NO_MATCHING_CUT',reason='Original geometry failure')
            parameter_fallback.apply_parameter_fallbacks(None,[item])
            self.assertEqual(item['primary_failure'],'Original geometry failure')
            self.assertEqual(item['result'],'AMBIGUOUS_HOST')
            self.assertFalse(item['valid'])
        finally:
            parameter_fallback.resolve_insert=old

    def test_fallback_results_ordered_after_geometry(self):
        resolve,bounds=parameter_fallback.resolve_insert,parameter_fallback.parameter_bounds
        try:
            parameter_fallback.resolve_insert=lambda *args:object()
            parameter_fallback.parameter_bounds=lambda *args:(4,7,2,6)
            failed=dict(valid=False,result='NO_MATCHING_CUT',reason='Missing face')
            good=dict(valid=True,result='PENDING',reason='PASS',bounds=(0,3,0,7))
            results=parameter_fallback.apply_parameter_fallbacks(None,[failed,good])
            self.assertIs(results[0],good)
            self.assertEqual(results[1]['detection_source'],'PARAMETER_FALLBACK')
            self.assertEqual(good['bounds'],(0,3,0,7))
        finally:
            parameter_fallback.resolve_insert,parameter_fallback.parameter_bounds=resolve,bounds
    def test_spatial_fallback_requires_actual_void_cut_relationship(self):
        good,bad=db.FamilyInstance(),db.FamilyInstance()
        good.Id=types.SimpleNamespace(IntegerValue=901)
        bad.Id=types.SimpleNamespace(IntegerValue=902)
        class Collector:
            def OfClass(self,cls): return self
            def WherePasses(self,filter): return [good,bad]
        replacements=dict(FilteredElementCollector=lambda doc:Collector(),
            BoundingBoxIntersectsFilter=lambda outline:outline,Outline=lambda a,b:(a,b),
            InstanceVoidCutUtils=types.SimpleNamespace(InstanceVoidCutExists=lambda wall,element:element is good))
        prior=dict((k,getattr(db,k,None)) for k in replacements)
        try:
            for k,v in replacements.items(): setattr(db,k,v)
            wall=Wall(); wall.Document=object(); wall.FindInserts=lambda *args:[]
            wall.get_BoundingBox=lambda view:types.SimpleNamespace(Min=XYZ(0,-1,0),Max=XYZ(10,1,8),Transform=Transform())
            self.assertEqual(cut_geometry.real_inserts(wall),[(good,'CUTTING_ELEMENT_FALLBACK')])
        finally:
            for k,v in prior.items():
                if v is None: delattr(db,k)
                else: setattr(db,k,v)

    def test_zero_insert_extent_does_not_scan_unrelated_wall_faces(self):
        original=cut_geometry.real_inserts
        try:
            insert=types.SimpleNamespace(Id=types.SimpleNamespace(IntegerValue=99),Category=None,
                get_BoundingBox=lambda view:types.SimpleNamespace(Min=XYZ(2,0,0),Max=XYZ(2,1,7),Transform=Transform()))
            cut_geometry.real_inserts=lambda wall:[(insert,'HOSTED_INSERT')]
            wall=Wall(); wall.get_Geometry=lambda options:self.fail('Invalid insert must not trigger a full face scan')
            rows=cut_geometry.scan_wall_openings(wall)
            self.assertEqual(rows[0]['result'],'INVALID_PROJECTED_INSERT_EXTENT')
            self.assertFalse(rows[0]['valid'])
        finally:
            cut_geometry.real_inserts=original

    def test_insert_first_scan_accepts_local_segmented_hole(self):
        def make_loop(points):
            xyz=[XYZ(x,0,z) for x,z in points]
            return [Line(p,xyz[(i+1)%len(xyz)]) for i,p in enumerate(xyz)]
        class Face:
            Area=64
            FaceNormal=XYZ(0,1,0)
            Origin=XYZ(0,0,0)
            def GetEdgesAsCurveLoops(self):
                return [make_loop([(0,0),(10,0),(10,8),(0,8)]),
                        make_loop([(2,2),(3,2),(4,2),(4,4),(4,6),(3,6),(2,6),(2,4)])]
        class Faces(list):
            @property
            def Size(self): return len(self)
        class Solid:
            Volume=64
        Solid.Faces=Faces([Face()])
        class Level:
            def __init__(self,elevation): self.ProjectElevation=elevation
        replacements=dict(Solid=Solid,PlanarFace=Face,GeometryInstance=type('Instance',(),{}),
                          Options=type('Options',(),{}),ViewDetailLevel=types.SimpleNamespace(Fine=1),Level=Level)
        prior=dict((k,getattr(db,k,None)) for k in replacements)
        original_discovery=cut_geometry.real_inserts
        try:
            for k,v in replacements.items(): setattr(db,k,v)
            wall=Wall()
            wall.Document=types.SimpleNamespace(GetElement=lambda eid: Level(0 if eid==10 else 8))
            wall.params.update(WALL_BASE_OFFSET=Parameter(0,'double'),WALL_TOP_OFFSET=Parameter(0,'double'))
            wall.get_Geometry=lambda options: [None,Solid()]
            wall.FindInserts=lambda *args: []
            insert=types.SimpleNamespace(Id=types.SimpleNamespace(IntegerValue=777),Category=None,
                get_BoundingBox=lambda view: types.SimpleNamespace(Min=XYZ(1.9,-1,1.9),Max=XYZ(4.1,1,6.1),Transform=Transform()))
            cut_geometry.real_inserts=lambda w:[(insert,'HOSTED_INSERT')]
            rows=cut_geometry.scan_wall_openings(wall)
            accepted=[r for r in rows if r['valid']]
            self.assertEqual(len(accepted),1)
            self.assertEqual(accepted[0]['bounds'],(2,4,2,6))
            self.assertEqual(accepted[0]['raw_edges'],8)
            self.assertEqual(accepted[0]['insert_ids'],['777'])
        finally:
            cut_geometry.real_inserts=original_discovery
            for k,v in prior.items():
                if v is None: delattr(db,k)
                else: setattr(db,k,v)

    def test_no_insert_means_no_geometry_scan_and_no_candidates(self):
        wall=Wall()
        wall.Document=types.SimpleNamespace(GetElement=lambda eid:None)
        wall.FindInserts=lambda *args:[]
        wall.get_Geometry=lambda options:self.fail('Must not inspect faces without real inserts')
        self.assertEqual(cut_geometry.scan_wall_openings(wall),[])

    def test_local_search_excludes_distant_holes_and_wall_end_gaps(self):
        regions=[[dict(points=[(0.1,0),(10,0),(10,8),(0.1,8)],curved=False,edges=4),
                  dict(points=[(2,2),(4,2),(4,6),(2,6)],curved=False,edges=4),
                  dict(points=[(7,2),(9,2),(9,6),(7,6)],curved=False,edges=4)]]
        rows=cut_geometry.local_candidates(regions,(1.9,4.1,1.9,6.1),(0,10,0,8))
        self.assertEqual([r['bounds'] for r in rows if r['valid']],[(2,4,2,6)])

    def test_insert_local_door_bottom_notch(self):
        regions=[[dict(points=[(0,0),(2,0),(2,7),(4,7),(4,0),(10,0),(10,8),(0,8)],curved=False,edges=8)]]
        rows=cut_geometry.local_candidates(regions,(1.9,4.1,0,7.1),(0,10,0,8))
        self.assertEqual([r['bounds'] for r in rows if r['valid']],[(2,4,0,7)])

    def test_window_clipping_does_not_invent_smaller_opening(self):
        regions=[[dict(points=[(0,0),(2,0),(2,7),(6,7),(6,0),(10,0),(10,8),(0,8)],curved=False,edges=8)]]
        rows=cut_geometry.local_candidates(regions,(1.9,4.1,0,7.1),(0,10,0,8))
        self.assertFalse(any(r['valid'] for r in rows))

    def test_full_height_wall_end_gap_rejected_even_near_insert(self):
        regions=[[dict(points=[(0.2,0),(10,0),(10,8),(0.2,8)],curved=False,edges=4)]]
        rows=cut_geometry.local_candidates(regions,(0,0.3,0,8),(0,10,0,8))
        self.assertFalse(any(r['valid'] for r in rows))
        self.assertTrue(any(r['result']=='WALL_JOIN_OR_BOUNDARY' for r in rows))

    def test_arbitrary_segment_counts_follow_rectangle_sides(self):
        for count in (2,3,8,20):
            points=[(i*4.0/count,0) for i in range(count)]
            points += [(4,i*6.0/count) for i in range(count)]
            points += [(4-i*4.0/count,6) for i in range(count)]
            points += [(0,6-i*6.0/count) for i in range(count)]
            self.assertEqual(rectangle_bounds(points),(0,4,0,6))

    def test_notch_at_bottom_and_top(self):
        outer=[(0,0),(2,0),(2,4),(4,4),(4,0),(10,0),(10,8),(0,8)]
        self.assertEqual(boundary_notches([[outer]],(0,10,0,8)),[((2,4,0,4),True)])
        flipped=[(x,8-z) for x,z in outer]
        self.assertEqual(boundary_notches([[flipped]],(0,10,0,8)),[((2,4,4,8),True)])

    def test_notch_at_start_and_end(self):
        outer=[(0,0),(10,0),(10,8),(0,8),(0,6),(3,6),(3,2),(0,2)]
        self.assertEqual(boundary_notches([[outer]],(0,10,0,8)),[((0,3,2,6),True)])
        mirrored=[(10-x,z) for x,z in outer]
        self.assertEqual(boundary_notches([[mirrored]],(0,10,0,8)),[((7,10,2,6),True)])

    def test_inner_hole_not_misreported_as_boundary_notch(self):
        outer=[(0,0),(10,0),(10,8),(0,8)]
        hole=[(2,2),(4,2),(4,6),(2,6)]
        self.assertEqual(boundary_notches([[outer,hole]],(0,10,0,8)),[])
        self.assertEqual(boundary_notches([[outer,hole]],(0,10,0,8),include_inner=True),[((2,4,2,6),True)])

    def test_concave_missing_notch_is_not_bounding_rectangle(self):
        outer=[(0,0),(2,0),(2,6),(3,6),(3,3),(4,3),(4,0),(10,0),(10,8),(0,8)]
        self.assertFalse(boundary_notches([[outer]],(0,10,0,8))[0][1])

    def test_separate_face_pieces_reveal_full_height_cut(self):
        a=[(0,0),(2,0),(2,8),(0,8)]
        b=[(4,0),(10,0),(10,8),(4,8)]
        self.assertEqual(boundary_notches([[a],[b]],(0,10,0,8)),[((2,4,0,8),True)])

    def test_diagonal_outer_boundary_is_not_approximated(self):
        with self.assertRaises(ValueError):
            boundary_notches([[[(0,0),(10,0),(10,8),(1,8)]]],(0,10,0,8))

    def test_null_geometry_yields_no_solids(self):
        self.assertEqual(list(cut_geometry.solids(None)),[])
        self.assertEqual(list(cut_geometry.solids([None])),[])

    def test_candidate_diagnostics_include_segment_counts(self):
        item=cut_geometry.candidate([(0,0),(2,0),(4,0),(4,3),(4,6),(2,6),(0,6),(0,3)],8,'inner-loop')
        self.assertTrue(item['valid'])
        item['result']='EXISTING'
        text=cut_geometry.diagnostic_text(item,'123','456')
        self.assertIn('Raw edges: 8',text)
        self.assertIn('Raw points: 8',text)
        self.assertIn('Creation result: EXISTING',text)

    def test_tiny_duplicate_profile_vertices_are_removed(self):
        self.assertEqual(rectangle_bounds([(0,0),(0,0),(2,0),(2.000001,0),(4,0),(4,6),(0,6)]),(0,4,0,6))

    def test_nearly_collinear_vertices_stay_within_global_tolerance(self):
        self.assertEqual(rectangle_bounds([(0,0),(2,0.00001),(4,0),(4,6),(0,6)]),(0,4,0,6))

    def test_small_corner_artifact_simplifies(self):
        bounds = rectangle_bounds([(0,0),(4,0),(4,5.99999),(3.99999,6),(0,6)])
        self.assertAlmostEqual(bounds[1],4,places=4)
        self.assertAlmostEqual(bounds[3],6,places=4)

    def test_actual_notch_is_never_bounding_box_approximated(self):
        with self.assertRaises(ValueError):
            rectangle_bounds([(0,0),(4,0),(4,6),(3,6),(3,5.99),(2,5.99),(2,6),(0,6)])

    def test_arch_is_not_flattened(self):
        points = [(0,0),(4,0),(4,4)] + [(2+2*math.cos(i*math.pi/40),4+2*math.sin(i*math.pi/40)) for i in range(1,41)]
        with self.assertRaises(ValueError): rectangle_bounds(points)

    def test_backtracking_outline_rejected(self):
        with self.assertRaises(ValueError):
            rectangle_bounds([(0,0),(3,0),(1,0),(4,0),(4,6),(0,6)])

    def test_cut_loop_projected_in_rotated_wall_coordinates(self):
        transform = Transform(math.pi/4,XYZ(100,80,0))
        axis = Line(transform.OfPoint(XYZ(0,0,0)),transform.OfPoint(XYZ(10,0,0)))
        local = [(2,0,3),(4,0,3),(6,0,3),(6,0,7),(2,0,7)]
        points = [transform.OfPoint(XYZ(*p)) for p in local]
        loop = [Line(p,points[(i+1)%len(points)]) for i,p in enumerate(points)]
        bounds = cut_geometry.classify_loop(loop,dict(origin=axis.GetEndPoint(0),axis=axis))
        for actual,expected in zip(bounds,(2,6,3,7)):
            self.assertAlmostEqual(actual,expected,places=8)

    def test_cut_projection_handles_reversed_wall_axis(self):
        axis = Line(XYZ(10,0,0),XYZ(0,0,0))
        points = [XYZ(2,0,3),XYZ(6,0,3),XYZ(6,0,7),XYZ(2,0,7)]
        loop = [Line(p,points[(i+1)%4]) for i,p in enumerate(points)]
        self.assertEqual(cut_geometry.classify_loop(loop,dict(origin=axis.a,axis=axis)),(4,8,3,7))

    def test_combine_at_exact_gap_uses_extreme_elevations(self):
        self.assertEqual(combine_opening_bounds([(0,3,0,7),(4,6,3,9)],1),
                         [((0,6,0,9),[0,1])])

    def test_combine_leaves_gap_above_limit_separate(self):
        self.assertEqual(len(combine_opening_bounds([(0,3,0,7),(4.001,6,0,7)],1)),2)

    def test_combine_transitive_chain_and_unsorted_input(self):
        self.assertEqual(combine_opening_bounds([(8,10,2,8),(0,3,0,7),(4,7,1,9)],1),
                         [((0,10,0,9),[1,2,0])])

    def test_combine_zero_gap_touching_and_overlapping(self):
        self.assertEqual(combine_opening_bounds([(0,4,1,7),(3,5,0,6),(5,7,4,9)],0),
                         [((0,7,0,9),[0,1,2])])

    def test_combine_different_heights_uses_horizontal_gap(self):
        self.assertEqual(combine_opening_bounds([(0,2,0,2),(2.5,4,5,7)],0.5),
                         [((0,4,0,7),[0,1])])

    def test_combine_empty_singleton_and_input_preserved(self):
        bounds = [(4,6,2,9)]
        self.assertEqual(combine_opening_bounds([],1),[])
        self.assertEqual(combine_opening_bounds(bounds,1),[((4,6,2,9),[0])])
        self.assertEqual(bounds,[(4,6,2,9)])

    def test_combine_rejects_invalid_gap(self):
        for gap in (-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError):
                combine_opening_bounds([],gap)

    def test_rectangle_with_split_sides_is_accepted(self):
        points = [(0,0),(2,0),(4,0),(4,3),(4,6),(2,6),(0,6),(0,3)]
        self.assertEqual(rectangle_bounds(points),(0,4,0,6))
        self.assertEqual(rectangle_bounds(points[::-1]),(0,4,0,6))

    def test_split_profile_does_not_hide_a_notch(self):
        with self.assertRaises(ValueError):
            rectangle_bounds([(0,0),(4,0),(4,6),(2,6),(2,5),(1,5),(1,6),(0,6)])

    def test_allow_joins_enables_both_wall_ends(self):
        calls = []
        old = getattr(db,'WallUtils',None)
        wall = object()
        try:
            db.WallUtils = types.SimpleNamespace(AllowWallJoinAtEnd=lambda w,e: calls.append((w,e)))
            engine.allow_wall_joins(wall)
            self.assertEqual(calls,[(wall,0),(wall,1)])
        finally:
            db.WallUtils = old

    def test_mapping_prefers_matching_structural_thickness(self):
        self.assertEqual(suggest_wall_type(0.5,[(0,1.0),(1,0.5),(2,0.75)]),(1,True))

    def test_mapping_flags_nearest_width_and_stable_ties(self):
        self.assertEqual(suggest_wall_type(0.5,[(0,0.4),(1,0.8)]),(0,False))
        self.assertEqual(suggest_wall_type(0.5,[(0,0.5),(1,0.5)]),(0,True))

    def test_mapping_does_not_suggest_without_reliable_width(self):
        self.assertEqual(suggest_wall_type(0,[(0,0.5)]),(None,False))
        self.assertEqual(suggest_wall_type(0.5,[]),(None,False))

    def test_new_wall_regenerated_before_orientation_and_after_flip(self):
        events = []
        class NewWall:
            @property
            def Orientation(self):
                if not events or events[-1] != 'regenerate':
                    raise RuntimeError('Can not get face for the specified Wall object')
                events.append('orientation')
                return XYZ(0,-1,0)
            def Flip(self):
                events.append('flip')
        doc = types.SimpleNamespace(Regenerate=lambda: events.append('regenerate'))
        engine.align_host_orientation(doc,NewWall(),XYZ(0,1,0),Transform())
        self.assertEqual(events,['regenerate','orientation','flip','regenerate'])

    def test_matching_orientation_does_not_flip(self):
        events = []
        doc = types.SimpleNamespace(Regenerate=lambda: events.append('regenerate'))
        wall = types.SimpleNamespace(Orientation=XYZ(0,1,0),Flip=lambda: events.append('flip'))
        engine.align_host_orientation(doc,wall,XYZ(0,1,0),Transform())
        self.assertEqual(events,['regenerate'])

    def test_report_exposes_and_saves_per_wall_diagnostics(self):
        result = dict((k,0) for k in ('levels','found','created','none','unsupported',
            'duplicates','detected','openings','skipped_openings','errors'))
        result.update(details=[('Level 1','Test wall','123','', 'Nonvertical wall',
                                'Cross-section=1; Angle=5 degrees')], wall_map={})
        captured = {}
        old_forms,old_temp = engine.forms,engine.tempfile.gettempdir
        try:
            with tempfile.TemporaryDirectory() as directory:
                engine.forms = types.SimpleNamespace(alert=lambda message,**kwargs: captured.update(message=message,**kwargs))
                engine.tempfile.gettempdir = lambda: directory
                output = types.SimpleNamespace(print_md=lambda value: None,print_table=lambda *a,**k: None)
                engine.report(result,output)
                self.assertIn('Source wall ID: 123',captured['expanded'])
                self.assertIn('Angle=5 degrees',captured['expanded'])
                report_dir = os.path.join(directory,'NdevTools-WallTracing')
                with open(os.path.join(report_dir,os.listdir(report_dir)[0]),encoding='utf-8') as stream:
                    self.assertIn('Nonvertical wall',stream.read())
        finally:
            engine.forms,engine.tempfile.gettempdir = old_forms,old_temp

    def test_wall_diagnostics_include_raw_cross_section_and_angle(self):
        wall = Wall()
        wall.params['WALL_CROSS_SECTION'] = Parameter(1)
        wall.params['WALL_SINGLE_SLANT_ANGLE_FROM_VERTICAL'] = Parameter(math.pi/6,'double')
        diagnostic = engine.wall_diagnostics(wall)
        self.assertIn('Cross-section=1 (raw=1)', diagnostic)
        self.assertIn('Angle from vertical=30.000000 degrees', diagnostic)
        self.assertIn('Top attached=not available', diagnostic)

    def test_vertical_check_uses_api_enum_not_assumed_zero(self):
        old = db.WallCrossSection.Vertical
        try:
            db.WallCrossSection.Vertical = 99
            wall = Wall()
            wall.params['WALL_CROSS_SECTION'] = Parameter(99)
            analysis = dict(supported=True,center=0,
                compound=types.SimpleNamespace(GetOffsetForLocationLine=lambda value: 0))
            engine.corrected_curve(wall,analysis,Transform())
        finally:
            db.WallCrossSection.Vertical = old

    def test_thickest_structural_layer_and_asymmetric_center(self):
        self.assertEqual(structure_layer([(0.25,False),(0.5,True),(0.75,True),(0.125,False)]), (2,0.75,-0.3125))

    def test_no_structure_never_guesses(self):
        with self.assertRaises(ValueError): structure_layer([(1,False),(0,True)])

    def test_all_location_lines_flip_direction_and_transform(self):
        for reference in range(6):
            for flip in (False,True):
                for reverse in (False,True):
                    for mirror in (False,True):
                        wall = Wall(flip,reverse,reference)
                        transform = Transform(math.pi/2,XYZ(100,50,12),mirror)
                        analysis = dict(supported=True,center=-0.3125,
                            compound=types.SimpleNamespace(GetOffsetForLocationLine=lambda ref: ref*0.17))
                        curve = engine.corrected_curve(wall,analysis,transform)
                        for i in (0,1):
                            expected = transform.OfPoint(wall.Location.Curve.GetEndPoint(i).Add(wall.Orientation.Multiply(-0.3125)))
                            self.assertLess(curve.GetEndPoint(i).DistanceTo(expected),1e-9)

    def test_tilted_link_rejected(self):
        t = Transform()
        t.BasisZ = XYZ(0,1,0)
        with self.assertRaises(ValueError): engine.check_transform(t)

    def test_invalid_location_line_rejected(self):
        analysis = dict(supported=True,center=0,compound=None)
        for reference in (-1,6):
            with self.assertRaises(ValueError):
                engine.corrected_curve(Wall(reference=reference),analysis,Transform())

    def test_scaled_link_rejected(self):
        t = Transform()
        t.BasisX = XYZ(2,0,0)
        with self.assertRaises(ValueError): engine.check_transform(t)

    def test_profiled_slanted_and_curved_wall_rejected(self):
        analysis = dict(supported=True,center=0,compound=None)
        wall = Wall()
        wall.SketchId = 15
        with self.assertRaises(ValueError): engine.corrected_curve(wall,analysis,Transform())
        wall = Wall()
        wall.params['WALL_CROSS_SECTION'] = Parameter(1)
        with self.assertRaises(ValueError): engine.corrected_curve(wall,analysis,Transform())
        wall = Wall()
        wall.Location.Curve = object()
        with self.assertRaises(ValueError): engine.corrected_curve(wall,analysis,Transform())

    def test_duplicate_axis_reversal_type_and_levels(self):
        wall = Wall(reverse=True)
        line = Wall().Location.Curve
        self.assertTrue(engine.duplicate([wall],line,1,10,20))
        self.assertFalse(engine.duplicate([wall],line,2,10,20))
        self.assertFalse(engine.duplicate([wall],line,1,10,30))
        self.assertFalse(engine.duplicate([wall],line.CreateTransformed(Transform(translation=XYZ(0,0.01,0))),1,10,20))

    def test_rectangle_and_reversed_winding(self):
        points = [(2,3),(6,3),(6,7),(2,7)]
        self.assertEqual(rectangle_bounds(points),(2,6,3,7))
        self.assertEqual(rectangle_bounds(points[::-1]),(2,6,3,7))

    def test_irregular_sloped_and_bowtie_rejected(self):
        for points in [[(0,0),(3,0),(2,4),(0,4)],[(0,0),(3,3),(3,0),(0,3)],[(0,0),(1,0),(1,0),(0,0)]]:
            with self.assertRaises(ValueError): rectangle_bounds(points)

    def test_opening_offsets_share_bottom_level(self):
        self.assertEqual(opening_offsets(100,107,100),(0,7))
        self.assertEqual(opening_offsets(103,107,100),(3,7))
        self.assertEqual(opening_offsets(103,107,90),(13,17))

    def test_unchanged_parameter_is_success(self):
        engine.set_param(Wall(),'WALL_KEY_REF_PARAM',0)

    def test_opening_transformed_position_and_both_constraints(self):
        transform = Transform(math.pi/2,XYZ(100,50,12))
        source = Wall()
        host = Wall()
        host.Location = LocationCurve(source.Location.Curve.CreateTransformed(
            Transform.CreateTranslation(XYZ(0,-0.3125,0))).CreateTransformed(transform))
        opening = Wall()
        opening.params.update({'WALL_BASE_OFFSET':Parameter(0.0,'double'),
                               'WALL_TOP_OFFSET':Parameter(0.0,'double')})
        captured = []
        def new_opening(h,a,b):
            captured.extend([a,b])
            return opening
        document = types.SimpleNamespace(Create=types.SimpleNamespace(NewOpening=new_opening),Regenerate=lambda: None)
        level = types.SimpleNamespace(Id=10,ProjectElevation=12)
        engine.create_opening(document,host,source,(2,6,3,7),transform,level,12,25)
        self.assertEqual(opening.params['WALL_BASE_CONSTRAINT'].value,10)
        self.assertEqual(opening.params['WALL_HEIGHT_TYPE'].value,10)
        self.assertEqual(opening.params['WALL_BASE_OFFSET'].value,3)
        self.assertEqual(opening.params['WALL_TOP_OFFSET'].value,7)
        self.assertLess(captured[0].DistanceTo(XYZ(100.3125,52,15)),1e-9)
        self.assertLess(captured[1].DistanceTo(XYZ(100.3125,56,19)),1e-9)
        # Repeating the repair must retain the already matching native opening.
        existing = Opening()
        existing.IsRectBoundary = True
        existing.BoundaryRect = list(reversed(captured))
        host.GetDependentElements = lambda filter: [123]
        document.GetElement = lambda eid: existing
        self.assertIsNone(engine.create_opening(document,host,source,(2,6,3,7),transform,level,12,25))
        self.assertEqual(len(captured),2)


if __name__ == '__main__':
    unittest.main()
