# Match Properties

Location: **NdevTools → Modify → Match Properties**.

Click **Start matching**, pick a source model element, text note, tag, dimension,
detail item or other native Revit instance. Check the properties to copy, then select
targets of the same category and API class and click **Finish** in Revit.
The compact windows follow Renumber's visual style. The command optionally assigns
the source type and copies checked, compatible instance values into editable target fields. The scan
includes the Properties-palette list plus additional writable parameters. Source read-only
status alone does not exclude a value when the corresponding target field is editable.
An empty string value clears the corresponding target parameter. Text-note content
is deliberately excluded: matching its type/appearance preserves its written wording.
The report lists exceptions and has a **Copy Report** button; a UTF-8 copy is saved
in the user's temporary folder after each run.

## Behavior

- Type properties follow the assigned source type. No type definition is edited.
- Built-in parameter IDs, shared GUIDs and same-document definition IDs identify fields.
  Matching never relies on display names. Storage and data types must agree.
- Type assignment precedes field copying. Levels and controlling modes are set before
  offsets. Usage and connection settings follow geometry changes. Two bounded reconciliation
  passes also check fields that initially succeeded but were reset by dependent settings.
- Creation/demolition phases are applied as a pair when both are available.
- Revit-calculated or read-only values (such as beam length and volume) are not written.
  Formula/global-parameter-controlled target fields are retained and reported.
- Targets retain their element identity. No geometry is copied from the source, but
  editable constraints, offsets and justifications can reposition target geometry.
- Mark and other editable identity text are copied too. Any duplicate-value warnings
  returned by Revit are included in the report.
- Only native elements in the active project are modified. Linked-document contents,
  mismatched categories/classes, pinned targets and group members are retained.
  Unsupported rehosting or type changes that recreate elements are not performed.
- Text notes can match their text type (font, size and shared type formatting), horizontal
  alignment, readable-text setting and wrapped text-box width. Unwrapped width remains
  calculated by Revit. Per-character rich-text formatting is not transferred.
- Tags can match their type, leader visibility and orientation where writable. The tagged
  host/reference and its generated label remain associated with the target. Room/area/space
  tags expose compatible properties through their spatial-tag API. Other native annotations
  use the same type and editable-parameter checks as model elements.
- Each target has its own transaction. Revit errors roll back that target, not earlier
  successful targets. A completed run is grouped into one Undo operation.
- ESC during selection performs no changes. Cancelling progress retains completed targets.
- Running again with matching values does not set those values again.

## Validation

66 offline tests cover model/annotation selection, text-content preservation, tag hosts,
annotation API fields, identity matching, value types, dependency ordering, phase ordering,
source exclusions, parameter failures and target transaction failures. These cannot prove
live family behavior. Check a beam pair in Revit: different types, reference levels,
independent/uniform justification, offsets, material and comments; then rerun and inspect
the Copy Report output. Also verify Undo, a read-only field and a pinned target.

API references: Autodesk's `Element.ChangeTypeId`, `Element.GetOrderedParameters`,
`Parameter.IsReadOnly`, `Parameter.Set`, and `IFailuresPreprocessor` documentation.

The windows are modeless. Revit selection and copying run through an ExternalEvent,
not from window callbacks. Picking temporarily hides the active window; Finish,
Escape, and failures restore it with selections intact. The command validates the
active document before every operation. Exclude Levels is available only on the
property checklist, not on the opening page.

Version 1.3.0 adds a source-specific property checklist before target selection.
All copyable fields start checked, with Select all, Clear all, and Exclude Levels.
Element type is separately selectable; shared type properties follow that type.
Unchecked fields are not written. If regeneration changes an unchecked copyable
field, the target transaction is rolled back with a conflict report.

Version 1.4.0 removes the model-category-only selection restriction. Native text notes,
tags and other annotations are now accepted, with text/tag API fields added to the checklist.
Parameter aliases are collapsed to one checkbox and annotation fields are verified after commit.

Version 1.2.0: Structural Usage is copied through the writable
`FamilyInstance.StructuralUsage` API, including when its palette parameter is missing
or read-only. It is reconciled after other fields and verified after commit. Rejected
values are reported, not silently marked copied. Version 1.1's expanded scanning and
source/target reporting are retained. Live Revit validation remains required.

Reference: https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/52fe2ab8-d038-df14-fb12-e4f9c036dd7d.htm
