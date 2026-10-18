# NdevTools translated ribbon metadata

All **12 command bundles** contain titles and tooltip descriptions for these 20
pyRevit locale options: `ar`, `pt_br`, `bg`, `chinese_s`, `chinese_t`, `cs`,
`nl_nl`, `en_gb`, `en_us`, `fa`, `fr_fr`, `de_de`, `hu`, `it_it`, `ja`, `ko`,
`pl`, `ru`, `es_es`, and `uk`. Product names such as ViewPilot and FramePilot
remain unchanged where appropriate.

![Current 20-language support banner](media/NdevTools-20-Language-Support.png)

The ribbon contains Welcome, two Annotation tools, five Sheets tools, two
3D Model tools and two Handy tools. Each command includes `icon.png` for a light
background and `icon.dark.png` for a dark background.

An explicit **pyRevit Settings → Language** choice takes priority. Otherwise,
the shared helper follows the Revit interface language; unavailable UI strings
fall back to English. Spelling-dictionary variants are not interface locales.

`NdevTools.tab/lib/ribbon_translations.json` is generated from the current
`bundle.yaml` title/tooltip mappings. The one-shot startup ribbon synchronizer
reads this catalog, so it must be updated whenever those mappings change.
The catalog uses current bundle names, including `Create walls and opening`,
ViewPilot, FramePilot, Notes and Useful Links. It no longer restores old wall
descriptions or the printed Notes/Useful Links developer profile URLs.

Layout-only tab, panel and stack bundles do not need tooltip translations.
Custom dialogs and dynamic messages may still contain English; ribbon coverage
does not mean every dialog is fully localized. Native-speaker review remains
useful for engineering terminology and right-to-left presentation.

See [localization details](media/docs/LOCALIZATION.md) and the
[current ribbon overview](media/NdevTools-Ribbon.png).
