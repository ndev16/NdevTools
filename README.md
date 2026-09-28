
# NdevTools

![NdevTools tool overview](NdevTools-Overview.png)

A pyRevit extension for managing Autodesk Revit views and sheets, developed by Nataraj Devaraj.

NdevTools provides tools designed to simplify repetitive Revit tasks, improve productivity and streamline sheet and view management.

## Included tools

All four tools appear in the **NdevTools > Sheets** panel.

| Button | Description |
|---|---|
| Place Views on Sheet | Place multiple unplaced views on a selected sheet using saved viewport positions and a selected viewport type. |
| Match Crop Regions | Copy a source plan view's model crop extents to selected target plan views. |
| Sheet Manager | Create multiple sheets or batch rename existing sheets, with duplicate sheet-number checks. |
| Crop Position Manager | Save and apply named viewport positions using sheet X/Y coordinates. |

## Installation

1. Install a compatible version of Autodesk Revit.
2. Install pyRevit.
3. Download or clone this repository.
4. Place the repository files inside a folder named `NdevTools.extension` in a directory registered with pyRevit as a custom extension location.
5. Reload pyRevit in Revit.

The **NdevTools** tab should appear in the Revit ribbon.

## Repository layout

    NdevTools.tab/          pyRevit tab and four tools
    media/                 Tool icons for documentation
    NdevTools-Overview.png  Illustrated tool overview
    README.md              Project documentation
    extension.json         Extension metadata
    .gitignore             Git exclusions
    LICENSE                GNU GPL v3 license

Each tool folder inside `NdevTools.tab/Sheets.panel/` contains its corresponding `script.py`, `bundle.yaml` and `icon.png`.

No separate `lib/` directory is included because the existing tools do not require shared code.

## Compatibility and testing

All four NdevTools tools have been functionally tested inside Autodesk Revit using pyRevit.

### Tested Autodesk Revit versions

- Autodesk Revit 2023
- Autodesk Revit 2024
- Autodesk Revit 2025
- Autodesk Revit 2026
- Autodesk Revit 2027

### Tested pyRevit version

- pyRevit 6.0.0

### Verified functionality

- Place Views on Sheet
- Match Crop Regions
- Sheet Manager
- Crop Position Manager

All four tools have been tested and confirmed working in the Revit versions listed above.

Compatibility with other Revit and pyRevit versions has not yet been verified.

## Publishing

NdevTools is publicly available on GitHub.

**Repository:**
https://github.com/ndev16/NdevTools

NdevTools has been proposed for inclusion in the official pyRevit Extensions Manager.

Listing is subject to review and approval by the pyRevit maintainers.

## Issues, feedback and feature requests

If you encounter any problems while using NdevTools, please feel free to report them.

Your feedback is valuable and helps improve the extension for the entire Revit community.

**Report an issue:**

https://github.com/ndev16/NdevTools/issues/new

When reporting a problem, please provide:

- Autodesk Revit version
- pyRevit version
- Name of the affected tool
- Description of the problem
- Steps to reproduce the issue
- Screenshots or error messages, if available

Suggestions for improvements and requests for new features are also welcome.

## Support and contact

If you experience any issues, have questions or need assistance with NdevTools, please don't hesitate to contact me.

You can reach me through GitHub, LinkedIn or email. I'll do my best to help resolve any issues and welcome your suggestions for improving the tools.

**Developer:** Nataraj Devaraj

**GitHub:**
https://github.com/ndev16

**LinkedIn:**
https://www.linkedin.com/in/nataraj016/

**Email:**
devnataraj39@gmail.com

For bug reports and feature requests, please use GitHub Issues so they can be tracked and discussed publicly.

For other inquiries or direct assistance, feel free to connect with me on LinkedIn or send me an email.

Thank you for using NdevTools!

## License

Copyright (C) 2026 Nataraj Devaraj.

NdevTools is released under the **GNU General Public License, version 3 (GPL-3.0-only)**.

You may use, share and modify this extension under the conditions of that license.

See the [LICENSE](LICENSE) file in this repository for the full license terms.
