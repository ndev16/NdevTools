# -*- coding: utf-8 -*-
"""RoofPilot ownership stored privately in Revit Extensible Storage.

No project shared parameters are bound, and the built-in Comments field is
never used for new ownership tags. Legacy old roof tags in Comments can still
be READ when replacing roofs previously framed with older versions.
"""

TRACKING_PREFIX = "NDEV_ROOF_FRAME|"
LEGACY_TRACKING_PREFIX = "WF_FRAME|"
TRACKING_PREFIXES = (TRACKING_PREFIX, LEGACY_TRACKING_PREFIX)

# Keep the GUID constant forever for recognition across Revit sessions.
SCHEMA_GUID = "5a70453a-4291-5971-a6ad-26bc7e4b13ed"
_SCHEMA_NAME = "RoofPilotOwnershipV1"
_FIELD_NAME = "TrackingData"


def _schema(create=False):
    """Find or create the private Revit schema. Call create in a transaction."""
    from System import Guid, String
    from Autodesk.Revit.DB.ExtensibleStorage import Schema, SchemaBuilder, AccessLevel

    unique_id = Guid(SCHEMA_GUID)
    result = Schema.Lookup(unique_id)
    if result is not None:
        return result
    if not create:
        return None

    builder = SchemaBuilder(unique_id)
    builder.SetSchemaName(_SCHEMA_NAME)
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.AddSimpleField(_FIELD_NAME, String)
    return builder.Finish()


def ensure_private_tracking():
    """Fail before modifying framing if private Revit ownership is unavailable."""
    return _schema(create=True) is not None


def tag_instance(instance, host_info, member):
    """Tag in invisible Extensible Storage, NEVER in Identity Data/Comments."""
    from System import String
    from Autodesk.Revit.DB.ExtensibleStorage import Entity

    schema = _schema(create=True)
    field = schema.GetField(_FIELD_NAME)
    entity = Entity(schema)
    entity.Set[String](field, _build_tracking_line(host_info, member))
    instance.SetEntity(entity)
    return True


def get_tracking_data(element):
    """Read private tags first; read legacy Comments tags only for migration."""
    from System import String
    from Autodesk.Revit.DB import BuiltInParameter

    try:
        schema = _schema(create=False)
        if schema is not None:
            entity = element.GetEntity(schema)
            if entity is not None and entity.IsValid():
                value = entity.Get[String](schema.GetField(_FIELD_NAME))
                if value and value.startswith(TRACKING_PREFIX):
                    return _parse_tracking_line(value)
    except Exception:
        # Older family instances may not have the new Extensible Storage.
        pass

    # Backward compatibility only: never writes a metadata line to Comments.
    try:
        param = element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        value = param.AsString() if param is not None else ""
        for line in (value or "").splitlines():
            # Some early versions concatenated user text and tracking
            # without a newline, e.g. "ROOFNDEV_ROOF_FRAME|kind=roof|...".
            for prefix in TRACKING_PREFIXES:
                index = line.find(prefix)
                if index >= 0:
                    parsed = _parse_tracking_line(line[index:])
                    if parsed.get('kind') == 'roof' and parsed.get('host'):
                        return parsed
    except Exception:
        pass
    return None


def get_tracked_members_for_hosts(doc, hosts):
    """Return tracked structural framing instances for the given hosts."""
    from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

    host_keys = set()
    for host in hosts:
        host_key = host_key_for_element(host)
        if host_key is not None:
            host_keys.add(host_key)

    if not host_keys:
        return []

    collector = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_StructuralFraming)
        .WhereElementIsNotElementType()
    )

    matches = []
    for element in collector:
        tracking = get_tracking_data(element)
        if tracking is None:
            continue
        key = tracking.get("kind"), tracking.get("host")
        if key in host_keys:
            matches.append(element)
    return matches


