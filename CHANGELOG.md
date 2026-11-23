# Changelog

## November 23, 2026 — Sheet Clipboard detail groups and FramePilot roof boundaries

- Sheet Clipboard now includes detail groups when copying whole detail views between projects, preserving their filled regions, lines, and notes. Paste verification checks the contents of each group, while matching destination type names are reused and missing types are copied.
- Verified the CMU detail in Revit 2025 using rollback-only pastes: all eight detail groups and 23 filled regions were retained, with matching geometry, view scale, and sheet position. The disposable-project regression also checks grouped details, existing and missing region types, and repeated paste.
- Synced the current R&D FramePilot roof-face planning: native beam systems use actual top or bottom face boundaries, including openings and cuts at joins. The command refreshes older cached planners, verifies the expected number of profiles, and reports committed results.
- Preserved the main extension's Clipboard identifiers, ribbon layout, icons, and 20-language bundle metadata. This sync does not add a new live FramePilot validation claim.

## November 16, 2026 — Copy sheet and section details between projects

- Copy selected detail lines, text notes, filled regions, detail components, and imported or linked raster images from a section into a section or drafting view in another open project. Images retain their size, rotation, and pin state.
- Copy sheet lines, arcs, title blocks, and raster images between sheets. Across projects, Sheet Clipboard also copies placed drafting, section, and detail views with their supported detailing.
- Paste closes tabs that Revit opens for newly pasted views and preserves previously open tabs. The NdevTools paste result shows counts and explains skipped items, including structural plan views selected for a cross-project paste.
- Verified sheet graphics, section-to-section and section-to-drafting transfers, whole detail views, and the paste result in disposable projects in Revit 2023, 2024, 2025, 2026, and 2027.

## November 6, 2026 — Sheet transfers and Modify tools

- Added **Sheet Clipboard** to cut and paste placed detail views and other views between sheets in the same project. Paste moves the original views together to the point you pick, preserving their detailing and spacing. One Revit Undo restores the group. Copy keeps the originals on the source sheet.
- Added **Move Views** above Sheet Clipboard in the third Sheets column. Arrange views in two sheet previews or double-click a view to select it on its Revit sheet. The README shows the source and target side by side.
- Added Match Properties, Renumber and Tab Hider to the NdevTools Modify panel. The updated 20-language banner and full-size ribbon screenshot in the README show the current six-panel layout.
- Tab Hider remembers both hidden and visible tabs and add-in panels across Revit restarts. Apply and Show All save per-user preferences. The header includes translated Help, a GitHub star button and a link to Nataraj Devaraj on LinkedIn.
- The extension now lists 19 commands across six panels, with ribbon titles and tooltips for 20 locales.

## October 19, 2026 — Current ribbon and local testing sync

- Synced the current local testing extension: 12 commands across Welcome, Annotation, Sheets, 3D Model and Handy.
- Added ViewPilot, FramePilot, Notes and Useful Links, including their supporting browser/WPF resources and theme icons.
- Replaced the old Wall Tracing bundle with `Create walls and opening.pushbutton`, including current rectangular-opening detection, fallback, optional combination and reports. Removed the obsolete bundle to prevent a duplicate ribbon command.
- Included current Annotation/Sheets command implementations and shared themes from the testing folder.
- Notes includes multiple A4 sheets, independent portrait/landscape orientations, visible page layout, Fill window, local saving/export, queued layout updates and the native-maximize height fix.
- Regenerated the runtime ribbon translation catalog from all 12 bundles, including the URL-free Notes/Useful Links tooltips, and added Handy panel translations. Ribbon matching now prioritizes bundle identifiers before shared translated labels.
- Updated the ribbon screenshot, 20-language support banner, documentation and extension description. Python caches are excluded.
- Packaging checks validate metadata, Python syntax and offline regressions; they do not establish live-Revit stability. The separately observed native project-opening crash remains unresolved.

## October 16, 2026 — 20-language support preview and documentation

- Added the NdevTools 20-language banner to `media/NdevTools-20-Language-Support.png` and displayed it prominently in `README.md`.
- Documented all 20 supported pyRevit locale options for command titles and concise bundle tooltip descriptions.
- Clarified automatic Revit-interface language selection, English fallback for untranslated dialog text, and the matching black/white light/dark theme icon pairs.
- Documentation and preview-image update only; no Revit command logic or ribbon metadata was changed in this patch.

## October 13, 2026 — Sheet Pilot documentation and metadata update

### Sheets panel

- **Sheet Pilot (BulkPlaceViews):** Documented multi-sheet configuration and batch placement of up to 25 views per sheet.
- **Prerequisite:** Manually place a reference viewport on a sheet, then capture and save its X/Y position with **Viewport Position Manager** before using Sheet Pilot.
- **Placement:** Choose a target sheet, unplaced view, viewport type and saved position for each row, then select **PLACE ALL VIEWS**.
- **Protection:** Clarified temporary visibility handling, view-template restoration and independent rollback of failed placements.
- **Repository metadata:** Updated the extension description to include Sheet Pilot and other model/detailing tools. No Revit automation behavior changed by these documentation files.


## October 11, 2026 — Expanded NdevTools ribbon

This update organizes NdevTools into four ribbon panels and documents all eight buttons.

### Added

- **Welcome** — About/contact window with GitHub, LinkedIn and email links.
- **Vulcraft Deck Region** — Concrete filled-region profile following supported Vulcraft metal deck geometry in section views.
- **Auto Detail Generator** — Host-model tracing for floors, walls, roofs, foundations and framing into 2D detailing.
- **Wall Tracing** — Linked architectural Basic Wall tracing into the active host model.

### Updated and reorganized

- **Place Views on Sheet** — Multi-view placement with saved coordinates and temporary visibility controls.
- **Sheet Manager** — Batch sheet creation and renaming.
- **Match Crop Regions** — Apply a reference plan crop boundary to compatible views, optionally copying scale.
- **Viewport Position Manager** — Capture and manage saved viewport positions with temporary visibility handling.
- **Ribbon layout** — Welcome / Annotation / Sheets / 3D Model panels.
- **Documentation** — Expanded tool walkthroughs and updated installation instructions.

### Repository housekeeping

The older root-level Sheets button folders are superseded by the new `Sheets.panel/col1.stack/` and `Sheets.panel/col2.stack/` layout. See `GITHUB_COMMIT_GUIDE.md` for the exact obsolete paths to remove from the repository when committing this update.
