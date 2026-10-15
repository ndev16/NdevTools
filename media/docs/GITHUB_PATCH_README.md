# NdevTools GitHub-ready update

This ZIP contains **only files to add or replace in the repository root**,
not an extra `NdevTools.extension` wrapper folder. All eight commands keep
their underlying Revit model/drafting logic.

## Apply

1. Back up your local working copy and create a new branch of `ndev16/NdevTools`.
2. Unzip the contents of the `PATCH_FILES/` folder into the repository root.
3. On overwrite, replace only the listed files.
4. Review with `git status` and `git diff`, including your existing branch's code.
5. In Revit, verify both themes and representative languages.
6. Commit and push as a pull request.

## Scope

- 8 pairs of `icon.png` (dark outline) / `icon.dark.png` (white outline)
- 8 editable monochrome SVG source icons in `media/theme-icon-sources/`
- Native multilingual command metadata in each button's `bundle.yaml`
- Shared localization tables and language-selection helper
- Startup ribbon sync and existing custom-dialog localization wiring
- Documentation and test notes

**Translations status:** Ribbon titles are included for 20 locale codes.
English fallback remains in the long tooltips and some dialog labels; this
is not a claim of 100% translated user-facing text.

**Integration status:** Archive structure and syntax validated here, but
not yet tested running in Autodesk Revit.
