# NdevTools - Wall Tracing (walls only)

This pyRevit pushbutton traces **Basic Walls only** from a selected architectural Revit link to the active Revit project. It does not detect, combine, modify, or create wall openings. Existing openings in your project are not deliberately changed by this command; Revit may regenerate wall joins during wall creation.

## Installation

Install the `NdevTools.tab/3D Model.Panel/Create walls.pushbutton` folder as part of the complete `NdevTools.extension` directory, then reload pyRevit. The visible ribbon title is **Wall Tracing**. Keep just one installed copy of the button.

## Use

1. In an open Revit project, start in a plan or 3D view and click **Wall Tracing**.
2. Select a loaded architectural Revit link and choose one or more source levels.
3. Map each source level to host bottom/top levels; review suggested host Basic Wall types.
4. Set a type to **None** to skip it and click **Create Walls**.
5. Review created walls, skipped/unsupported walls, duplicates, and error diagnostics.

## Behavior and safety

- Only straight, vertical Basic Walls with a reliable positive-width structural layer are supported; curved, slanted/tapered, attached or edited-profile walls are skipped.
- The thickest `Structure [1]` layer is used for wall alignment. Host Basic Wall type suggestions use thickness only; verify actual type/material suitability yourself.
- Host bottom/top levels come from your selections. Source wall base and constrained top offsets are preserved as applicable.
- Matching walls are not recreated. No opening-specific analysis or API calls are performed.
- Linked Revit documents are read-only; the active host project is modified in a transaction group with rollback on fatal error or cancellation.
- Automatic joins are temporarily disabled during wall creation and restored after creation. Select existing host walls and rerun the button to choose **Allow joins on selected walls**, if desired.

Designed for pyRevit and Revit 2022 or later.
