# -*- coding: utf-8 -*-
"""Match type + editable instance parameters using stable parameter identities."""
from __future__ import unicode_literals
from pyrevit import DB
from System import Int32, Int64, Double, String
from Autodesk.Revit.UI.Selection import ISelectionFilter

import match_properties_core as core


def id_value(element_id):
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


def element_id(value):
    try:
        return DB.ElementId(Int64(value))
    except (TypeError, OverflowError):
        return DB.ElementId(Int32(value))


def is_matchable_instance(element):
    """Native instances include annotation, detail, analytical and model categories."""
    return (element is not None and not isinstance(element, DB.ElementType)
            and element.Category is not None and getattr(element, 'IsValidObject', True))


def is_model_instance(element):
    """Compatibility alias for earlier callers of the selection helper."""
    return is_matchable_instance(element)


class ModelFilter(ISelectionFilter):
    def __init__(self, source=None):
        self.source = source

    def AllowElement(self, element):
        if not is_matchable_instance(element):
            return False
        if self.source is None:
            return True
        return (element.Id != self.source.Id and element.Category.Id == self.source.Category.Id
                and element.GetType().FullName == self.source.GetType().FullName)

    def AllowReference(self, reference, position):
        return False


def label(element):
    try:
        name = DB.Element.Name.GetValue(element)
    except Exception:
        name = element.Category.Name if element.Category else 'Element'
    return '{} [ID {}]'.format(name, id_value(element.Id))


def family_key(element):
    if isinstance(element, DB.FamilyInstance):
        return element.Symbol.Family.UniqueId
    return element.GetType().FullName


def read_value(parameter):
    storage = str(parameter.StorageType)
    if storage == 'String':
        return parameter.AsString() or ''
    if not parameter.HasValue:
        return None
    if storage == 'Double':
        return parameter.AsDouble()
    if storage == 'Integer':
        return parameter.AsInteger()
    if storage == 'ElementId':
        return id_value(parameter.AsElementId())
    return None


def describe(doc, parameter):
    pid = id_value(parameter.Id)
    shared_guid = str(parameter.GUID) if parameter.IsShared else None
    definition = parameter.Definition
    builtin = str(getattr(definition, 'BuiltInParameter', ''))
    try:
        data_type = definition.GetDataType().TypeId
    except AttributeError:
        data_type = str(definition.ParameterType)
    global_id = DB.ElementId.InvalidElementId
    try:
        global_id = parameter.GetAssociatedGlobalParameter()
    except Exception:
        pass
    return {'key': core.identity(pid, shared_guid, builtin), 'name': definition.Name,
            'builtin': builtin, 'storage': str(parameter.StorageType), 'data_type': data_type,
            'value': read_value(parameter), 'has_value': bool(parameter.HasValue),
            'readonly': bool(parameter.IsReadOnly), 'global_parameter': global_id != DB.ElementId.InvalidElementId,
            'project_parameter': pid > 0 and isinstance(doc.GetElement(parameter.Id), DB.ParameterElement)}


ANNOTATION_FIELDS = (
    ('TextNote', 'HorizontalAlignment', 'Text horizontal alignment', 'Integer', 'TextAlignment'),
    ('TextNote', 'KeepRotatedTextReadable', 'Keep rotated text readable', 'Integer', 'Boolean'),
    ('TextNote', 'Width', 'Text box width', 'Double', 'SheetLength'),
    ('IndependentTag', 'HasLeader', 'Tag leader', 'Integer', 'Boolean'),
    ('IndependentTag', 'TagOrientation', 'Tag orientation', 'Integer', 'TagOrientation'),
    ('SpatialElementTag', 'HasLeader', 'Tag leader', 'Integer', 'Boolean'),
)
ANNOTATION_PARAMETER_ALIASES = {
    ('TextNote', 'HorizontalAlignment'): ('TEXT_ALIGN_HORZ', 'TEXT_ALIGNMENT'),
    ('TextNote', 'KeepRotatedTextReadable'): ('KEEP_READABLE',),
    ('IndependentTag', 'HasLeader'): ('LEADER_LINE',),
    ('IndependentTag', 'TagOrientation'): ('TAG_ORIENTATION_PARAM',),
    ('SpatialElementTag', 'HasLeader'): ('LEADER_LINE',),
}


