# Changelog

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
