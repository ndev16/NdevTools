# NdevTools translated bundle descriptions


## Supported language options

Arabic (`ar`), Brazilian Portuguese (`pt_br`), Bulgarian (`bg`), Chinese Simplified (`chinese_s`), Chinese Traditional (`chinese_t`), Czech (`cs`), Dutch (`nl_nl`), English GB (`en_gb`), English USA (`en_us`), Farsi (`fa`), French (`fr_fr`), German (`de_de`), Hungarian (`hu`), Italian (`it_it`), Japanese (`ja`), Korean (`ko`), Polish (`pl`), Russian (`ru`), Spanish (`es_es`), and Ukrainian (`uk`).

![NdevTools 20-language support preview](media/NdevTools-20-Language-Support.png)

This update supplies actual localized descriptions for all eight command-button tooltips in the 20 language codes included with NdevTools.

The existing long English (`en_us`) tooltips remain unchanged. Existing `en_gb`, `de_de`, `fr_fr`, `it_it`, and `es_es` text also remains unchanged. The other 14 languages now have translated purpose, usage and safety summaries rather than English fallback text. They are **concise localized descriptions**, not line-by-line translations of every paragraph of the long English help content.

The file `NdevTools.tab/lib/ribbon_translations.json` mirrors the descriptions in each command's `bundle.yaml`. The NdevTools ribbon synchronization at startup reads that file, so keeping them aligned prevents the translations from being replaced when the tab reloads.

Root and stack `bundle.yaml` files are layouts only; no translatable tooltip content exists there.

No command scripts, panel layouts or icon files have been changed by this update. For this NdevTools build, the startup synchronizer follows the active Revit interface language (not a separate pyRevit language override); switch the Revit interface language, restart Revit and hover over each command to review the localized tooltip. Some long help text inside custom tool dialogs can still be in English.

Translations should be reviewed by native speakers before claiming full professional localization, particularly for engineering terms and right-to-left text.