def is_instance_of(element, class_name):
    api_type = getattr(DB, class_name, None)
    return api_type is not None and isinstance(element, api_type)


def api_property_writable(element, name):
    try:
        prop = element.GetType().GetProperty(name)
        return prop is not None and prop.GetSetMethod() is not None
    except AttributeError:
        # Offline test objects have ordinary attributes rather than CLR properties.
        return hasattr(element, name)


def annotation_value(element, row):
    value = getattr(element, row['api_property'])
    return float(value) if row['storage'] == 'Double' else int(value)


def annotation_target_row(target, row):
    try:
        result = dict(row)
        result['value'] = annotation_value(target, row)
        result['readonly'] = not api_property_writable(target, row['api_property'])
        return result
    except (AttributeError, TypeError, ValueError):
        return None


def append_annotation_rows(source, rows, skipped):
    for class_name, prop, name, storage, data_type in ANNOTATION_FIELDS:
        if not is_instance_of(source, class_name):
            continue
        try:
            if prop == 'Width' and not source.IsTextWrappingActive:
                skipped.append({'name': name, 'reason': 'Unwrapped text width is calculated; target width retained.'})
                continue
            if not api_property_writable(source, prop):
                continue
            row = {'key': 'api:' + class_name + '.' + prop, 'name': name, 'builtin': '',
                   'storage': storage, 'data_type': data_type, 'api_property': prop,
                   'api_value': getattr(source, prop), 'has_value': True}
            row['value'] = annotation_value(source, row)
            reason = core.source_skip(row)
            if reason:
                skipped.append({'name': name, 'reason': reason})
                continue
            # Show one checkbox for the property, not a second parameter alias
            # that would conflict with the unchecked-property protection.
            aliases = ANNOTATION_PARAMETER_ALIASES.get((class_name, prop), ())
            rows[:] = [r for r in rows if r['builtin'] not in aliases]
            rows.append(row)
        except Exception as error:
            skipped.append({'name': name, 'reason': 'Could not read: ' + str(error)})


def source_snapshot(doc, source):
    rows, skipped = [], []
    # Retain palette fields and supplement writable parameters omitted by its ordered view.
    parameters = list(source.GetOrderedParameters())
    included = set(id_value(p.Id) for p in parameters)
    for parameter in source.Parameters:
        if id_value(parameter.Id) not in included and not parameter.IsReadOnly and getattr(parameter.Definition, 'Visible', True):
            parameters.append(parameter)
            included.add(id_value(parameter.Id))
    for parameter in parameters:
        try:
            row = describe(doc, parameter)
            if row['builtin'] == 'PHASE_DEMOLISHED' and row['storage'] == 'ElementId' and not row['has_value']:
                # The palette's demolition "None" is an explicit state, not missing input.
                row['value'], row['has_value'] = -1, True
            reason = core.source_skip(row)
            if reason:
                skipped.append({'name': row['name'], 'reason': reason})
            else:
                rows.append(row)
        except Exception as error:
            skipped.append({'name': parameter.Definition.Name, 'reason': 'Could not read: ' + str(error)})
    # Structural Usage is also an API property. Its palette parameter can be
    # absent/read-only even though FamilyInstance.StructuralUsage is writable.
    if isinstance(source, DB.FamilyInstance):
        try:
            usage = source.StructuralUsage
            if int(usage) != 0:
                rows = [r for r in rows if r['builtin'] not in
                        ('INSTANCE_STRUCT_USAGE_PARAM', 'STRUCTURAL_USAGE_PARAM')]
                rows.append({'key': 'api:StructuralUsage', 'name': 'Structural Usage',
                             'builtin': 'INSTANCE_STRUCT_USAGE_PARAM', 'storage': 'Integer',
                             'data_type': 'StructuralInstanceUsage', 'value': int(usage),
                             'api_value': usage, 'has_value': True})
        except AttributeError:
            pass
        except Exception as error:
            skipped.append({'name': 'Structural Usage', 'reason': 'Could not read API property: ' + str(error)})
    append_annotation_rows(source, rows, skipped)
    return {'type_id': id_value(source.GetTypeId()), 'family': family_key(source),
            'id': id_value(source.Id), 'rows': sorted(rows, key=core.priority), 'skipped': skipped,
            'label': label(source), 'category_id': id_value(source.Category.Id),
            'class': source.GetType().FullName}


