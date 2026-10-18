# NdevTools Wall Tracing

This button creates model walls and rectangular openings from one selected
architectural Revit link. The ribbon title and brief tooltip use the same 20
locale entries as the adjacent tools. The supplied dark and light ribbon icons
are stored as `icon.png` and `icon.dark.png`; the existing in-window logo remains
unchanged in `reference/NdevTools_Logo.png`.

Legacy detail-tracing files, IDE settings, duplicate icons, and design references
have been removed from this command bundle. A complete pre-update recovery ZIP
is stored outside the extension in the Codex chat's artifact folder.

## Use

1. Reload pyRevit and open a project plan or 3D view.
2. Run **Wall Tracing**. Choose a link from the list or use **Pick Link**.
3. Select one or more linked levels. Search filters the list; Select All selects
   every linked level, including those hidden by the search.
4. On the second page, review the suggested host bottom/top levels for each level.
   All selected levels appear together in one scrolling page.
5. Review each suggested host Basic Wall type. Suggestions use the closest host
   type width to the detected structural-layer thickness. An exact width is preferred;
   nearest-width alternatives are marked in amber. Width alone does not establish
   material or structural equivalence. Select **None** to exclude a type. Unsupported types remain
   disabled at None. Going Back preserves choices until the selected link changes.
6. Click **Create Walls**. Review the summary and per-item output, including source
   IDs, created host IDs, and reasons for skipped or failed elements.

Source base offsets are preserved relative to mapped host bottom levels. Source
top offsets are preserved for level-constrained source walls; unconnected source
walls use the chosen host top with zero top offset. Openings retain actual linked
geometry elevations, including link translation, and are skipped if outside the
mapped host wall's vertical extent. Both opening constraints use the mapped host
bottom level. Nothing is written to the linked document.

### Optional nearby-opening combination

On page 2, **Combine Nearby Openings** is off by default. Enable it and enter
**Maximum Gap** in project length units (explicit units such as `150 mm` or `6"`
are also accepted). The value must be finite and non-negative.

Verified rectangular source cuts on each wall are sorted along that wall. Cuts
with a horizontal clear edge-to-edge gap less than or equal to Maximum Gap are
combined, including chains of qualifying neighbors. Each group creates only its
bounding rectangle: leftmost edge, rightmost edge, lowest bottom, highest top.
Zero combines touching or overlapping intervals. Different sill/head elevations
do not prevent combination. Groups never span different source walls. With the
option off, the previous individual-opening behavior is retained.

This option controls openings created by the run; it does not delete individual
openings already in the host model. Existing matching rectangles are still retained.
If existing cuts conflict with a combined rectangle, Revit's creation failure is
reported and that attempted opening is rolled back.

## Geometry and safety

### Two-stage detection

The existing insert-local geometry detector always runs first. Valid results and
geometry duplicates are marked GEOMETRY and never read fallback parameters.
Only failed insert/wall pairs attempt the controlled Door/Window fallback.

Fallback requires an explicit FamilyInstance.Host matching the source wall, an
insertion point within its length/thickness, and positive numeric length parameters.
Dimensions are read in this order: instance built-ins, type built-ins, named instance
parameters, named type parameters. Rough dimensions do not override valid nominal
values without reliable evidence of their cut semantics. Non-length, ambiguous named,
non-finite and non-positive values are rejected. Unsupported categories stay skipped.

Door bottom uses insertion Z. Window bottom requires its source level plus a sill
height or instance elevation offset; no floor-level default is invented. Width and
height must fit the source wall. Existing creation checks then validate the mapped
destination wall, transform once, project into its local direction, and prevent
duplicate openings. Secondary/corner-wall fallback is conservatively rejected when
the source wall is not the confirmed owner; geometry can still resolve such cuts.

Geometry jobs run before parameter fallback jobs. Combine Nearby Openings retains
its prior geometry-only behavior; fallback jobs cannot enlarge successful geometry
results through combination. Reports retain the primary failure plus fallback
attempt, parameter sources/names/values, elevation/center source, host validation,
and final GEOMETRY/PARAMETER_FALLBACK/NONE detection method.

- Structure [1] function determines the structural layer; the thickest wins.
  Material names are displayed only. Zero-width/missing structural layers and
  vertically varying compound structures are unsupported.
- Layers are ordered exterior to interior. Wall.Orientation already incorporates
  Wall.Flipped. The API LocationCurve is the wall's geometric center, independent
  of its location-line setting; the code accounts for this without double-offsetting.
  See Autodesk's [wall layer explanation](https://blog.autodesk.io/identifying-wall-compound-layers-and-parts/)
  and [compound structure guide](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API/files/Revit_API_Developers_Guide/Revit_Geometric_Elements/Walls_Floors_Ceilings_Roofs_and_Openings/Revit_API_Revit_API_Developers_Guide_Revit_Geometric_Elements_Walls_Floors_Ceilings_Roofs_and_Openings_CompoundStructure_html.html).
- Straight, vertical Basic Walls are supported. Curved, slanted, tapered, attached,
  and edited-profile walls are skipped. Horizontal rotated, translated, and mirrored
  links are supported; tilted/scaled links are rejected.
- Opening discovery starts from real wall-related family/opening elements in
  `Wall.FindInserts` and native dependent Openings. Non-hosted candidates come from
  a spatially bounded family collector and require `InstanceVoidCutExists` proof
  against this source wall. Spatial overlap alone never authorizes a cut.
