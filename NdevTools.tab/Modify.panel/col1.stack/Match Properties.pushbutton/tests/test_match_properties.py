# -*- coding: utf-8 -*-
"""Offline regression tests. The fake API is not a substitute for a Revit run."""
import copy
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import match_properties_core as core


class Bag(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class Id(object):
    def __init__(self, value):
        self.Value = int(value)

    def __eq__(self, other):
        return isinstance(other, Id) and self.Value == other.Value

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.Value)


Id.InvalidElementId = Id(-1)


class Parameter(object):
    def __init__(self, pid, name, value, storage='String', builtin='', readonly=False, shared=None, datatype=None):
        self.Id = Id(pid)
        self.Definition = Bag(Name=name, BuiltInParameter=builtin, GetDataType=lambda: Bag(TypeId=datatype or storage))
        self.value, self.StorageType, self.readonly = value, storage, readonly
        self.IsShared, self.GUID = bool(shared), shared
        self.global_id = Id.InvalidElementId
        self.fail, self.set_count, self.on_set = False, 0, None

    @property
    def HasValue(self):
        return self.value is not None

    @property
    def IsReadOnly(self):
        return self.readonly() if callable(self.readonly) else self.readonly

    def AsString(self):
        return self.value

    def AsDouble(self):
        return self.value

    def AsInteger(self):
        return self.value

    def AsElementId(self):
        return Id(self.value)

    def GetAssociatedGlobalParameter(self):
        return self.global_id

    def Set(self, value):
        if self.IsReadOnly or self.fail:
            raise ValueError('Cannot write this parameter')
        self.value = value.Value if isinstance(value, Id) else value
        self.set_count += 1
        if self.on_set:
            self.on_set(self.value)
        return True


class Element(object):
    def __init__(self, eid, parameters, type_id=10, category=5, family='family-a'):
        self.Id, self.Parameters = Id(eid), parameters
        self.Category = Bag(Id=Id(category), CategoryType='Model', Name='Beam')
        self.GroupId, self.Pinned = Id.InvalidElementId, False
        self.type_id, self.family = type_id, family
        self.valid_types, self.replacement = {10, 11}, False

    @property
    def Symbol(self):
        return Bag(Family=Bag(UniqueId=self.family))

    def GetOrderedParameters(self):
        return self.Parameters

    def GetType(self):
        return Bag(FullName='FamilyInstance')

    def GetTypeId(self):
        return Id(self.type_id)

    def IsValidType(self, type_id):
        return type_id.Value in self.valid_types

    def ChangeTypeId(self, type_id):
        self.type_id = type_id.Value
        self.family = 'family-a'
        return Id(999) if self.replacement else Id.InvalidElementId

    def get_Parameter(self, builtin):
        return next((p for p in self.Parameters if p.Definition.BuiltInParameter == builtin), None)


class Doc(object):
    Title = 'Offline test'

    def __init__(self, elements):
        self.elements = {e.Id.Value: e for e in elements}
        self.rejected_target = None
        self.warn_target = None
        self.after_regen = None
        self.project_params = set()

    def GetElement(self, eid):
        if eid.Value in self.project_params:
            return ParameterElement()
        return self.elements.get(eid.Value)

    def Regenerate(self):
        if self.after_regen:
            self.after_regen()

    def state(self):
        return {key: (e.type_id, e.family, [(p.value, p.set_count) for p in e.Parameters],
                      getattr(e, 'StructuralUsage', None),
                      {name: copy.deepcopy(getattr(e, name)) for name in
                       ('HorizontalAlignment', 'KeepRotatedTextReadable', 'Width', 'HasLeader', 'TagOrientation')
                       if hasattr(e, name)}) for key, e in self.elements.items()}

    def restore(self, state):
        for key, (tid, family, values, usage, annotation_values) in state.items():
            e = self.elements[key]
            e.type_id, e.family = tid, family
            if usage is not None:
                e.StructuralUsage = usage
            for p, (value, count) in zip(e.Parameters, values):
                p.value, p.set_count = value, count
            for name, value in annotation_values.items():
                setattr(e, name, value)