def target_parameters(doc, target):
    parameters = {}
    for parameter in target.Parameters:
        pid = id_value(parameter.Id)
        key = core.identity(pid, str(parameter.GUID) if parameter.IsShared else None)
        if key in parameters:
            parameters[key] = None
        else:
            parameters[key] = parameter
    return parameters


def write_value(parameter, storage, value):
    if storage == 'String':
        return parameter.Set(String(value or ''))
    if storage == 'Integer':
        return parameter.Set(Int32(value))
    if storage == 'Double':
        return parameter.Set(Double(value))
    if storage == 'ElementId':
        return parameter.Set(element_id(value))
    raise ValueError('Unsupported storage type.')


class TargetFailures(DB.IFailuresPreprocessor):
    def __init__(self):
        self.warnings, self.errors = [], []

    def PreprocessFailures(self, accessor):
        for failure in accessor.GetFailureMessages():
            message = failure.GetDescriptionText()
            if failure.GetSeverity() == DB.FailureSeverity.Warning:
                self.warnings.append(message)
                accessor.DeleteWarning(failure)  # dismiss message, never delete elements
            else:
                self.errors.append(message)
        return DB.FailureProcessingResult.ProceedWithRollBack if self.errors else DB.FailureProcessingResult.Continue


def apply_structural_usage(doc, target, row):
    sub = DB.SubTransaction(doc)
    try:
        if int(target.StructuralUsage) == row['value']:
            return 'Already matches', 'Verified through StructuralUsage API.'
        # Do not override an explicitly associated global parameter.
        for parameter in target.Parameters:
            if str(getattr(parameter.Definition, 'BuiltInParameter', '')) in (
                    'INSTANCE_STRUCT_USAGE_PARAM', 'STRUCTURAL_USAGE_PARAM'):
                if describe(doc, parameter)['global_parameter']:
                    return 'Skipped', 'Controlled by a global parameter.'
        sub.Start()
        target.StructuralUsage = row['api_value']
        doc.Regenerate()
        if int(target.StructuralUsage) != row['value']:
            raise ValueError('Revit recalculated Structural Usage to a different value.')
        if sub.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Revit did not commit Structural Usage.')
        return 'Copied', 'Applied through StructuralUsage API.'
    except Exception as error:
        if sub.GetStatus() == DB.TransactionStatus.Started:
            sub.RollBack()
        if type(error).__name__ == 'RegenerationFailedException':
            raise
        return 'Skipped', str(error)
    finally:
        sub.Dispose()


def apply_field(doc, target, source_row, source_family):
    if source_row['key'] == 'api:StructuralUsage':
        return apply_structural_usage(doc, target, source_row)
    if source_row.get('api_property'):
        return apply_annotation_field(doc, target, source_row)
    parameters = target_parameters(doc, target)
    key = source_row['key']
    parameter = parameters.get(key)
    if key in parameters and parameter is None:
        return 'Skipped', 'Multiple target parameters share this identity.'
    target_row = describe(doc, parameter) if parameter is not None else None
    if (target_row and source_row['storage'] == target_row['storage'] and
            source_row['data_type'] == target_row['data_type'] and
            core.equal_values(source_row['storage'], source_row['value'], target_row['value'])):
        return 'Already matches', ''
    reason = core.compatibility(source_row, target_row, source_family == family_key(target))
    if reason:
        return 'Skipped', reason
    sub = DB.SubTransaction(doc)
    sub.Start()
    try:
        accepted = write_value(parameter, source_row['storage'], source_row['value'])
        if not accepted and not core.equal_values(source_row['storage'], source_row['value'], read_value(parameter)):
            raise ValueError('Revit did not accept this value.')
        doc.Regenerate()
        if not core.equal_values(source_row['storage'], source_row['value'], read_value(parameter)):
            raise ValueError('Revit recalculated a different value.')
        if sub.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Revit did not commit this field.')
        return 'Copied', ''
    except Exception as error:
        if sub.GetStatus() == DB.TransactionStatus.Started:
            sub.RollBack()
        if type(error).__name__ == 'RegenerationFailedException':
            raise
        return 'Skipped', str(error)
    finally:
        sub.Dispose()


