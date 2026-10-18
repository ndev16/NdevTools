# NdevTools localization

NdevTools includes 20 locale mappings for the titles and tooltip descriptions of
all **12 commands** across five panels. An explicit **pyRevit Settings → Language**
selection wins; otherwise `get_host_applocale()` supplies the Revit UI locale.
Unknown strings fall back to English. The helper does not change pyRevit settings
or Revit's interface language. Spelling dictionaries are unrelated to UI locale.

## Ribbon synchronization

Each button's `bundle.yaml` is the metadata source. The matching
`NdevTools.tab/lib/ribbon_translations.json` supplies the optional one-shot
`startup.py` UI-idle synchronization. That routine updates only NdevTools ribbon
captions and tooltips; it does not create commands or edit model data. The shared
helper also has translated captions for Welcome, Annotation, Sheets, 3D Model
and Handy. If native ribbon updating is unavailable, pyRevit bundle metadata
remains in effect.

## Dialogs and icons

Known static dialog labels use the shared UI translation catalog where wired.
Custom WPF/browser panels, dynamic results, engineering data and longer help text
may still be English. User-entered model names and note contents are preserved.
Every command ships black/dark `icon.png` artwork for a light theme and white
`icon.dark.png` artwork for a dark theme. Actual theme switching depends on the
installed Revit/pyRevit version. The older editable SVGs remain available for
the icons they cover; they are not the source of every newer icon.

## Validate changes

1. Keep one installed copy of NdevTools, with `extension.json`, `startup.py` and
   `NdevTools.tab` directly inside `NdevTools.extension`.
2. Regenerate the ribbon catalog whenever localized bundle titles/tooltips change.
3. Reload pyRevit and verify all 12 commands and five panels.
4. Check representative locales, including Arabic/Farsi and CJK, and both themes.
5. Review label overflow and preserve user-entered text during dialog translation.

Static packaging checks and offline regressions do not replace live-Revit testing.
See [supported locales](../../BUNDLE_TRANSLATIONS.md) for the full list.
