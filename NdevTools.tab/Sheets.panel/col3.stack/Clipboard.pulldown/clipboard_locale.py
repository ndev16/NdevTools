# -*- coding: utf-8 -*-
"""FramePilot locale keys used by the sheet clipboard dialogs."""
import io
import json
import os


DEFAULT = 'en_us'
LOCALES = ('ar', 'bg', 'chinese_s', 'chinese_t', 'cs', 'de_de', 'en_gb', 'en_us',
           'es_es', 'fa', 'fr_fr', 'hu', 'it_it', 'ja', 'ko', 'nl_nl', 'pl',
           'pt_br', 'ru', 'uk')
RTL = ('ar', 'fa')
FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')
_cache = {}


def active():
    # pyRevit resolves its configured UI-language override first, then Revit's language.
    from pyrevit.coreutils import applocales
    try:
        locale = applocales.get_current_applocale()
        if locale and locale.locale_code in LOCALES:
            return locale.locale_code
    except (AttributeError, TypeError):
        pass
    return DEFAULT


def catalog(code):
    if code not in _cache:
        with io.open(os.path.join(FOLDER, code + '.json'), encoding='utf-8-sig') as stream:
            _cache[code] = json.load(stream)
    return _cache[code]


class Strings(object):
    def __init__(self, code=DEFAULT):
        self.code = code if code in LOCALES else DEFAULT
        self.values = catalog(self.code)

    def __call__(self, key, *args):
        return self.values[key].format(*args)

    def reason(self, message):
        # Preserve Revit's own diagnostic and all project names when no match exists.
        for key in ('deleted', 'wrong_sheet', 'pinned', 'grouped', 'revision',
                    'source_gone', 'changed', 'skipped_choice'):
            if message == catalog(DEFAULT)[key]:
                return self(key)
        prefix = 'Unsupported sheet item ('
        if message.startswith(prefix) and message.endswith(').'):
            return self('unsupported', message[len(prefix):-2])
        return message
