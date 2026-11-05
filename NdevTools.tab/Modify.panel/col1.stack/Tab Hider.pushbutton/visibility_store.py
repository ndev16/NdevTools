# -*- coding: utf-8 -*-
"""Per-user ribbon visibility choices shared by all Revit versions."""
from contextlib import contextmanager
import hashlib
import json
import os

from System import Environment, Guid
from System.IO import Directory, DirectoryNotFoundException, File, FileNotFoundException
from System.Text import DecoderFallbackException, UTF8Encoding
from System.Threading import AbandonedMutexException, Mutex


class VisibilityStoreError(Exception):
    """An actionable preference error suitable for the Tab Hider status area."""


def _settings_path():
    root = os.environ.get('APPDATA') or Environment.GetFolderPath(
        Environment.SpecialFolder.ApplicationData)
    if not root:
        raise VisibilityStoreError('The roaming profile folder is unavailable. '
                                   'Check your Windows profile and try again.')
    return os.path.join(root, 'NdevTools', 'TabHider', 'visibility.json')


@contextmanager
def _locked(path):
    # Include the profile path so separate Windows users have separate locks.
    digest = hashlib.sha256(os.path.normcase(path).encode('utf-8')).hexdigest()
    try:
        mutex = Mutex(False, 'Global\\NdevTools.TabHider.' + digest)
        acquired = False
        try:
            try:
                acquired = mutex.WaitOne(2000)
            except AbandonedMutexException:
                acquired = True
            if not acquired:
                raise VisibilityStoreError('Tab Hider settings are busy. Try again.')
            yield
        finally:
            if acquired:
                mutex.ReleaseMutex()
            mutex.Dispose()
    except VisibilityStoreError:
        raise
    except Exception as error:
        raise VisibilityStoreError(u'Could not access {}. Check file permissions '
                                   u'and try again. ({})'.format(path, error))


def _validate(choices):
    if not isinstance(choices, dict):
        raise ValueError('Expected a JSON object.')
    for key, value in choices.items():
        if not isinstance(key, basestring) or not key or type(value) is not bool:
            raise ValueError('Each entry needs a name and a true or false value.')


def _unique_keys(pairs):
    choices = dict(pairs)
    if len(choices) != len(pairs):
        raise ValueError('A setting appears more than once.')
    return choices


def _read(path):
    try:
        contents = File.ReadAllBytes(path)
    except (FileNotFoundException, DirectoryNotFoundException):
        return {}
    try:
        contents = UTF8Encoding(False, True).GetString(contents)
        if contents.startswith(u'\ufeff'):
            contents = contents[1:]
        choices = json.loads(contents, object_pairs_hook=_unique_keys)
        _validate(choices)
        return choices
    except (ValueError, DecoderFallbackException) as error:
        raise VisibilityStoreError(u'Invalid Tab Hider settings in {}. Repair or '
                                   u'rename the file and try again. ({})'.format(path, error))


def read_choices():
    """Read explicit choices. A missing file represents a new profile."""
    path = _settings_path()
    with _locked(path):
        return _read(path)


def save_choices(changes):
    """Merge the supplied keys into the latest file and return all choices."""
    _validate(changes)
    path = _settings_path()
    with _locked(path):
        choices = _read(path)
        if all(choices.get(key) == value for key, value in changes.items()):
            return choices
        choices.update(changes)
        folder = os.path.dirname(path)
        Directory.CreateDirectory(folder)
        temporary = os.path.join(folder, 'visibility-' + Guid.NewGuid().ToString('N') + '.tmp')
        try:
            contents = json.dumps(choices, ensure_ascii=False, indent=2, sort_keys=True)
            File.WriteAllText(temporary, contents + u'\n')
            if File.Exists(path):
                File.Replace(temporary, path, None)
            else:
                File.Move(temporary, path)
        finally:
            File.Delete(temporary)
        return choices