def delete_tracked_members_for_hosts(doc, hosts, allowed_kinds=None):
    """Delete tracked generated members owned by the given host elements."""
    from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

    host_keys = set()
    for host in hosts:
        host_key = host_key_for_element(host)
        if host_key is not None:
            host_keys.add(host_key)

    if not host_keys:
        return 0

    if allowed_kinds is not None:
        allowed_kinds = set(allowed_kinds)
        host_keys = set(
            key for key in host_keys
            if key[0] in allowed_kinds
        )
        if not host_keys:
            return 0

    # Delete owned native Beam Systems first: a BeamSystem deletion will also
    # delete its generated beams. Collecting by class avoids a category-name
    # difference across Revit versions and project languages.
    try:
        from Autodesk.Revit.DB import BeamSystem
        system_candidates = list(FilteredElementCollector(doc).OfClass(BeamSystem)
                                 .WhereElementIsNotElementType())
    except Exception:
        system_candidates = []

    other_candidates = []
    for category in _tracked_delete_categories(BuiltInCategory):
        try:
            other_candidates.extend(list(
                FilteredElementCollector(doc).OfCategory(category)
                .WhereElementIsNotElementType()))
        except Exception:
            continue

    # Deduplicate tracked ids; beam systems first to avoid leaving empty
    # managed systems behind when replacing a flat roof or switching modes.
    system_ids, other_ids, seen_ids = [], [], set()
    for candidates, destination in ((system_candidates, system_ids),
                                     (other_candidates, other_ids)):
        for element in candidates:
            tracking = get_tracking_data(element)
            if tracking is None or (tracking.get('kind'), tracking.get('host')) not in host_keys:
                continue
            element_id = getattr(element, 'Id', None)
            if element_id is None:
                continue
            id_value = _element_id_value(element_id)
            if id_value in seen_ids:
                continue
            seen_ids.add(id_value)
            destination.append(element_id)

    deleted = 0
    for element_id in system_ids + other_ids:
        try:
            # doc.Delete can return an empty collection for ids already
            # removed with their parent BeamSystem; don't count these.
            if doc.GetElement(element_id) is None:
                continue
            if doc.Delete(element_id) is not None:
                deleted += 1
        except Exception:
            pass
    return deleted


def host_key_for_element(element):
    """Return the tracking key for a selected host element."""
    from Autodesk.Revit.DB import BuiltInCategory, Floor, RoofBase, Wall

    if isinstance(element, Wall):
        return ("wall", str(_element_id_value(element.Id)))
    if isinstance(element, Floor):
        return ("floor", str(_element_id_value(element.Id)))
    if _category_matches(element, BuiltInCategory.OST_Ceilings):
        return ("ceiling", str(_element_id_value(element.Id)))
    if isinstance(element, RoofBase):
        return ("roof", str(_element_id_value(element.Id)))
    return None


def get_nearby_structural_framing(doc, element, tolerance=0.5):
    """Fallback collector for legacy untracked framing near a host."""
    from Autodesk.Revit.DB import (
        BoundingBoxIntersectsFilter,
        BuiltInCategory,
        FilteredElementCollector,
        Outline,
        XYZ,
    )

    bounding_box = element.get_BoundingBox(None)
    if bounding_box is None:
        return []

    outline = Outline(
        XYZ(
            bounding_box.Min.X - tolerance,
            bounding_box.Min.Y - tolerance,
            bounding_box.Min.Z - tolerance,
        ),
        XYZ(
            bounding_box.Max.X + tolerance,
            bounding_box.Max.Y + tolerance,
            bounding_box.Max.Z + tolerance,
        ),
    )
    collector = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_StructuralFraming)
        .WhereElementIsNotElementType()
        .WherePasses(BoundingBoxIntersectsFilter(outline))
    )
    return list(collector)


def _build_tracking_line(host_info, member):
    """Create a single-line tracking record."""
    values = [
        ("kind", getattr(member, "host_kind", None) or getattr(host_info, "kind", None)),
        ("host", _element_id_value(getattr(member, "host_id", None) or getattr(host_info, "element_id", None))),
        ("member", member.member_type),
        ("layer", getattr(member, "layer_index", None)),
    ]

    parts = [TRACKING_PREFIX.rstrip("|")]
    for key, value in values:
        if value is None or value == "":
            continue
        parts.append("%s=%s" % (key, value))
    return "|".join(parts)


def _parse_tracking_line(line):
    """Parse a tracking line into a dictionary."""
    result = {}
    parts = line.split("|")
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key] = value
    return result


def _category_matches(element, category_id):
    """Return True when the element belongs to the given category."""
    category = getattr(element, "Category", None)
    if category is None:
        return False

    current_id = getattr(category.Id, "IntegerValue", getattr(category.Id, "Value", None))
    target_id = int(category_id)
    return current_id == target_id


def _tracked_delete_categories(built_in_category):
    """Return categories that can contain generated framing elements."""
    names = (
        "OST_StructuralFraming",
        "OST_StructuralColumns",
        "OST_StructuralFramingSystem",
        "OST_StructuralFramingSystems",
    )
    categories = []
    seen = set()
    for name in names:
        category = getattr(built_in_category, name, None)
        if category is None:
            continue
        try:
            key = int(category)
        except Exception:
            key = name
        if key in seen:
            continue
        seen.add(key)
        categories.append(category)
    return categories


def _element_id_value(element_id):
    """Return a numeric id for an ElementId or raw integer."""
    if element_id is None:
        return None
    try:
        integer_types = (int, long)
    except NameError:
        integer_types = (int,)
    if isinstance(element_id, integer_types):
        return element_id
    return getattr(element_id, "IntegerValue", getattr(element_id, "Value", None))