def apply_annotation_field(doc, target, row):
    target_row = annotation_target_row(target, row)
    if target_row and core.equal_values(row['storage'], row['value'], target_row['value']):
        return 'Already matches', ''
    reason = core.compatibility(row, target_row)
    if reason:
        return 'Skipped', reason
    sub = DB.SubTransaction(doc)
    sub.Start()
    try:
        setattr(target, row['api_property'], row['api_value'])
        doc.Regenerate()
        if not core.equal_values(row['storage'], row['value'], annotation_value(target, row)):
            raise ValueError('Revit recalculated a different annotation value.')
        if sub.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Revit did not commit the annotation property.')
        return 'Copied', ''
    except Exception as error:
        if sub.GetStatus() == DB.TransactionStatus.Started:
            sub.RollBack()
        if type(error).__name__ == 'RegenerationFailedException':
            raise
        return 'Skipped', str(error)
    finally:
        sub.Dispose()


def apply_phases(doc, target, rows):
    """Copy the valid created/demolished pair together, avoiding order conflicts."""
    phases = {r['builtin']: r for r in rows if r['builtin'] in core.PHASE_FIELDS}
    results = []
    if not phases:
        return results
    parameters = target_parameters(doc, target)
    if all(parameters.get(row['key']) is not None and
           core.equal_values(row['storage'], row['value'], read_value(parameters[row['key']]))
           for row in phases.values()):
        return [{'name': row['name'], 'key': row['key'], 'status': 'Already matches', 'reason': ''}
                for row in phases.values()]
    sub = DB.SubTransaction(doc)
    sub.Start()
    try:
        parameters = target_parameters(doc, target)
        for row in phases.values():
            parameter = parameters.get(row['key'])
            reason = core.compatibility(row, describe(doc, parameter) if parameter else None)
            if reason:
                raise ValueError(reason)
        demo = target.get_Parameter(DB.BuiltInParameter.PHASE_DEMOLISHED)
        # Clear only when both values are supplied, so partial phase copying cannot erase demolition.
        if len(phases) == 2 and demo is not None and not demo.IsReadOnly:
            demo.Set(DB.ElementId.InvalidElementId)
        for field in ('PHASE_CREATED', 'PHASE_DEMOLISHED'):
            row = phases.get(field)
            if row is None:
                continue
            parameter = parameters[row['key']]
            write_value(parameter, row['storage'], row['value'])
        doc.Regenerate()
        for row in phases.values():
            if not core.equal_values(row['storage'], row['value'], read_value(parameters[row['key']])):
                raise ValueError('Phase values did not match after regeneration.')
        if sub.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Phase changes did not commit.')
        results = [{'name': row['name'], 'key': row['key'], 'status': 'Copied', 'reason': ''} for row in phases.values()]
    except Exception as error:
        if sub.GetStatus() == DB.TransactionStatus.Started:
            sub.RollBack()
        if type(error).__name__ == 'RegenerationFailedException':
            raise
        results = [{'name': row['name'], 'key': row['key'], 'status': 'Skipped', 'reason': str(error)} for row in phases.values()]
    finally:
        sub.Dispose()
    return results


