# -*- coding: utf-8 -*-
"""UTF-8 personal notes with atomic writes, backups, and conflict detection.

This module has no Revit or WPF dependencies and is testable outside Revit.
"""
import datetime
import hashlib
import io
import json
import os
import re
import tempfile
import uuid

BUILD = '2026-10-18-note-sheets-3'


def _validate_rich(value):
    if (not isinstance(value, dict) or value.get('format') != 'xaml-package'
            or not isinstance(value.get('data'), type(u''))
            or not value['data']
            or not isinstance(value.get('page_color'), type(u''))
            or not re.match(r'^#[a-fA-F0-9]{8}$', value['page_color'])):
        raise ValueError('Invalid formatted note content.')
    return dict(format='xaml-package', data=value['data'], page_color=value['page_color'])


def new_sheet(number=1, orientation='portrait'):
    return dict(name=u'Sheet {}'.format(number), body=u'', orientation=orientation)


def _validate_sheets(value):
    if not isinstance(value, list) or not value:
        raise ValueError('A note must contain at least one sheet.')
    result = []
    for sheet in value:
        if (not isinstance(sheet, dict)
                or not isinstance(sheet.get('name'), type(u''))
                or not isinstance(sheet.get('body'), type(u''))
                or sheet.get('orientation') not in ('portrait', 'landscape')):
            raise ValueError('Invalid note sheet.')
        clean = dict(name=sheet['name'].strip() or u'Sheet {}'.format(len(result) + 1),
                     body=sheet['body'], orientation=sheet['orientation'])
        if sheet.get('rich_text') is not None:
            clean['rich_text'] = _validate_rich(sheet['rich_text'])
        result.append(clean)
    return result


def _active_sheet(value, sheets):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < len(sheets):
        raise ValueError('Invalid active note sheet.')
    return value


def note_sheets(note):
    if 'sheets' in note:
        return _validate_sheets(note['sheets'])
    sheet = new_sheet()
    sheet['body'] = note.get('body', u'')
    if note.get('rich_text') is not None:
        sheet['rich_text'] = _validate_rich(note['rich_text'])
    return [sheet]


class NoteConflictError(Exception):
    pass


def _text(value):
    try:
        return unicode(value)
    except NameError:
        return str(value)


def _digest(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, 'rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def new_note():
    return dict(id=uuid.uuid4().hex, title=u'Untitled note', body=u'',
                created=datetime.datetime.utcnow().isoformat() + 'Z', updated='', revision=None)


def _replace(temporary, path):
    if os.name == 'nt':
        try:
            from System.IO import File
        except ImportError:
            File = None
        if File is not None:
            if os.path.isfile(path):
                File.Replace(temporary, path, path + '.bak', True)
            else:
                File.Move(temporary, path)
            return
    if os.path.isfile(path):
        import shutil
        shutil.copy2(path, path + '.bak')
    replace = getattr(os, 'replace', os.rename)
    replace(temporary, path)


class NoteStore(object):
    def __init__(self, directory):
        self.directory = directory
        if not os.path.isdir(directory):
            os.makedirs(directory)

    def path(self, note_id):
        if not re.match(r'^[a-f0-9]{32}$', note_id or ''):
            raise ValueError('Invalid note identifier.')
        return os.path.join(self.directory, note_id + '.json')

    def load(self, note_id):
        path = self.path(note_id)
        with io.open(path, 'rb') as stream:
            raw = stream.read()
        value = json.loads(raw.decode('utf-8-sig'))
        if (value.get('version') not in (1, 2, 3) or value.get('id') != note_id
                or not isinstance(value.get('title'), type(u''))
                or not isinstance(value.get('body'), type(u''))
                or not isinstance(value.get('created'), type(u''))
                or not isinstance(value.get('updated'), type(u''))):
            raise ValueError('Invalid note file.')
        if value['version'] == 2:
            value['rich_text'] = _validate_rich(value.get('rich_text'))
        if value['version'] == 3:
            value['sheets'] = _validate_sheets(value.get('sheets'))
            value['active_sheet'] = _active_sheet(value.get('active_sheet', 0), value['sheets'])
            value['body'] = u'\n\n'.join(sheet['body'] for sheet in value['sheets'])
        value['revision'] = hashlib.sha256(raw).hexdigest()
        return value

    def list_notes(self):
        notes, failures = [], []
        for filename in os.listdir(self.directory):
            if not re.match(r'^[a-f0-9]{32}\.json$', filename):
                continue
            try:
                notes.append(self.load(filename[:-5]))
            except Exception as error:
                failures.append((filename, _text(error)))
        notes.sort(key=lambda item: item.get('updated', ''), reverse=True)
        return notes, failures

    def save(self, note):
        path = self.path(note['id'])
        if _digest(path) != note.get('revision'):
            raise NoteConflictError('This note changed in another Revit session. Save a copy to keep both versions.')
        value = dict(version=1, id=note['id'], title=_text(note['title']).strip() or u'Untitled note',
                     body=_text(note['body']), created=note['created'],
                     updated=datetime.datetime.utcnow().isoformat() + 'Z')
        if 'sheets' in note:
            value['sheets'] = _validate_sheets(note['sheets'])
            value['active_sheet'] = _active_sheet(note.get('active_sheet', 0), value['sheets'])
            value['body'] = u'\n\n'.join(sheet['body'] for sheet in value['sheets'])
            value['version'] = 3
        elif note.get('rich_text') is not None:
            value['rich_text'] = _validate_rich(note['rich_text'])
            value['version'] = 2
        payload = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        descriptor, temporary = tempfile.mkstemp(prefix='note-', suffix='.tmp', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                if hasattr(os, 'fsync'):
                    os.fsync(stream.fileno())
            # Never truncate an existing note. A failed replacement leaves it intact.
            _replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        value['revision'] = hashlib.sha256(payload).hexdigest()
        note.clear()
        note.update(value)
        return note

    def delete(self, note):
        path = self.path(note['id'])
        if _digest(path) != note.get('revision'):
            raise NoteConflictError('This note changed in another Revit session. Reopen Notes before deleting it.')
        if os.path.isfile(path):
            # Keep the last saved version recoverable, outside the active list.
            archive = os.path.join(self.directory, 'Deleted')
            if not os.path.isdir(archive):
                os.makedirs(archive)
            destination = os.path.join(archive, note['id'] + '-' + uuid.uuid4().hex[:8] + '.json')
            os.rename(path, destination)
