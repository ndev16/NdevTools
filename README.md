# NdevTools

![NdevTools tool overview](NdevTools-Overview.png)

A pyRevit extension for managing Revit views and sheets, created by Nataraj Devaraj.

## Included tools

All tools appear in the **NdevTools > Sheets** panel.

| Button | What it does |
|---|---|
| Place Views on Sheet | Place multiple unplaced views on a selected sheet using saved viewport positions and a selected viewport type. |
| Match Crop Regions | Copy a source plan view's model crop extents to selected target plan views. |
| Sheet Manager | Create multiple sheets or batch rename existing sheets, with duplicate sheet-number checks. |
| Crop Position Manager | Save and apply named viewport positions using sheet X/Y coordinates. |

## Install locally

1. Install pyRevit and use a compatible Revit version.
2. Place these repository files inside a directory called `NdevTools.extension` in a directory registered with pyRevit as a custom extension location.
3. Reload pyRevit in Revit. The `NdevTools` tab should appear.

## Repository layout

```text
NdevTools.tab/              The actual pyRevit tab and four buttons
media/                      Copies of tool icons for documentation
NdevTools-Overview.png      Illustrated tool overview (not a Revit screenshot)
README.md                   Project documentation
extension.json              Extension metadata
.gitignore                  Files excluded from Git
LICENSE                     GNU GPL v3 (already created on GitHub)
```

The four button folders in `NdevTools.tab/Sheets.panel/` each retain
their original `script.py` and `bundle.yaml`, with an icon named exactly `icon.png`.
No `lib/` directory is included because the existing tools do not currently
need a separate shared-code folder.

## Compatibility and testing

The source scripts pass a Python 3 syntax check, but functionality has **not** been tested inside Revit. Confirm the supported Revit and pyRevit versions through testing before advertising specific compatibility.

## Publishing

Once this repository is public, add its GitHub URL and optional author profile to `extension.json`. To propose inclusion in pyRevit's Extensions directory, follow [pyRevit's instructions](https://docs.pyrevitlabs.io/custom_extension/).

## License

Copyright (C) 2026 Nataraj Devaraj.

NdevTools is released under the **GNU General Public License, version 3 (GPL-3.0-only)**. You may use, share, and modify it under the conditions of that license. See the [`LICENSE`](LICENSE) file in this repository for the full terms.
