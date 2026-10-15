# -*- coding: utf-8 -*-
"""NdevTools shared UI labels; Python 2.7 / IronPython compatible.

The locale comes from an explicit pyRevit language choice or the Revit UI.
Spellchecker dictionary variants
such as French capitals and the German spelling reform are not UI locales.
Only interface labels known in ui_translations.json are changed. Free text,
model/sheet/view names, engineering data, and user-entered values are untouched.
"""
import os
import json
import codecs

try:
    from pyrevit.coreutils import applocales
except Exception:
    applocales = None

_CATALOG = None
_SUPPORTED = ('en_us', 'en_gb', 'fr_fr', 'de_de', 'it_it', 'es_es', 'ar', 'pt_br', 'bg', 'chinese_s', 'chinese_t', 'cs', 'nl_nl', 'fa', 'hu', 'ja', 'ko', 'pl', 'ru', 'uk')


def get_language():
    """Return the chosen pyRevit language or, by default, the Revit UI language.

    Python 2.7 and IronPython compatible. Never modifies global settings.
    An explicit pyRevit locale selection takes precedence, enabling the full
    pyRevit language list even if that language is not available in Revit.
    """
    try:
        from pyrevit.userconfig import user_config
        choice = str(getattr(user_config, 'user_locale', '') or '').lower()
        if choice in _SUPPORTED:
            return choice
    except Exception:
        pass
    try:
        if applocales is not None:
            revit_locale = applocales.get_host_applocale()
            code = str(getattr(revit_locale, 'locale_code', '')).lower()
            if code in _SUPPORTED:
                return code
    except Exception:
        pass
    try:
        from pyrevit import HOST_APP
        name = str(getattr(HOST_APP, 'language', '')).lower()
        for signature, code in (
            ('english_gb','en_gb'), ('german','de_de'),
            ('french','fr_fr'), ('italian','it_it'),
            ('spanish','es_es'), ('english','en_us')):
            if signature in name:
                return code
    except Exception:
        pass
    return 'en_us'


def _catalog():
    global _CATALOG
    if _CATALOG is None:
        try:
            path = os.path.join(os.path.dirname(__file__), 'ui_translations.json')
            with codecs.open(path, 'r', encoding='utf-8') as stream:
                _CATALOG = json.load(stream)
        except Exception:
            _CATALOG = {}
    return _CATALOG


def tr(english_text):
    """Translate exact-known interface labels; safely fall back to English."""
    if not english_text:
        return english_text
    lang = get_language()
    if lang in ('en_us', 'en_gb'):
        return english_text
    try:
        val = unicode(english_text)
    except Exception:
        return english_text
    values = _catalog().get(val)
    if values:
        return values.get(lang, english_text)
    stripped = val.strip()
    values = _catalog().get(stripped)
    if values:
        return val[:len(val) - len(val.lstrip())] + values.get(lang, stripped) + val[len(val.rstrip()):]
    return english_text


def _as_string(value):
    """Reject controls and model objects, translating only .NET strings."""
    try:
        if isinstance(value, basestring):
            return unicode(value)
    except Exception:
        pass
    return None


def localize_window(window):
    """Translate WPF and WinForms static labels before modal display.

    Never alters model elements, data entry textboxes or selection values.
    Non-fatal: failed labels must never stop a Revit tool from opening.
    """
    if get_language() in ('en_us', 'en_gb'):
        return window
    try:
        from System.Windows import LogicalTreeHelper
    except Exception:
        LogicalTreeHelper = None
    stack = [window]
    seen = set()
    while stack and len(seen) < 12000:
        control = stack.pop()
        if control is None:
            continue
        try:
            identity = id(control)
            if identity in seen:
                continue
            seen.add(identity)
            type_name = control.GetType().FullName
        except Exception:
            type_name = ''

        # WPF TextBoxes and Windows Forms input fields may hold user/project
        # data; intentionally never change these values.
        editable = ('TextBox' in type_name or 'ComboBox' in type_name or
                    'RichText' in type_name or 'PasswordBox' in type_name)
        for property_name in ('Title', 'Header', 'Content', 'Text', 'ToolTip'):
            if property_name == 'Text' and editable:
                continue
            try:
                original = getattr(control, property_name)
                value = _as_string(original)
                if value is None:
                    continue
                translated = tr(value)
                if translated != value:
                    setattr(control, property_name, translated)
            except Exception:
                pass
        # Recursively inspect WPF logical children, and WinForms Controls.
        if LogicalTreeHelper is not None:
            try:
                stack.extend(list(LogicalTreeHelper.GetChildren(control)))
            except Exception:
                pass
        try:
            stack.extend(list(control.Controls))
        except Exception:
            pass
        # Some WinForms containers expose tabs as a separate collection.
        try:
            stack.extend(list(control.TabPages))
        except Exception:
            pass
    return window


def show_localized_dialog(window):
    """Drop-in replacement for Window/Form.ShowDialog() with same result."""
    try:
        localize_window(window)
    except Exception:
        pass
    return window.ShowDialog()


_RIBBON_REGISTRY = None


