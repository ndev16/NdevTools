# Tab Hider

Safety repair: add-in pages now enumerate only public Revit RibbonPanel objects, not internal Autodesk.Windows panels. Apply writes only changed checkboxes. Family-mode tab IDs and contextual/unknown native tabs are locked, including during Show All. Opening the tool in a project hides the specific family-only tabs and Family Editor panels exposed by the previous version; family documents are excluded from that repair. Revit 2023 live check confirmed the duplicates disappeared and Show All did not restore them.

All Revit Tabs is the main page. Loaded ribbon tabs that expose add-in panels through Revit's GetRibbonPanels API have their own pages. Modify panels and the main Modify tab are locked. The NdevTools tab remains reachable.

In NdevTools > Modify, open Tab Hider. Check a tab or panel to show it, or clear its checkbox to hide it. Click **Apply** to save your choices. **Show All** restores editable entries across all pages and saves that choice for future sessions.

Tab Hider stores your preferences in `%APPDATA%\NdevTools\TabHider\visibility.json` and reapplies them when Revit starts. The preferences belong to your Windows user profile and apply across projects. Revit controls contextual and protected tabs.

Lists the loaded Autodesk.Windows ribbon tabs, including hidden tabs. Revit-managed contextual tabs are shown but not editable. The NdevTools tab stays accessible to reopen this tool.

Implementation is original. Open-source reference: [pyRevit ribbon API](https://docs.pyrevitlabs.io/reference/pyrevit/coreutils/ribbon/) and pyRevit's Minify UI tool were inspected for ribbon visibility behavior; no source was copied. Autodesk.Windows is an internal UI API and requires live verification per Revit release.