- A wall with no real insert produces no opening candidates and its side faces
  are not scanned for gaps. For each insert, its projected X-Z extent defines a
  local search window expanded by only 0.0004 ft (four geometry tolerances).
  Invalid zero-width/height extents are retried from actual geometry; if no search
  window can be justified, they are logged as INVALID_PROJECTED_INSERT_EXTENT.
- Reusable wall-face topology is read after insert discovery, but candidate loops
  and missing-region analysis are restricted to each insert window. No full-wall
  missing-region discovery is performed. Clipping is for search only: a cut crossing
  the search-window border is rejected instead of approximated by that border.
- Segmented rectangle validation has no four-edge/four-vertex requirement. Every
  segment must follow minX/maxX/minZ/maxZ within 0.0001 ft, with complete perimeter
  and matching area. Genuine curves, diagonal sides, arches and concavity fail.
- Insert-supported rectangular bottom notches are supported. Wall-end/full-height
  gaps and notch widths inconsistent with the insert are rejected. Anonymous wall
  gaps never become opening candidates. FacingOrientation is not consulted.
- Nearby loops are ranked by X/Z overlap, center distance and width/height similarity.
  Each insert is handled independently; one continuous cut found for two inserts is
  deduplicated. This detection step never merges distinct loops; the separate explicit
  Combine Nearby Openings option, when enabled, still applies after detection.
- Diagnostics are per real insert and include IDs, category/family/type, discovery
  method, projected search extent, cut extent, raw counts, width/height, overlap
  ratios, touched wall boundaries, rectangle validation and final creation result.
  Null solids/faces are guarded; failures remain isolated to the insert.
- Native rectangular Openings are supported. Opening constraint parameters and
  offsets are checked after regeneration; a failed opening is rolled back.
- Existing host walls are checked for duplicate plan endpoints (either direction),
  wall type, bottom level, and top level, at 0.0001 ft tolerance. Matching existing
  walls are reused for opening repair. Matching native rectangular openings are
  retained; missing verified rectangular cuts are created in the existing wall.
  Keep the same type/level mappings on reruns so existing walls can match.
  Automatic joins are temporarily disabled during construction,
  then enabled at both ends after wall and opening creation. Revit controls the
  resulting corner cleanup, including connections to adjacent existing walls.
- Transactions create walls first and openings second within one undo group.
  Safe per-item failures roll back their subtransaction. Fatal errors and cancellation
  roll back the entire group. The linked model is never edited. Existing host walls
  may participate in Revit's automatic join cleanup.

To repair walls created by earlier versions, select those host walls in Revit,
run Wall Tracing, and choose **Allow joins on selected walls**. This enables both
ends in an undoable transaction; it does not recreate walls or openings. It only
explicitly changes the selected walls, although adjacent walls can participate in
Revit's join cleanup. Enabling joins does not bridge arbitrary gaps.

## Verification status

Local checks: 61 offline regression tests pass, covering 48 combinations of location
line, flip, endpoint direction and mirrored/rotated transforms, structural-layer
selection, duplicate matching, cut profile rejection, shared-bottom-level opening
offsets and transformed opening placement. Profile tests also cover tiny/collinear
segments, rotated/reversed wall-space projection, arch/notch/backtracking rejection.
The six production Python modules pass
syntax and Python-2-compatible grammar checks. WPF loads successfully; both pages
were rendered and visually inspected with sample data. The supplied logo and installed
icon have identical SHA-256 hashes.

Location-line settings use explicit .NET enum members for IronPython compatibility.
Unexpected wall-preparation exceptions are counted as errors, and the summary dialog
now includes the most common skip/error reasons so a zero-result run is diagnosable.
Expand the result dialog's details to see every skipped wall's linked level, type,
source ID, reason, cross-section display/raw value, angle in degrees, attachment
flags, and location-line setting. A UTF-8 text report is also saved under the user's
temporary `NdevTools-WallTracing` directory; the dialog shows its exact path.
The vertical-wall check uses Revit's named enum rather than an assumed numeric value.
New host walls are regenerated before their exterior-face orientation is queried,
and again after flipping. Creation errors include the failed operation and a Python
stack trace in the expanded/saved report.

These checks do not run Revit. Revit 2022 API compatibility is targeted; installed
Revit 2023 API documentation was used to check API signatures. In-Revit execution,
wall-face extraction on real family cuts, transactions and opening constraints remain to be verified after this rewrite. The prior 36 successful openings are protected by existing-opening checks; preservation of the detection count and recovery of the remaining 14 require an in-Revit run.

## In-Revit acceptance checks

- Use a test project with an asymmetric architectural wall, two Structure [1]
  layers, all six location-line settings, flipped walls and reversed directions.
  Verify the created wall center is the thickest structural layer center.
- Repeat with translated, rotated and mirrored link instances; compare elevations
  with nonzero link Z and project/shared level elevation settings.
- Select multiple levels, use different host bottom/top mappings, and leave some
  types at None. Verify only source types used on each level are listed.
- Check a rectangular door, a window with a sill, and a native wall opening.
  Inspect both constraint references: each must equal the mapped host bottom level.
  Inspect offsets, widths and actual geometry. Test arched/irregular families too.
- Run again with the same mapping: existing walls must be skipped as duplicates.
  Compare existing model geometry before/after and verify the linked model is untouched.
- Test cancellation, unloaded links, invalid top levels, unsupported walls, and a
  failed opening. Confirm rollback and per-item reporting.
- Start from both plan and 3D views with hidden source walls and a section box;
  collection must still depend only on the link and selected base levels.

Tests: `tests/test_wall_tracing.py` uses Python 3 offline fakes; these are not runtime
dependencies. `tests/render_ui.ps1` renders the actual WPF XAML with sample data.
