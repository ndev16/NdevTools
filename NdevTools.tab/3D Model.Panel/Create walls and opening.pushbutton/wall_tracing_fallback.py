# -*- coding: utf-8 -*-
"""Controlled Door/Window parameter fallback. Never replaces successful geometry."""
import math
from pyrevit import DB
from wall_tracing_math import TOL, rectangle_metrics


class FallbackFailure(ValueError):
    def __init__(self,status,message):
        ValueError.__init__(self,message)
        self.status=status


def length_value(parameter,positive=True):
    if parameter is None or not parameter.HasValue or parameter.StorageType != DB.StorageType.Double:
        return None
    try:
        if parameter.Definition.GetDataType() != DB.SpecTypeId.Length:
            return None
        value=parameter.AsDouble()
        if math.isnan(value) or math.isinf(value) or (positive and value<=TOL):
            return None
        return value
    except Exception:
        return None


def builtin(element,name):
    try:
        return element.get_Parameter(getattr(DB.BuiltInParameter,name))
    except Exception:
        return None


def dimension(instance,symbol,builtins,names):
    # Instance built-ins -> type built-ins -> named instance -> named type.
    # Rough values never override a valid nominal built-in without cut evidence.
    for element,scope in ((instance,'INSTANCE'),(symbol,'TYPE')):
        if element is None:
            continue
        for name in builtins:
            parameter=builtin(element,name)
            value=length_value(parameter)
            if value is not None:
                return value,scope+'_BUILTIN',name
    for element,scope in ((instance,'INSTANCE'),(symbol,'TYPE')):
        if element is None:
            continue
        for name in names:
            try:
                matches=list(element.GetParameters(name))
            except Exception:
                continue
            # Duplicate names are ambiguous even if one happens to be a length.
            if len(matches)!=1:
                continue
            value=length_value(matches[0])
            if value is not None:
                return value,scope+'_PARAMETER',name
    raise FallbackFailure('PARAMETER_NOT_FOUND','No reliable positive length parameter: '+', '.join(names))


def resolve_insert(wall,item):
    ids=item.get('insert_ids',[])
    if len(ids)!=1:
        raise FallbackFailure('AMBIGUOUS_HOST','Fallback requires one unambiguous source insert.')
    # String overload resolves UniqueIds, not numeric ElementIds.
    return wall.Document.GetElement(DB.ElementId(int(ids[0])))


