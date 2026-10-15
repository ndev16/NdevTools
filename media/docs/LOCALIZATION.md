# NdevTools — automatic Revit-language matching

**No separate NdevTools language setting is required.** NdevTools UI strings now use
`pyrevit.coreutils.applocales.get_host_applocale()` to read Revit's active
interface language, rather than the optional pyRevit locale override.

## Language support

| Revit interface | NdevTools locale |
|---|---|
| American English | `en_us` |
| British English | `en_gb` |
| French | `fr_fr` |
| German | `de_de` |
| Italian | `it_it` |
| Spanish | `es_es` |

The screenshot's French uppercase variants, German spelling reforms, and
building-industry dictionary are *spell-checker options*, not distinct UI languages.

## Automatic ribbon localization

The eight `bundle.yaml` files keep their localized titles/tooltips. pyRevit itself
may otherwise prefer the global user-selected pyRevit language. The optional
`startup.py` runs a one-shot UI Idling handler after pyRevit ribbon creation:
it adjusts only NdevTools button/panel captions and tooltips to match the active
Revit language, leaving every other pyRevit extension and global setting alone.
It does not create commands, change paths, touch Revit model data, or modify any
pyRevit settings. If this particular Revit/pyRevit version doesn't allow the
ribbon update, the standard bundle metadata stays in effect without preventing
NdevTools from loading.

## Dialog localization

All eight Python commands already use `NdevTools.tab/lib/ndev_i18n.py` for
known static dialog labels. The locale resolution in that file now **always**
reads the Revit interface language (not the pyRevit preference).
Unknown UI messages still fall back to English. This is partial rather than
complete translation of dynamic messages or long help text.

## Dark icons

Each command retains original `icon.png` and added `icon.dark.png`.
Automatic dark-theme icons require a recent pyRevit with Revit 2024+;
Revit 2021–2023 uses normal `icon.png`.

## Install

1. Close Revit. Back up your working `%APPDATA%\pyRevit\Extensions\NdevTools.extension`.
2. Copy the *contents* of this ZIP into that folder, replacing its files.
3. Confirm that `extension.json`, `startup.py` and `NdevTools.tab` are directly
   inside the extension folder; do not nest another `NdevTools.extension`.
4. Restart Revit. Change Revit interface language using a supported Revit
   language shortcut or installation configuration; not the spelling dictionary.
5. NdevTools reads that interface language automatically when commands open.
   The ribbon labels are adjusted on the next Revit UI idle where supported.

No Autodesk Revit runtime was available in the packaging environment; test on a
safe copy of a project before public release. If the tab is missing, restore
your backup first and check the pyRevit extension path, then review logs.


## Additional update

- Toolbar icons now use monochrome theme pairs: `icon.png` (black for light theme) and `icon.dark.png` (white for dark theme).
- Added pyRevit/Revit language-code support for: ar, pt_br, bg, chinese_s, chinese_t, cs, nl_nl, fa, hu, ja, ko, pl, ru, uk.
- Existing French, German, Italian, Spanish, and English localizations remain in place. Untranslated static labels safely fall back to English.


## GitHub monochrome theme-icons update

Every ribbon command has `icon.png` (dark outline, transparent background for
light themes) and `icon.dark.png` (white outline, transparent background for
dark themes). The editable SVG artwork is in `media/theme-icon-sources/`.

### Language selection

NdevTools honors an explicit **pyRevit Settings → Language** selection. When
no pyRevit language override is configured, it follows the Revit UI language.
The metadata contains all 20 supported locale keys. English is the fallback
for untranslated tooltip descriptions and custom-dialog labels in newer locales.
Native Revit language switching is not controlled by this extension.

### Testing

1. Use an isolated Revit installation or back up your extension folder.
2. Install files at `<extensions-root>/NdevTools.extension/`.
3. Restart Revit or reload pyRevit. Confirm all eight buttons appear.
4. In pyRevit Settings, switch between English, German, and a newly added locale.
5. Check ribbon text, opening each dialog, and both Revit light/dark themes.
6. Review black/white icon contrast and report any translated labels that overflow.

Static code validation and file integrity checks do not substitute for a
functional test in Revit.
