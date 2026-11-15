# -*- coding: utf-8 -*-
"""Exercise the NdevTools result dialog through cross-project Paste in two unsaved projects."""
import imp
import math
import os
import tempfile
import traceback

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import IntPtr
from System.IO import File
from System.Windows import Rect, Size, SystemParameters
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Media import PixelFormats
from System.Windows.Media.Imaging import BitmapFrame, PngBitmapEncoder, RenderTargetBitmap
from pyrevit import DB

fixture = imp.load_source('sheet_report_fixture', os.path.join(os.path.dirname(__file__), 'revit_cross_project_smoke.py'))
command = fixture.command


def run(uiapp):
    app = uiapp.Application
    source = app.NewProjectDocument(DB.UnitSystem.Imperial)
    dest = None
    try:
        dest = app.NewProjectDocument(DB.UnitSystem.Imperial)
        a, originals = fixture.sample(source, True)
        b, ignored = fixture.sample(dest, False)
        tx = DB.Transaction(source, 'Foundation plan on a sheet')
        with tx:
            tx.Start()
            types = DB.FilteredElementCollector(source).OfClass(DB.ViewFamilyType)
            family = next(t for t in types if t.ViewFamily == DB.ViewFamily.StructuralPlan)
            level = next(iter(DB.FilteredElementCollector(source).OfClass(DB.Level)))
            plan = DB.ViewPlan.Create(source, family.Id, level.Id)
            plan.Name = 'FOUNDATION PLAN'
            placement = DB.Viewport.Create(source, a.Id, plan.Id, DB.XYZ(.1, .2, 0))
            assert tx.Commit() == DB.TransactionStatus.Committed
        copy = fixture.Context(source, a)
        paste = fixture.Context(dest, b)
        paste.MainWindowHandle = uiapp.MainWindowHandle
        picker = command.Dialog(a.Name, [], set(), 'copy', IntPtr.Zero)
        assert picker.ChooseButton.Style is not None and picker.window.Icon is not None
        picker.window.Close()
        native_report = command.report_skips
        seen = []
        def inspect(window):
            try:
                assert WindowInteropHelper(window).Owner == uiapp.MainWindowHandle
                assert window.FindName('BrandLogo').Source is not None
                count = len(seen)
                assert window.FindName('Summary').Text == command.tr('summary', count, 1)
                rows = window.FindName('SkippedItems')
                assert rows.Items.Count == 1 and 'FOUNDATION PLAN' in rows.Items[0].Key
                assert rows.Items[0].Value == command.tr('structural_plan_skip')
                button = window.FindName('DismissButton')
                assert button.IsCancel and button.IsDefault and button.Style is not None
                # Journal playback cannot drive a modal WPF window. Lay out its
                # actual visual tree at the same width and height limit as Paste.
                panel = window.Content
                panel.Measure(Size(window.Width, window.MaxHeight))
                size = panel.DesiredSize
                panel.Arrange(Rect(0, 0, window.Width, size.Height))
                panel.UpdateLayout()
                assert 0 < size.Height <= SystemParameters.WorkArea.Height
                if app.VersionNumber == '2025' and not seen:
                    bitmap = RenderTargetBitmap(int(window.Width), int(math.ceil(size.Height)),
                                                96, 96, PixelFormats.Pbgra32)
                    bitmap.Render(panel)
                    encoder = PngBitmapEncoder()
                    encoder.Frames.Add(BitmapFrame.Create(bitmap))
                    path = os.path.join(tempfile.gettempdir(), 'NdevTools-paste-result-2025.png')
                    stream = File.Create(path)
                    try:
                        encoder.Save(stream)
                    finally:
                        stream.Dispose()
                seen.append(rows.Items[0].Key)
            finally:
                window.Close()

        command.report_skips = lambda placed, skipped, data, owner=None: native_report(
            placed, skipped, data, show=inspect, owner=owner)
        note = next(e for e in originals if isinstance(e, DB.TextNote))
        for items in ([placement], [placement, note]):
            copy.ids = [e.Id for e in items]
            command.main(copy, 'copy')
            result = command.main(paste, 'paste')
            assert len(result) == len(items) - 1
        assert len(seen) == 2
        print('PASS Revit {} branded Paste report, skipped foundation plan, mixed paste and owner'.format(app.VersionNumber))
    finally:
        if dest is not None:
            dest.Close(False)
        source.Close(False)


if __name__ == '__main__':
    try:
        run(__revit__)
    except Exception:
        print(traceback.format_exc())
        raise