def _ribbon_registry():
    global _RIBBON_REGISTRY
    if _RIBBON_REGISTRY is None:
        try:
            path = os.path.join(os.path.dirname(__file__), 'ribbon_translations.json')
            with codecs.open(path, 'r', encoding='utf-8') as stream:
                _RIBBON_REGISTRY = json.load(stream)
        except Exception:
            _RIBBON_REGISTRY = []
    return _RIBBON_REGISTRY


def _normalized_title(value):
    """Treat newline and whitespace variants as the same ribbon title."""
    try:
        return u' '.join(unicode(value).lower().split())
    except Exception:
        return u''


def sync_ribbon_to_revit_language(uiapp=None):
    """Localize ONLY the NdevTools tab; do not change pyRevit preferences.

    Safe to call from a Revit UI event once pyRevit has created the ribbon.
    Returns number of updated command buttons. Never changes a document.
    """
    if uiapp is None:
        try:
            from pyrevit import HOST_APP
            uiapp = HOST_APP.uiapp
        except Exception:
            return 0
    if uiapp is None:
        return 0
    lang = get_language()
    registry = _ribbon_registry()
    updated = 0
    panels = uiapp.GetRibbonPanels('NdevTools')
    if not panels:
        return 0
    # Revit ribbon panel names are stable English IDs, but titles can change.
    panel_titles = {
        'Welcome': {'en_us': 'Welcome', 'en_gb': 'Welcome',
                    'fr_fr': 'Accueil', 'de_de': 'Willkommen',
                    'it_it': 'Benvenuto', 'es_es': 'Bienvenida',
                    'ar': 'الترحيب', 'pt_br': 'Boas-vindas',
                    'bg': 'Добре дошли', 'chinese_s': '欢迎',
                    'chinese_t': '歡迎', 'cs': 'Vítejte',
                    'nl_nl': 'Welkom', 'fa': 'خوش‌آمد',
                    'hu': 'Üdvözlet', 'ja': 'ようこそ',
                    'ko': '환영', 'pl': 'Powitanie',
                    'ru': 'Добро пожаловать', 'uk': 'Ласкаво просимо'},
        'Annotation': {'en_us': 'Annotation', 'en_gb': 'Annotation',
                       'fr_fr': 'Annotation', 'de_de': 'Beschriftung',
                       'it_it': 'Annotazione', 'es_es': 'Anotación',
                       'ar': 'الشرح', 'pt_br': 'Anotação',
                       'bg': 'Анотация', 'chinese_s': '注释',
                       'chinese_t': '註解', 'cs': 'Anotace',
                       'nl_nl': 'Annotatie', 'fa': 'یادداشت‌گذاری',
                       'hu': 'Jelölés', 'ja': '注釈',
                       'ko': '주석', 'pl': 'Adnotacje',
                       'ru': 'Аннотации', 'uk': 'Анотації'},
        'Sheets': {'en_us': 'Sheets', 'en_gb': 'Sheets',
                   'fr_fr': 'Feuilles', 'de_de': 'Planblätter',
                   'it_it': 'Tavole', 'es_es': 'Planos',
                   'ar': 'اللوحات', 'pt_br': 'Folhas',
                   'bg': 'Листове', 'chinese_s': '图纸',
                   'chinese_t': '圖紙', 'cs': 'Výkresy',
                   'nl_nl': 'Bladen', 'fa': 'شیت‌ها',
                   'hu': 'Lapok', 'ja': 'シート',
                   'ko': '시트', 'pl': 'Arkusze',
                   'ru': 'Листы', 'uk': 'Аркуші'},
        '3D Model': {'en_us': '3D Model', 'en_gb': '3D Model',
                     'fr_fr': 'Modèle 3D', 'de_de': '3D-Modell',
                     'it_it': 'Modello 3D', 'es_es': 'Modelo 3D',
                     'ar': 'نموذج ثلاثي الأبعاد', 'pt_br': 'Modelo 3D',
                     'bg': '3D модел', 'chinese_s': '三维模型',
                     'chinese_t': '三維模型', 'cs': '3D model',
                     'nl_nl': '3D-model', 'fa': 'مدل سه‌بعدی',
                     'hu': '3D modell', 'ja': '3Dモデル',
                     'ko': '3D 모델', 'pl': 'Model 3D',
                     'ru': '3D-модель', 'uk': '3D-модель'},
    }
    for panel in panels:
        try:
            name = unicode(panel.Name)
            if name in panel_titles:
                panel.Title = panel_titles[name].get(lang, name)
        except Exception:
            pass
        try:
            items = list(panel.GetItems())
        except Exception:
            continue
        for item in items:
            try:
                current = _normalized_title(item.ItemText)
                name = unicode(item.Name).lower()
            except Exception:
                continue
            for spec in registry:
                # Prefer matching the internal bundle name, then the current
                # display text against any locale (covers older pyRevit builds).
                hint = unicode(spec['folder']).lower()
                candidates = [_normalized_title(v) for v in spec['title'].values()]
                matches_name = hint in name
                matches_text = current in candidates
                if not (matches_name or matches_text):
                    continue
                target = spec['title'].get(lang, spec['title'].get('en_us'))
                if not target:
                    break
                try:
                    item.ItemText = target
                    updated += 1
                except Exception:
                    pass
                try:
                    tip = spec['tooltip'].get(lang, spec['tooltip'].get('en_us'))
                    if tip:
                        item.ToolTip = tip
                except Exception:
                    pass
                break
    return updated