class Transaction(object):
    def __init__(self, doc, name=''):
        self.doc, self.name, self.status = doc, name, 'Uninitialized'
        self.handler = None

    def Start(self):
        self.saved = self.doc.state()
        self.status = 'Started'

    def GetStatus(self):
        return self.status

    def GetFailureHandlingOptions(self):
        return self

    def SetClearAfterRollback(self, value):
        return self

    def SetFailuresPreprocessor(self, handler):
        self.handler = handler
        return self

    def SetFailureHandlingOptions(self, options):
        pass

    def Commit(self):
        if self.doc.rejected_target is not None and self.name == 'Match Properties - {}'.format(self.doc.rejected_target):
            self.handler.errors.append('Rejected at commit')
            return self.RollBack()
        if self.doc.warn_target is not None and self.name == 'Match Properties - {}'.format(self.doc.warn_target):
            self.handler.warnings.append('Duplicate mark')
        self.status = 'Committed'
        return self.status

    def RollBack(self):
        self.doc.restore(self.saved)
        self.status = 'RolledBack'
        return self.status

    def Assimilate(self):
        return self.Commit()

    def Dispose(self):
        pass


class ParameterElement(object):
    pass


class Annotation(object):
    """Annotations are not FamilyInstance objects in the real Revit API."""
    GetOrderedParameters = Element.GetOrderedParameters
    GetTypeId = Element.GetTypeId
    IsValidType = Element.IsValidType
    ChangeTypeId = Element.ChangeTypeId
    get_Parameter = Element.get_Parameter

    def __init__(self, eid, parameters=None, type_id=10, category=25):
        Element.__init__(self, eid, parameters or [], type_id, category)
        self.Category.CategoryType = 'Annotation'
        self.Category.Name = 'Annotation'

    def GetType(self):
        return Bag(FullName=type(self).__name__)


class TextNote(Annotation):
    def __init__(self, eid, text, type_id=10):
        Annotation.__init__(self, eid, [Parameter(-601, 'Text', text, builtin='TEXT_TEXT')], type_id, 20)
        self.HorizontalAlignment = 0
        self.KeepRotatedTextReadable = True
        self.Width = 0.5
        self.IsTextWrappingActive = True

    @property
    def Text(self):
        return self.Parameters[0].value


class IndependentTag(Annotation):
    def __init__(self, eid, label, host_id, type_id=10):
        Annotation.__init__(self, eid, [Parameter(-602, 'Tag text', label, readonly=True)], type_id)
        self.HasLeader = False
        self.TagOrientation = 0
        self.TaggedElementId = Id(host_id)


class SpatialElementTag(Annotation):
    def __init__(self, eid, type_id=10):
        Annotation.__init__(self, eid, type_id=type_id, category=26)
        self.HasLeader = False


db = Bag(ElementId=Id, ElementType=type('ElementType', (), {}), RevitLinkInstance=type('RevitLinkInstance', (), {}),
         FamilyInstance=Element, ParameterElement=ParameterElement, CategoryType=Bag(Model='Model'),
         TextNote=TextNote, IndependentTag=IndependentTag, SpatialElementTag=SpatialElementTag,
         Element=Bag(Name=Bag(GetValue=lambda e: 'Beam')),
         IFailuresPreprocessor=object, FailureSeverity=Bag(Warning='Warning'),
         FailureProcessingResult=Bag(ProceedWithRollBack='Rollback', Continue='Continue'),
         TransactionStatus=Bag(Started='Started', Committed='Committed'), Transaction=Transaction,
         SubTransaction=Transaction, TransactionGroup=Transaction,
         BuiltInParameter=Bag(PHASE_CREATED='PHASE_CREATED', PHASE_DEMOLISHED='PHASE_DEMOLISHED'))