def match_target(doc, snapshot, target):
    report = {'id': id_value(target.Id), 'status': 'Skipped', 'type_status': 'Not changed', 'fields': [], 'warnings': []}
    if target.Id == element_id(snapshot['id']):
        report['error'] = 'Source is excluded from targets.'
        return report
    if not is_matchable_instance(target) or id_value(target.Category.Id) != snapshot['category_id'] or target.GetType().FullName != snapshot['class']:
        report['error'] = 'Target must be the same category and element class as the source.'
        return report
    if target.GroupId != DB.ElementId.InvalidElementId:
        report['error'] = 'Group member retained; edit its group separately.'
        return report
    if target.Pinned:
        report['error'] = 'Pinned element retained; unpin it to match properties.'
        return report
    transaction = DB.Transaction(doc, 'Match Properties - {}'.format(report['id']))
    handler = TargetFailures()
    transaction.Start()
    try:
        original_text = target.Text if is_instance_of(target, 'TextNote') else None
        protected = [r for r in source_snapshot(doc, target)['rows']
                     if r['key'] in snapshot.get('excluded_keys', set())]
        options = transaction.GetFailureHandlingOptions()
        options.SetClearAfterRollback(True)
        options.SetFailuresPreprocessor(handler)
        transaction.SetFailureHandlingOptions(options)
        wanted_type = element_id(snapshot['type_id']) if snapshot.get('copy_type', True) else target.GetTypeId()
        if target.GetTypeId() == wanted_type:
            report['type_status'] = 'Already matches'
        elif wanted_type != DB.ElementId.InvalidElementId:
            if not target.IsValidType(wanted_type):
                raise ValueError('Source type is not valid for this target; target retained.')
            replacement_id = target.ChangeTypeId(wanted_type)
            if replacement_id != DB.ElementId.InvalidElementId:
                raise ValueError('This type change would replace the element; target retained.')
            doc.Regenerate()
            report['type_status'] = 'Matched source type'
        else:
            report['type_status'] = 'Source has no assignable element type'

        report['fields'].extend(apply_phases(doc, target, snapshot['rows']))
        deferred = []
        for row in snapshot['rows']:
            if row['builtin'] in core.PHASE_FIELDS:
                continue
            status, reason = apply_field(doc, target, row, snapshot['family'])
            field = {'name': row['name'], 'key': row['key'], 'status': status, 'reason': reason}
            report['fields'].append(field)
            if status == 'Skipped':
                deferred.append((row, field))
        # Later constraints can also reset fields that succeeded earlier. Reconcile all
        # non-phase fields, bounded to two passes so conflicting dependencies cannot loop.
        fields_by_key = {field['key']: field for field in report['fields']}
        for attempt in range(2):
            changed = False
            for row in snapshot['rows']:
                if row['builtin'] in core.PHASE_FIELDS:
                    continue
                field = fields_by_key[row['key']]
                status, reason = apply_field(doc, target, row, snapshot['family'])
                if status == 'Copied':
                    changed = True
                if not (status == 'Already matches' and field['status'] == 'Copied'):
                    field['status'], field['reason'] = status, reason
            if not changed:
                break
        doc.Regenerate()
        current_rows = {r['key']: r for r in source_snapshot(doc, target)['rows']}
        for original in protected:
            current = current_rows.get(original['key'])
            if current is None or not core.equal_values(original['storage'], original['value'], current['value']):
                raise ValueError('Selected changes affect unchecked property "{}"; target retained.'.format(original['name']))
        if wanted_type != DB.ElementId.InvalidElementId and target.GetTypeId() != wanted_type:
            raise ValueError('Target type did not remain matched.')
        if original_text is not None and target.Text != original_text:
            raise ValueError('Text content changed unexpectedly; target retained.')
        if transaction.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('; '.join(handler.errors) or 'Revit rejected this target.')
        report['status'] = 'Updated'
        report['warnings'] = handler.warnings
        # Verify the final committed state, including dependencies changed by later fields.
        parameters = target_parameters(doc, target)
        source_by_key = {row['key']: row for row in snapshot['rows']}
        for field in report['fields']:
            parameter = parameters.get(field['key'])
            source_row = source_by_key[field['key']]
            if field['key'] == 'api:StructuralUsage':
                target_row = dict(source_row)
                target_row['value'] = int(target.StructuralUsage)
            elif source_row.get('api_property'):
                target_row = annotation_target_row(target, source_row)
            else:
                target_row = describe(doc, parameter) if parameter is not None else None
            matches = (target_row is not None and source_row['storage'] == target_row['storage'] and
                       source_row['data_type'] == target_row['data_type'] and
                       core.equal_values(source_row['storage'], source_row['value'], target_row['value']))
            if not matches and field['status'] in ('Copied', 'Already matches'):
                field['status'] = 'Not matched'
                field['reason'] = 'A dependent setting or Revit recalculation changed this value.'
            field['reason'] = '{} Source: {}; target: {}.'.format(
                field.get('reason', ''), source_row['value'], target_row['value'] if target_row else '<missing>')
        if any(f['status'] in ('Skipped', 'Not matched') for f in report['fields']):
            report['status'] = 'Updated with exceptions'
        elif report['type_status'] in ('Already matches', 'Source has no assignable element type') and all(
                f['status'] == 'Already matches' for f in report['fields']):
            report['status'] = 'Already matches'
        return report
    except Exception as error:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        committed = transaction.GetStatus() == DB.TransactionStatus.Committed
        report['status'] = 'Updated; verification interrupted' if committed else 'Retained (target transaction rolled back)'
        report['error'] = str(error)
        report['warnings'] = handler.warnings
        if not committed:
            report['type_status'] = 'Retained'
            for field in report['fields']:
                if field['status'] == 'Copied':
                    field['status'] = 'Rolled back'
        if type(error).__name__ == 'RegenerationFailedException':
            report['fatal'] = True
        return report
    finally:
        transaction.Dispose()


