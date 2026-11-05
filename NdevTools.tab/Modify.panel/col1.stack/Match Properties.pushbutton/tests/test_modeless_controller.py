"""Exercise controller lifecycle without requiring a running Revit application."""
import ast
import os
import types
import unittest


class Cancelled(Exception):
    pass


class Window(object):
    def __init__(self):
        self.IsEnabled = True
        self.hidden = False

    def Hide(self):
        self.hidden = True


class ModelessTests(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'script.py')
        with open(path, encoding='utf-8') as stream:
            tree = ast.parse(stream.read())
        tree.body = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MatchController']
        self.alerts = []
        env = {'OperationCanceledException': Cancelled,
               'forms': types.SimpleNamespace(alert=lambda text, **kw: self.alerts.append(text)),
               'traceback': types.SimpleNamespace(format_exc=lambda: ''),
               'ObjectType': types.SimpleNamespace(Element=1),
               'adapter': types.SimpleNamespace(ModelFilter=lambda: None)}
        exec(compile(tree, path, 'exec'), env)
        self.c = env['MatchController'].__new__(env['MatchController'])
        self.c.closed = False
        self.c.pending = None
        self.c.executing = False
        self.c.start = Window()
        self.c.selection = None
        self.disposed = []
        self.c.event = types.SimpleNamespace(Raise=lambda: 'Accepted', Dispose=lambda: self.disposed.append(True))
        self.restored = []
        self.c.show = lambda: self.restored.append(True)
        self.c.doc = types.SimpleNamespace(IsValidObject=True, IsReadOnly=False, IsModifiable=False)

    def test_request_waits_for_external_event_and_prevents_double_queue(self):
        self.c.request('source')
        self.assertEqual('source', self.c.pending)
        self.assertFalse(self.c.start.IsEnabled)
        self.c.request('targets')
        self.assertEqual('source', self.c.pending)

    def test_rejected_raise_reenables_window(self):
        self.c.event.Raise = lambda: 'Denied'
        self.c.request('source')
        self.assertIsNone(self.c.pending)
        self.assertTrue(self.c.start.IsEnabled)
        self.assertTrue(self.alerts)

    def test_switched_document_does_not_select_or_write(self):
        self.c.pending = 'source'
        self.c.execute(types.SimpleNamespace(ActiveUIDocument=types.SimpleNamespace(Document=object())))
        self.assertTrue(self.alerts)
        self.assertFalse(self.c.start.hidden)
        self.assertIsNone(self.c.pending)
        self.assertTrue(self.restored)

    def test_escape_returns_to_window(self):
        def pick(*args):
            raise Cancelled()
        uidoc = types.SimpleNamespace(Document=self.c.doc, Selection=types.SimpleNamespace(PickObject=pick))
        self.c.pending = 'source'
        self.c.execute(types.SimpleNamespace(ActiveUIDocument=uidoc))
        self.assertTrue(self.c.start.hidden)
        self.assertTrue(self.restored)
        self.assertFalse(self.alerts)
        self.assertIsNone(self.c.pending)

    def test_closed_window_cancels_pending_action(self):
        self.c.closed = True
        self.c.pending = 'source'
        self.c.execute(None)
        self.assertTrue(self.disposed)
        self.assertIsNone(self.c.pending)