for name in ('pyrevit', 'System', 'Autodesk', 'Autodesk.Revit', 'Autodesk.Revit.UI', 'Autodesk.Revit.UI.Selection'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['pyrevit'].DB = db
for name, value in [('Int32', int), ('Int64', int), ('Double', float), ('String', str)]:
    setattr(sys.modules['System'], name, value)
sys.modules['Autodesk.Revit.UI.Selection'].ISelectionFilter = object
import match_properties_revit as adapter


def fixture(source_value='Source', target_value='Target', storage='String'):
    source = Element(1, [Parameter(-100, 'Comments', source_value, storage)])
    target = Element(2, [Parameter(-100, 'Comments', target_value, storage)], type_id=11)
    return Doc([source, target]), source, target


class MatchingTests(unittest.TestCase):
    def test_selection_accepts_model_text_tag_detail_and_analytical_instances(self):
        candidates = [Element(1, []), TextNote(2, 'Note'), IndependentTag(3, 'Label', 99),
                      SpatialElementTag(4), Annotation(5)]
        analytical = Element(6, [])
        analytical.Category.CategoryType = 'AnalyticalModel'
        candidates.append(analytical)
        for element in candidates:
            self.assertTrue(adapter.ModelFilter().AllowElement(element), type(element).__name__)

    def test_selection_rejects_types_invalid_category_and_source(self):
        self.assertFalse(adapter.ModelFilter().AllowElement(None))
        self.assertFalse(adapter.ModelFilter().AllowElement(db.ElementType()))
        note = TextNote(1, 'Source')
        self.assertFalse(adapter.ModelFilter(note).AllowElement(note))
        note.Category = None
        self.assertFalse(adapter.ModelFilter().AllowElement(note))

    def test_text_type_alignment_readability_and_width_copy_but_text_is_retained(self):
        source, target = TextNote(1, 'SOURCE WORDING'), TextNote(2, 'KEEP TARGET WORDING', 11)
        source.HorizontalAlignment, source.KeepRotatedTextReadable, source.Width = 2, False, 1.25
        doc = Doc([source, target])
        original = copy.deepcopy(doc.state()[1])
        result = adapter.run(doc, source, [target])
        self.assertEqual((10, 2, False, 1.25),
                         (target.type_id, target.HorizontalAlignment, target.KeepRotatedTextReadable, target.Width))
        self.assertEqual('KEEP TARGET WORDING', target.Text)
        self.assertEqual(original, doc.state()[1])
        self.assertEqual('Updated', result['targets'][0]['status'])
        self.assertTrue(any('Text content' in r['reason'] for r in result['source_skips']))
        self.assertEqual('Already matches', adapter.run(doc, source, [target])['targets'][0]['status'])

    def test_unchecked_annotation_properties_are_retained(self):
        source, target = TextNote(1, 'Source'), TextNote(2, 'Target', 11)
        source.HorizontalAlignment, source.Width = 2, 1.5
        doc = Doc([source, target])
        key = next(r['key'] for r in adapter.source_snapshot(doc, source)['rows'] if r.get('api_property') == 'HorizontalAlignment')
        result = adapter.run(doc, source, [target], selected_keys=[key], copy_type=False)
        self.assertEqual(2, target.HorizontalAlignment)
        self.assertEqual((11, 0.5, 'Target'), (target.type_id, target.Width, target.Text))
        self.assertEqual('Updated', result['targets'][0]['status'])

    def test_annotation_api_aliases_do_not_create_duplicate_checkboxes(self):
        source = TextNote(1, 'Source')
        source.Parameters.append(Parameter(-603, 'Horizontal Align', 0, 'Integer', 'TEXT_ALIGN_HORZ'))
        rows = adapter.source_snapshot(Doc([source]), source)['rows']
        self.assertFalse(any(r['builtin'] == 'TEXT_ALIGN_HORZ' for r in rows))
        self.assertEqual(1, sum(r.get('api_property') == 'HorizontalAlignment' for r in rows))

    def test_readonly_annotation_api_property_is_reported_and_retained(self):
        source, target = TextNote(1, 'Source'), TextNote(2, 'Target')
        source.Width = 2.0
        original = adapter.api_property_writable
        try:
            adapter.api_property_writable = lambda element, name: False if element is target and name == 'Width' else original(element, name)
            result = adapter.run(Doc([source, target]), source, [target])
        finally:
            adapter.api_property_writable = original
        self.assertEqual(0.5, target.Width)
        field = next(f for f in result['targets'][0]['fields'] if f['key'] == 'api:TextNote.Width')
        self.assertEqual('Skipped', field['status'])
        self.assertIn('read-only', field['reason'])

    def test_text_content_change_from_type_assignment_rolls_back_target(self):
        source, target = TextNote(1, 'Source'), TextNote(2, 'Keep', 11)
        original = target.ChangeTypeId
        def change(tid):
            result = original(tid)
            target.Parameters[0].value = 'Unexpected content'
            return result
        target.ChangeTypeId = change
        result = adapter.run(Doc([source, target]), source, [target])
        self.assertEqual((11, 'Keep'), (target.type_id, target.Text))
        self.assertIn('Text content', result['targets'][0]['error'])

    def test_unwrapped_text_does_not_copy_calculated_width(self):
        source, target = TextNote(1, 'Source'), TextNote(2, 'Target')
        source.IsTextWrappingActive = False
        source.Width = 4.0
        result = adapter.run(Doc([source, target]), source, [target])
        self.assertEqual(0.5, target.Width)
        self.assertTrue(any('Unwrapped' in r['reason'] for r in result['source_skips']))

    def test_tag_type_leader_orientation_copy_without_retagging_or_changing_label(self):
        source, target = IndependentTag(1, 'SOURCE LABEL', 100), IndependentTag(2, 'TARGET LABEL', 200, 11)
        source.HasLeader, source.TagOrientation = True, 1
        result = adapter.run(Doc([source, target]), source, [target])
        self.assertEqual((10, True, 1), (target.type_id, target.HasLeader, target.TagOrientation))
        self.assertEqual((200, 'TARGET LABEL'), (target.TaggedElementId.Value, target.Parameters[0].value))
        self.assertEqual('Updated with exceptions', result['targets'][0]['status'])

    def test_spatial_tags_and_generic_detail_annotations_are_matchable(self):
        source, target = SpatialElementTag(1), SpatialElementTag(2, 11)
        source.HasLeader = True
        adapter.run(Doc([source, target]), source, [target])
        self.assertTrue(target.HasLeader)
        source = Annotation(3, [Parameter(-100, 'Comments', 'Source')])
        target = Annotation(4, [Parameter(-100, 'Comments', 'Target')], 11)
        adapter.run(Doc([source, target]), source, [target])
        self.assertEqual((10, 'Source'), (target.type_id, target.Parameters[0].value))

    def test_different_annotation_class_or_category_is_not_matched(self):
        source, target = TextNote(1, 'Source'), IndependentTag(2, 'Target', 100, 11)
        target.Category.Id = source.Category.Id
        self.assertFalse(adapter.ModelFilter(source).AllowElement(target))
        result = adapter.run(Doc([source, target]), source, [target])
        self.assertEqual(11, target.type_id)
        self.assertIn('same category', result['targets'][0]['error'])

    def test_annotation_properties_rollback_when_target_commit_fails(self):
        source, target = TextNote(1, 'Source'), TextNote(2, 'Target', 11)
        source.HorizontalAlignment, source.Width = 2, 2.0
        doc = Doc([source, target]); doc.rejected_target = 2
        result = adapter.run(doc, source, [target])
        self.assertEqual((11, 0, 0.5, 'Target'), (target.type_id, target.HorizontalAlignment, target.Width, target.Text))
        self.assertIn('rolled back', result['targets'][0]['status'])

    def test_recalculated_tag_property_is_reported_not_falsely_copied(self):
        source, target = IndependentTag(1, 'Source', 100), IndependentTag(2, 'Target', 200)
        source.HasLeader = True
        doc = Doc([source, target]); doc.after_regen = lambda: setattr(target, 'HasLeader', False)
        result = adapter.run(doc, source, [target])
        field = next(f for f in result['targets'][0]['fields'] if f['key'] == 'api:IndependentTag.HasLeader')
        self.assertFalse(target.HasLeader)
        self.assertEqual('Skipped', field['status'])

    def test_property_selection_leaves_unchecked_fields_and_type_unchanged(self):
        doc, source, target = fixture()
        source.Parameters.append(Parameter(-300, 'Material choice', 'wood'))
        target.Parameters.append(Parameter(-300, 'Material choice', 'steel'))
        original_type = target.type_id
        key = adapter.source_snapshot(doc, source)['rows'][0]['key']
        result = adapter.run(doc, source, [target], selected_keys=[key], copy_type=False)
        self.assertEqual(original_type, target.type_id)
        self.assertEqual('steel', target.Parameters[-1].value)
        self.assertEqual('Source', target.Parameters[0].value)
        self.assertTrue(any(r['reason'] == 'Unchecked; not copied.' for r in result['source_skips']))

    def test_unchecked_dependency_conflict_retains_target(self):
        doc, source, target = fixture()
        source.Parameters.append(Parameter(-300, 'Other', 'source other'))
        target.Parameters.append(Parameter(-300, 'Other', 'keep'))
        target.Parameters[0].on_set = lambda value: setattr(target.Parameters[-1], 'value', 'changed')
        key = adapter.source_snapshot(doc, source)['rows'][0]['key']
        result = adapter.run(doc, source, [target], selected_keys=[key], copy_type=False)
        self.assertEqual('keep', target.Parameters[-1].value)
        self.assertEqual('Target', target.Parameters[0].value)
        self.assertIn('unchecked property', result['targets'][0]['error'])

    def test_unchecked_structural_usage_is_not_copied(self):
        doc, source, target = fixture()
        source.StructuralUsage, target.StructuralUsage = 3, 4
        keys = [r['key'] for r in adapter.source_snapshot(doc, source)['rows'] if r['key'] != 'api:StructuralUsage']
        adapter.run(doc, source, [target], selected_keys=keys, copy_type=False)
        self.assertEqual(4, target.StructuralUsage)

    def test_exclude_levels_preserves_level_but_copies_offset_and_comments(self):
        doc, source, target = fixture()
        for element, level, offset in ((source, 100, 2.0), (target, 200, 0.0)):
            element.Parameters.extend([
                Parameter(-200, 'Reference Level', level, 'ElementId', 'INSTANCE_REFERENCE_LEVEL_PARAM'),
                Parameter(-201, 'Offset', offset, 'Double', 'FAMILY_BASE_LEVEL_OFFSET_PARAM')])
        result = adapter.run(doc, source, [target], exclude_levels=True)
        self.assertEqual(200, target.Parameters[-2].value)
        self.assertEqual(2.0, target.Parameters[-1].value)
        self.assertEqual('Source', target.Parameters[0].value)
        self.assertTrue(any('Exclude Levels' in r['reason'] for r in result['source_skips']))

    def test_levels_copy_when_option_off(self):
        doc, source, target = fixture()
        source.Parameters.append(Parameter(-200, 'Top', 100, 'ElementId', 'WALL_HEIGHT_TYPE'))
        target.Parameters.append(Parameter(-200, 'Top', 200, 'ElementId', 'WALL_HEIGHT_TYPE'))
        adapter.run(doc, source, [target])
        self.assertEqual(100, target.Parameters[-1].value)

    def test_usage_api_copies_when_not_in_parameters_and_rerun_is_noop(self):
        doc, source, target = fixture()
        source.StructuralUsage, target.StructuralUsage = 3, 4
        result = adapter.run(doc, source, [target])
        self.assertEqual(3, target.StructuralUsage)
        self.assertEqual(3, source.StructuralUsage)
        field = next(f for f in result['targets'][0]['fields'] if f['key'] == 'api:StructuralUsage')
        self.assertEqual('Copied', field['status'])
        self.assertIn('Source: 3; target: 3', field['reason'])
        self.assertEqual('Already matches', adapter.run(doc, source, [target])['targets'][0]['status'])

    def test_usage_api_handles_readonly_palette_parameter(self):
        doc, source, target = fixture()
        source.StructuralUsage, target.StructuralUsage = 3, 4
        for element, value in ((source, 3), (target, 4)):
            element.Parameters.append(Parameter(-88, 'Structural Usage', value, 'Integer',
                                                'INSTANCE_STRUCT_USAGE_PARAM', readonly=True))
        result = adapter.run(doc, source, [target])
        self.assertEqual(3, target.StructuralUsage)
        self.assertEqual(1, len([f for f in result['targets'][0]['fields'] if f['name'] == 'Structural Usage']))

    def test_usage_api_rolls_back_on_rejected_target_commit(self):
        doc, source, target = fixture()
        source.StructuralUsage, target.StructuralUsage = 3, 4
        doc.rejected_target = target.Id.Value
        result = adapter.run(doc, source, [target])
        self.assertEqual(4, target.StructuralUsage)
        self.assertIn('rolled back', result['targets'][0]['status'])

    def test_usage_api_recalculation_is_reported_and_other_fields_survive(self):
        doc, source, target = fixture()
        source.StructuralUsage, target.StructuralUsage = 3, 4
        doc.after_regen = lambda: setattr(target, 'StructuralUsage', 4)
        result = adapter.run(doc, source, [target])
        self.assertEqual(4, target.StructuralUsage)
        self.assertEqual('Source', target.Parameters[0].value)
        field = next(f for f in result['targets'][0]['fields'] if f['key'] == 'api:StructuralUsage')
        self.assertEqual('Skipped', field['status'])

    def test_type_and_editable_value_match_without_editing_source(self):
        doc, source, target = fixture()
        original = copy.deepcopy(doc.state()[1])
        result = adapter.run(doc, source, [target])
        self.assertEqual(10, target.type_id)
        self.assertEqual('Source', target.Parameters[0].value)
        self.assertEqual(original, doc.state()[1])
        self.assertEqual('Updated', result['targets'][0]['status'])

    def test_second_run_is_noop(self):
        doc, source, target = fixture()
        adapter.run(doc, source, [target])
        before = doc.state()
        result = adapter.run(doc, source, [target])
        self.assertEqual(before, doc.state())
        self.assertEqual('Already matches', result['targets'][0]['status'])

    def test_same_name_different_identity_not_copied(self):
        doc, source, target = fixture()
        target.Parameters[0].Id = Id(-999)
        result = adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)
        self.assertIn('does not expose', result['targets'][0]['fields'][0]['reason'])

    def test_shared_guid_overrides_definition_id(self):
        doc, source, target = fixture()
        source.Parameters[0].Id, target.Parameters[0].Id = Id(100), Id(200)
        for p in (source.Parameters[0], target.Parameters[0]):
            p.IsShared, p.GUID = True, 'SAME-GUID'
        adapter.run(doc, source, [target])
        self.assertEqual('Source', target.Parameters[0].value)

    def test_same_name_distinct_guids_not_copied(self):
        doc, source, target = fixture()
        source.Parameters[0].IsShared, source.Parameters[0].GUID = True, 'one'
        target.Parameters[0].IsShared, target.Parameters[0].GUID = True, 'two'
        adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)

    def test_storage_mismatch_skipped(self):
        doc, source, target = fixture()
        target.Parameters[0].StorageType = 'Integer'
        target.Parameters[0].value = 3
        adapter.run(doc, source, [target])
        self.assertEqual(3, target.Parameters[0].value)

    def test_data_type_mismatch_skipped(self):
        doc, source, target = fixture(1.2, 4.5, 'Double')
        target.Parameters[0].Definition.GetDataType = lambda: Bag(TypeId='Angle')
        adapter.run(doc, source, [target])
        self.assertEqual(4.5, target.Parameters[0].value)

    def test_double_to_text_does_not_abort_other_fields(self):
        doc, source, target = fixture(1.2, 'Not numeric', 'Double')
        target.Parameters[0].StorageType = 'String'
        source.Parameters.append(Parameter(-200, 'Other', 'Source'))
        target.Parameters.append(Parameter(-200, 'Other', 'Target'))
        result = adapter.run(doc, source, [target])
        self.assertEqual('Not numeric', target.Parameters[0].value)
        self.assertEqual('Source', target.Parameters[1].value)
        self.assertEqual('Updated with exceptions', result['targets'][0]['status'])

    def test_unicode_report_keeps_parameter_text(self):
        doc, source, target = fixture(u'Fa\u00e7ade', 'Before')
        source.Parameters[0].Definition.Name = u'\u6ce8\u91ca'
        report = core.format_report(adapter.run(doc, source, [target]))
        self.assertIn(u'\u6ce8\u91ca', report)
        self.assertEqual(u'Fa\u00e7ade', target.Parameters[0].value)

    def test_readonly_source_recalculated_not_written(self):
        doc, source, target = fixture()
        source.Parameters[0].readonly = True
        source.Parameters[0].Definition.BuiltInParameter = 'CURVE_ELEM_LENGTH'
        result = adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)
        self.assertEqual(1, len(result['source_skips']))

    def test_readonly_target_retained(self):
        doc, source, target = fixture()
        target.Parameters[0].readonly = True
        adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)

    def test_global_parameter_not_detached(self):
        doc, source, target = fixture()
        target.Parameters[0].global_id = Id(99)
        adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)

    def test_empty_source_text_clears_target(self):
        doc, source, target = fixture(None, 'Clear me')
        adapter.run(doc, source, [target])
        self.assertEqual('', target.Parameters[0].value)

    def test_missing_numeric_source_does_not_clear_target(self):
        doc, source, target = fixture(None, 7, 'Integer')
        adapter.run(doc, source, [target])
        self.assertEqual(7, target.Parameters[0].value)

    def test_elementid_64bit_copies_exactly(self):
        doc, source, target = fixture(9000000001, -1, 'ElementId')
        adapter.run(doc, source, [target])
        self.assertEqual(9000000001, target.Parameters[0].value)

    def test_double_uses_internal_units(self):
        doc, source, target = fixture(3.125, 1.0, 'Double')
        adapter.run(doc, source, [target])
        self.assertEqual(3.125, target.Parameters[0].value)

    def test_pinned_target_retained(self):
        doc, source, target = fixture()
        target.Pinned = True
        adapter.run(doc, source, [target])
        self.assertEqual(11, target.type_id)
        self.assertEqual('Target', target.Parameters[0].value)

    def test_group_member_retained(self):
        doc, source, target = fixture()
        target.GroupId = Id(50)
        adapter.run(doc, source, [target])
        self.assertEqual(11, target.type_id)

    def test_invalid_type_prevents_partial_match(self):
        doc, source, target = fixture()
        target.valid_types = {11}
        result = adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)
        self.assertIn('Retained', result['targets'][0]['status'])

    def test_replacement_type_rolled_back(self):
        doc, source, target = fixture()
        target.replacement = True
        result = adapter.run(doc, source, [target])
        self.assertEqual(11, target.type_id)
        self.assertIn('replace', result['targets'][0]['error'])

    def test_parameter_failure_does_not_erase_successful_fields(self):
        doc, source, target = fixture()
        source.Parameters.append(Parameter(-200, 'Mark', 'B1'))
        target.Parameters.append(Parameter(-200, 'Mark', 'B2'))
        target.Parameters[1].fail = True
        result = adapter.run(doc, source, [target])
        self.assertEqual('Source', target.Parameters[0].value)
        self.assertEqual('B2', target.Parameters[1].value)
        self.assertEqual('Updated with exceptions', result['targets'][0]['status'])

    def test_commit_failure_restores_one_target_and_keeps_earlier(self):
        doc, source, target = fixture()
        later = Element(3, [Parameter(-100, 'Comments', 'Later')], type_id=11)
        doc.elements[3] = later
        doc.rejected_target = 3
        result = adapter.run(doc, source, [target, later])
        self.assertEqual('Source', target.Parameters[0].value)
        self.assertEqual('Later', later.Parameters[0].value)
        self.assertEqual(11, later.type_id)
        self.assertEqual('Rolled back', result['targets'][1]['fields'][0]['status'])

    def test_source_and_duplicate_targets_excluded(self):
        doc, source, target = fixture()
        result = adapter.run(doc, source, [source, target, target])
        self.assertEqual(1, len(result['targets']))

    def test_controller_before_offset(self):
        doc, source, target = fixture()
        mode = Parameter(-201, 'Mode', 1, 'Integer', 'YZ_JUSTIFICATION')
        source.Parameters.extend([mode, Parameter(-202, 'Offset', 3.2, 'Double', 'Z_OFFSET_VALUE')])
        target_mode = Parameter(-201, 'Mode', 0, 'Integer', 'YZ_JUSTIFICATION')
        offset = Parameter(-202, 'Offset', 0, 'Double', 'Z_OFFSET_VALUE', readonly=lambda: target_mode.value == 0)
        target.Parameters.extend([target_mode, offset])
        adapter.run(doc, source, [target])
        self.assertEqual(3.2, offset.value)

    def test_retry_after_controller(self):
        doc, source, target = fixture()
        source.Parameters.extend([Parameter(-300, 'A value', 'Ready'), Parameter(-301, 'Z custom switch', 1, 'Integer')])
        switch = Parameter(-301, 'Z custom switch', 0, 'Integer')
        dependent = Parameter(-300, 'A value', 'Old', readonly=lambda: switch.value == 0)
        target.Parameters.extend([dependent, switch])
        adapter.run(doc, source, [target])
        self.assertEqual('Ready', dependent.value)

    def test_phase_pair_clears_demolition_before_creation(self):
        doc, source, target = fixture()
        source.Parameters.extend([Parameter(-400, 'Created', 20, 'ElementId', 'PHASE_CREATED'), Parameter(-401, 'Demolished', 30, 'ElementId', 'PHASE_DEMOLISHED')])
        created = Parameter(-400, 'Created', 10, 'ElementId', 'PHASE_CREATED')
        demo = Parameter(-401, 'Demolished', 15, 'ElementId', 'PHASE_DEMOLISHED')
        def check(value):
            if demo.value != -1 and value > demo.value:
                raise ValueError('Invalid phase order')
        created.on_set = check
        target.Parameters.extend([created, demo])
        adapter.run(doc, source, [target])
        self.assertEqual((20, 30), (created.value, demo.value))
        before = doc.state()
        adapter.run(doc, source, [target])
        self.assertEqual(before, doc.state())

    def test_commit_warnings_reported(self):
        doc, source, target = fixture()
        doc.warn_target = 2
        result = adapter.run(doc, source, [target])
        self.assertIn('Duplicate mark', core.format_report(result))

    def test_none_demolition_clears_existing_demolition(self):
        doc, source, target = fixture()
        source.Parameters.append(Parameter(-401, 'Demolished', None, 'ElementId', 'PHASE_DEMOLISHED'))
        demo = Parameter(-401, 'Demolished', 30, 'ElementId', 'PHASE_DEMOLISHED')
        target.Parameters.append(demo)
        adapter.run(doc, source, [target])
        self.assertEqual(-1, demo.value)

    def test_final_dependency_recalculation_reported(self):
        doc, source, target = fixture()
        source.Parameters.append(Parameter(-500, 'Z related value', 'Different'))
        related = Parameter(-500, 'Z related value', 'Old')
        related.on_set = lambda v: setattr(target.Parameters[0], 'value', 'Recalculated')
        target.Parameters.append(related)
        result = adapter.run(doc, source, [target])
        self.assertEqual('Source', target.Parameters[0].value)
        self.assertEqual('Copied', result['targets'][0]['fields'][0]['status'])

    def test_writable_parameter_outside_ordered_list_is_copied(self):
        doc, source, target = fixture()
        source.GetOrderedParameters = lambda: []
        adapter.run(doc, source, [target])
        self.assertEqual('Source', target.Parameters[0].value)

    def test_source_readonly_does_not_exclude_writable_target(self):
        doc, source, target = fixture()
        source.Parameters[0].readonly = True
        adapter.run(doc, source, [target])
        self.assertEqual('Source', target.Parameters[0].value)

    def test_structural_usage_applied_after_offsets(self):
        usage = {'builtin': 'INSTANCE_STRUCT_USAGE_PARAM', 'name': 'Structural Usage', 'key': ('builtin', -1)}
        offset = {'builtin': 'Z_OFFSET_VALUE', 'name': 'z Offset', 'key': ('builtin', -2)}
        self.assertGreater(core.priority(usage), core.priority(offset))

    def test_beam_structural_fields_copy_all_storage_types(self):
        doc, source, target = fixture()
        for pid, name, storage, desired, previous, builtin in [
                (-501, 'Structural Material', 'ElementId', 52, 51, 'STRUCTURAL_MATERIAL_PARAM'),
                (-502, 'Stick Symbol Location', 'Integer', 2, 0, 'STRUCTURAL_BEAM_STICK_SYMBOL_LOCATION'),
                (-503, 'Start Connection', 'Integer', 1, 0, 'STRUCT_CONNECTION_BEAM_START'),
                (-504, 'End Connection', 'Integer', 2, 0, 'STRUCT_CONNECTION_BEAM_END'),
                (-505, 'Structural Usage', 'Integer', 3, 0, 'INSTANCE_STRUCT_USAGE_PARAM')]:
            source.Parameters.append(Parameter(pid, name, desired, storage, builtin))
            target.Parameters.append(Parameter(pid, name, previous, storage, builtin))
        adapter.run(doc, source, [target])
        self.assertEqual([p.value for p in source.Parameters], [p.value for p in target.Parameters])

    def test_cancel_before_first_target_changes_nothing(self):
        doc, source, target = fixture()
        original = doc.state()
        result = adapter.run(doc, source, [target], Bag(cancelled=True, update_progress=lambda *args: None))
        self.assertTrue(result['cancelled'])
        self.assertEqual(original, doc.state())

    def test_incompatible_category_retained(self):
        doc, source, target = fixture()
        target.Category.Id = Id(999)
        result = adapter.run(doc, source, [target])
        self.assertIn('same category', result['targets'][0]['error'])

    def test_ambiguous_parameter_not_written(self):
        doc, source, target = fixture()
        target.Parameters.append(Parameter(-100, 'Different name', 'Other'))
        adapter.run(doc, source, [target])
        self.assertEqual('Target', target.Parameters[0].value)
        self.assertEqual('Other', target.Parameters[1].value)

    def test_family_local_ids_cannot_cross_families_without_type_match(self):
        row = {'key': ('definition', 20), 'storage': 'String', 'data_type': 'Text'}
        self.assertIn('Family-local', core.compatibility(row, dict(row), False))

    def test_true_project_parameter_can_cross_families(self):
        row = {'key': ('definition', 20), 'storage': 'String', 'data_type': 'Text', 'project_parameter': True}
        self.assertIsNone(core.compatibility(row, dict(row), False))

    def test_formula_readonly_is_not_forced(self):
        row = {'key': ('definition', 20), 'storage': 'Double', 'data_type': 'Length'}
        target = dict(row, readonly=True)
        self.assertIn('read-only', core.compatibility(row, target))


if __name__ == '__main__':
    unittest.main()
