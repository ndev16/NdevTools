# NdevTools: GitHub-ready repository layout

This ZIP contains the repository *contents*, with **no** `PATCH_FILES`
wrapper and **no** `NdevTools.extension` wrapper. The root has the same
main entries as the current GitHub repository.

## Apply to GitHub

1. Back up the repository or create a new branch in GitHub Desktop.
2. Extract this ZIP to a temporary directory.
3. Copy **the extracted contents** into the root of your local
   `ndev16/NdevTools` checkout (not the parent directory).
4. Review changes in GitHub Desktop and commit only the intended files.
5. Push your feature branch, and test in Revit before making a PR.

## Local Revit installation

For a local test, put these same contents directly under
`%APPDATA%\pyRevit\Extensions\NdevTools.extension\`, replacing matching
files. **Do not create a second nested `NdevTools.extension` folder.**
Restart Revit and reload pyRevit.

The root `startup.py` supports automatic language synchronization with
the selected pyRevit/Revit language; the ribbon and translations live under `NdevTools.tab`.
The black light-mode and white dark-mode icons are in each `.pushbutton`.

*Note:* 20 locale codes are recognized in the metadata; not every
long tooltip or custom dialog string has a complete translation.
The update has not been tested inside Autodesk Revit in this environment.
