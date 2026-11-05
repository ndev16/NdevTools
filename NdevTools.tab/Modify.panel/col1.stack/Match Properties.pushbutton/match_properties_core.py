# -*- coding: utf-8 -*-
"""Pure comparison rules for Match Properties, compatible with IronPython 2.7."""
from __future__ import division, unicode_literals

import math

TYPE_FIELDS = frozenset(('ELEM_TYPE_PARAM', 'ELEM_FAMILY_PARAM', 'ELEM_FAMILY_AND_TYPE_PARAM', 'SYMBOL_ID_PARAM'))
PHASE_FIELDS = frozenset(('PHASE_CREATED', 'PHASE_DEMOLISHED'))
CALCULATED_FIELDS = frozenset(('CURVE_ELEM_LENGTH', 'STRUCTURAL_FRAME_CUT_LENGTH',
                              'HOST_VOLUME_COMPUTED', 'HOST_AREA_COMPUTED'))


def is_level_assignment(row):
    """Level references only; offsets and unrelated text fields remain copyable."""
    name = row.get('builtin', '')
    return row.get('storage') == 'ElementId' and (
        'LEVEL' in name or name in ('WALL_BASE_CONSTRAINT', 'WALL_HEIGHT_TYPE'))


def identity(parameter_id, shared_guid=None, builtin=None):
    # Never use translated display names: two different parameters may share one.
    if shared_guid:
        return ('shared', str(shared_guid).lower())
    if parameter_id < 0:
        return ('builtin', int(parameter_id))
    return ('definition', int(parameter_id))


def equal_values(storage, left, right):
    if storage == 'Double':
        if left is None or right is None:
            return left is right
        return abs(left - right) <= max(1e-9, 1e-10 * max(abs(left), abs(right)))
    if storage == 'String':
        return (left or '') == (right or '')
    return left == right


def priority(row):
    """Apply controllers/constraints before dependent offsets and dimensions."""
    name = row.get('builtin', '')
    if 'LEVEL' in name or name in ('WALL_BASE_CONSTRAINT', 'WALL_HEIGHT_TYPE'):
        order = 10
    elif 'USAGE' in name or 'CONNECTION' in name:
        order = 90  # Revit can reset these when geometry/constraints change.
    elif any(word in name for word in ('JUSTIFICATION', 'MODE', 'STYLE', 'STRUCTURAL_SIGNIFICANT')):
        order = 20
    elif 'OFFSET' in name or 'ELEVATION' in name:
        order = 40
    else:
        order = 30
    return (order, row['name'].lower(), str(row['key']))


def source_skip(row):
    if row.get('builtin') == 'TEXT_TEXT':
        return 'Text content is retained; match text style and properties instead.'
    if row.get('builtin') in TYPE_FIELDS:
        return 'Handled by matching the element type.'
    if row.get('builtin') in CALCULATED_FIELDS:
        return 'Calculated or read-only; Revit maintains this value.'
    if not row.get('has_value') and row['storage'] != 'String':
        return 'Source has no value; target is retained.'
    if row['storage'] not in ('String', 'Integer', 'Double', 'ElementId'):
        return 'Unsupported parameter storage.'
    if row['storage'] == 'Double' and (math.isnan(row['value']) or math.isinf(row['value'])):
        return 'Source value is not finite.'
    return None


def compatibility(source, target, same_family=True):
    if target is None:
        return 'Target does not expose this parameter.'
    if target.get('ambiguous'):
        return 'Multiple target parameters share this identity.'
    if source['key'] != target['key']:
        return 'Parameter identities differ.'
    if isinstance(source['key'], tuple) and source['key'][0] == 'definition' and not same_family and not source.get('project_parameter'):
        return 'Family-local parameters are not matched across different families.'
    if source['storage'] != target['storage']:
        return 'Parameter storage types differ.'
    if source.get('data_type') != target.get('data_type'):
        return 'Parameter data types or measurement units differ.'
    if target.get('readonly'):
        return 'Target parameter is read-only or inactive.'
    if target.get('global_parameter'):
        return 'Target is controlled by a global parameter.'
    return None


def format_report(result):
    lines = ['NdevTools - Match Properties', 'Version: 1.4.0',
             'Project: ' + result.get('document', ''), 'Source: ' + result.get('source_label', ''),
             'Targets processed: {}'.format(len(result.get('targets', []))),
             'Matching source type and editable model/annotation properties. Text-note content is retained.',
             'Calculated values are maintained by Revit. Constraints and offsets may change target elevations.', '']
    for row in result.get('source_skips', []):
        lines.append('SOURCE / {}: {}'.format(row['name'], row['reason']))
    for target in result.get('targets', []):
        lines.extend(['', 'TARGET {} - {}'.format(target['id'], target['status']),
                      'Type: ' + target.get('type_status', 'Not changed')])
        for field in target.get('fields', []):
            lines.append('  {} | {} | {}'.format(field['name'], field['status'], field.get('reason', '')))
        for warning in target.get('warnings', []):
            lines.append('  Revit warning: ' + warning)
        if target.get('error'):
            lines.append('  Error: ' + target['error'])
    if result.get('cancelled'):
        lines.extend(['', 'Cancelled. Earlier completed targets were retained.'])
    lines.extend(['', 'Type definitions were not edited. The source was not edited.'])
    return '\n'.join(lines)
