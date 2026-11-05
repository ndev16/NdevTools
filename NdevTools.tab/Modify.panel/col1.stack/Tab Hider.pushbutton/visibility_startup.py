# -*- coding: utf-8 -*-
"""Restore the shared Tab Hider profile after Revit builds or switches ribbons."""
import imp
import os

from System import AppDomain
from pyrevit.coreutils.logger import get_logger


# Both editions manage the same ribbon in the same Revit process.
REGISTRY = 'NdevTools.TabHider.Restoration'
LOGGER = get_logger('NdevTabHider')
MAX_PASSES = 5


class RibbonRestorer(object):
    def __init__(self, host, read_choices, restore_visibility):
        self.host = host
        self.read_choices = read_choices
        self.restore_visibility = restore_visibility
        self.idling = False
        self.listening = False
        self.choices = None
        self.passes = 0

    def start(self):
        self.host.ViewActivated += self.queue
        self.listening = True
        self.queue()

    def queue(self, sender=None, args=None):
        self.choices = None
        self.passes = 0
        if not self.idling:
            self.host.Idling += self.on_idle
            self.idling = True

    def end_idle(self):
        if self.idling:
            self.host.Idling -= self.on_idle
            self.idling = False

    def stop(self):
        self.end_idle()
        if self.listening:
            self.host.ViewActivated -= self.queue
            self.listening = False

    def on_idle(self, uiapp, args):
        if self.choices is None:
            try:
                self.choices = self.read_choices()
            except Exception as error:
                LOGGER.warning('Could not read saved ribbon choices: {}'.format(error))
                self.end_idle()
                return
        if not self.choices:
            self.end_idle()
            return

        self.passes += 1
        try:
            handled = self.restore_visibility(uiapp, self.choices)
            # A later idle subscriber may rebuild tabs/panels after our first pass.
            if self.passes >= 2 and set(self.choices).issubset(handled):
                self.end_idle()
                return
        except Exception as error:
            if self.passes >= MAX_PASSES:
                LOGGER.warning('Could not restore ribbon choices: {}'.format(error))

        # Uninstalled add-ins and tabs belonging to another document can be absent.
        if self.passes >= MAX_PASSES:
            self.end_idle()


def install(host):
    folder = os.path.dirname(__file__)
    store = imp.load_source('ndev_tab_hider_store', os.path.join(folder, 'visibility_store.py'))
    items = imp.load_source('ndev_tab_hider_items', os.path.join(folder, 'visibility_items.py'))
    domain = AppDomain.CurrentDomain
    previous = domain.GetData(REGISTRY)
    if previous is not None:
        previous.stop()
        domain.SetData(REGISTRY, None)

    session = RibbonRestorer(host, store.read_choices, items.restore_visibility)
    try:
        session.start()
        domain.SetData(REGISTRY, session)
    except Exception:
        session.stop()
        raise


def queue_restore():
    """Discard any pending idle snapshot after the dialog saves newer choices."""
    session = AppDomain.CurrentDomain.GetData(REGISTRY)
    if session is not None:
        session.queue()