def parameter_bounds(wall,instance,item):
    if not isinstance(instance,DB.FamilyInstance) or instance.Category is None:
        raise FallbackFailure('SKIPPED','Only Door and Window instances support parameter fallback.')
    category=instance.Category.Id
    is_door=category == DB.ElementId(DB.BuiltInCategory.OST_Doors)
    is_window=category == DB.ElementId(DB.BuiltInCategory.OST_Windows)
    if not (is_door or is_window):
        raise FallbackFailure('SKIPPED','Category is not a Door or Window; dimensions are not guessed.')
    # FindInserts can include a neighbor's cutter. Explicit ownership avoids
    # stamping the same nominal Width x Height into every wall near a corner.
    host=instance.Host
    if host is None or host.Id != wall.Id:
        item['host_validation']='PARAMETER_FALLBACK_AMBIGUOUS_HOST'
        raise FallbackFailure('AMBIGUOUS_HOST','PARAMETER_FALLBACK_AMBIGUOUS_HOST: this wall is not the confirmed insert Host. Geometry must resolve secondary wall cuts.')
    item['host_validation']='PASS: explicit source-wall Host'
    location=instance.Location
    if not isinstance(location,DB.LocationPoint):
        raise FallbackFailure('LOCATION_FAILURE','Insert has no reliable insertion point.')
    point=location.Point
    if any(math.isnan(v) or math.isinf(v) for v in (point.X,point.Y,point.Z)):
        raise FallbackFailure('LOCATION_FAILURE','Insert point contains invalid coordinates.')
    axis=wall.Location.Curve
    origin=axis.GetEndPoint(0)
    along=point.Subtract(origin).DotProduct(axis.Direction)
    depth=abs(point.Subtract(origin).DotProduct(wall.Orientation))
    if depth>wall.Width/2+TOL or along < -TOL or along > axis.Length+TOL:
        raise FallbackFailure('LOCATION_FAILURE','Insertion point is outside source-wall length/thickness.')
    symbol=wall.Document.GetElement(instance.GetTypeId())
    prefix='DOOR' if is_door else 'WINDOW'
    width,source,name=dimension(instance,symbol,[prefix+'_WIDTH'],
        ['Width','Opening Width','Rough Width','Rough Opening Width'])
    item.update(width_source=source,width_parameter=name,width_value=width)
    height,source,name=dimension(instance,symbol,[prefix+'_HEIGHT'],
        ['Height','Opening Height','Rough Height','Rough Opening Height'])
    item.update(height_source=source,height_parameter=name,height_value=height)
    bottom=point.Z
    bottom_source='INSTANCE_LOCATION'
    if is_window:
        level=wall.Document.GetElement(instance.LevelId)
        if not isinstance(level,DB.Level):
            raise FallbackFailure('LOCATION_FAILURE','Window level unavailable; sill elevation cannot be established.')
        offset=None
        for name in ('INSTANCE_SILL_HEIGHT_PARAM','INSTANCE_ELEVATION_PARAM'):
            offset=length_value(builtin(instance,name),positive=False)
            if offset is not None:
                bottom=level.ProjectElevation+offset
                bottom_source='SILL_HEIGHT' if name=='INSTANCE_SILL_HEIGHT_PARAM' else 'LEVEL_PLUS_OFFSET'
                item['bottom_parameter']=name
                break
        if offset is None:
            raise FallbackFailure('LOCATION_FAILURE','Window sill/base offset unavailable; insertion Z is not assumed to be the sill.')
    item.update(bottom_source=bottom_source,center_source='INSTANCE_LOCATION projected along mapped destination wall')
    bounds=along-width/2,along+width/2,bottom,bottom+height
    if bounds[0]<-TOL or bounds[1]>axis.Length+TOL:
        raise FallbackFailure('INVALID_DIMENSIONS','Parameter opening extends beyond source-wall ends.')
    from wall_tracing_openings import wall_envelope
    envelope=wall_envelope(wall)
    if bottom < envelope[2]-TOL or bottom+height > envelope[3]+TOL:
        raise FallbackFailure('INVALID_DIMENSIONS','Parameter opening extends outside source-wall vertical bounds.')
    return bounds


def apply_parameter_fallbacks(wall,items):
    """All primary detection already ran. Never inspect parameters for success."""
    for item in items:
        success=item['valid'] or item['result']=='DUPLICATE'
        item.update(primary_geometry='SUCCESS' if success else 'FAILED',
                    primary_failure='' if success else item['reason'],fallback_attempted='NO',
                    detection_source='GEOMETRY' if success else 'NONE',
                    width_source='GEOMETRY' if success else 'NONE',
                    height_source='GEOMETRY' if success else 'NONE',
                    bottom_source='GEOMETRY' if success else 'NONE',
                    center_source='GEOMETRY' if success else 'NONE',host_validation='GEOMETRY' if success else 'NOT_CHECKED')
        if success:
            if item.get('bounds'):
                item['width_value'],item['height_value'],center=rectangle_metrics(item['bounds'])
            continue
        item['fallback_attempted']='YES'
        try:
            instance=resolve_insert(wall,item)
            bounds=parameter_bounds(wall,instance,item)
            item.update(bounds=bounds,valid=True,rectangle_valid=True,result='PENDING',
                        detection_source='PARAMETER_FALLBACK',reason='Controlled parameter fallback validated; primary failure retained below.')
        except FallbackFailure as error:
            item.update(valid=False,result=error.status,reason=str(error))
        except Exception as error:
            item.update(valid=False,result='GEOMETRY_FAILURE',reason='Parameter fallback: {}: {}'.format(type(error).__name__,error))
    # Geometry successes are created first. Original ordering within each stage
    # remains stable. Existing-opening checks protect both stages on reruns.
    return sorted(items,key=lambda item:item.get('detection_source')=='PARAMETER_FALLBACK')