def is_level_reference(doc, row):
    if core.is_level_assignment(row):
        return True
    return (row['storage'] == 'ElementId' and row['value'] is not None and hasattr(DB, 'Level')
            and isinstance(doc.GetElement(element_id(row['value'])), DB.Level))


def run(doc, source, targets, progress=None, exclude_levels=False, selected_keys=None, copy_type=True):
    snapshot = source_snapshot(doc, source)
    snapshot['copy_type'] = copy_type
    snapshot['excluded_keys'] = set()
    if selected_keys is not None:
        selected = set(selected_keys)
        snapshot['excluded_keys'] = set(r['key'] for r in snapshot['rows'] if r['key'] not in selected)
        for row in snapshot['rows']:
            if row['key'] not in selected:
                snapshot['skipped'].append({'name': row['name'], 'reason': 'Unchecked; not copied.'})
        snapshot['rows'] = [r for r in snapshot['rows'] if r['key'] in selected]
    if exclude_levels:
        retained = []
        for row in snapshot['rows']:
            level_reference = is_level_reference(doc, row)
            if level_reference:
                snapshot['excluded_keys'].add(row['key'])
                snapshot['skipped'].append({'name': row['name'],
                                           'reason': 'Excluded by Exclude Levels option; target level retained.'})
            else:
                retained.append(row)
        snapshot['rows'] = retained
    result = {'document': doc.Title, 'source_label': snapshot['label'], 'source_skips': snapshot['skipped'],
              'targets': [], 'cancelled': False}
    group = DB.TransactionGroup(doc, 'NdevTools - Match Properties')
    group.Start()
    try:
        seen = set()
        for index, target in enumerate(targets):
            target_id = id_value(target.Id)
            if target_id in seen or target_id == snapshot['id']:
                continue
            seen.add(target_id)
            if progress:
                progress.update_progress(index, len(targets))
                if progress.cancelled:
                    result['cancelled'] = True
                    break
            report = match_target(doc, snapshot, target)
            result['targets'].append(report)
            if report.get('fatal'):
                break
    finally:
        if group.GetStatus() == DB.TransactionStatus.Started:
            status = group.Assimilate()
            if status != DB.TransactionStatus.Committed:
                for target in result['targets']:
                    target['status'] = 'Group not committed'
                    target['type_status'] = 'Retained'
                    for field in target['fields']:
                        if field['status'] == 'Copied':
                            field['status'] = 'Rolled back'
        group.Dispose()
    return result
