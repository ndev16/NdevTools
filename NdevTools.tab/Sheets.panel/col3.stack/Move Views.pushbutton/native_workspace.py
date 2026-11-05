# -*- coding: utf-8 -*-
"""Screen geometry for the native sheet workspace. Revit supplies screen pixels."""


def rectangle(r):
    if r is not None and r.Right > r.Left and r.Bottom > r.Top:
        return (r.Left, r.Top, r.Right, r.Bottom)


def arrangement(source, target):
    if not source or not target:
        return None
    # Adjacent views may be separated by a splitter or one rounded device pixel.
    if source[0] >= target[2] - 1:
        return 'Destination left, source right.'
    if target[0] >= source[2] - 1:
        return 'Source left, destination right.'
    if source[1] >= target[3] - 1:
        return 'Destination above, source below.'
    if target[1] >= source[3] - 1:
        return 'Source above, destination below.'
    return None


def zoom_corners(paper, viewport, toolbar):
    """Fit the whole paper inside the visible part of this tile, in sheet feet."""
    x1, y1, x2, y2 = paper
    left, top, right, bottom = viewport
    if x2 <= x1 or y2 <= y1 or right <= left or bottom <= top:
        return None
    cover = 0
    if (toolbar and toolbar[0] < right and toolbar[2] > left
            and toolbar[1] <= top + 2 and toolbar[3] > top):
        cover = min(toolbar[3] - top, (bottom-top) * 0.6)
    units = 1.06 * max((x2-x1) / float(right-left), (y2-y1) / float(bottom-top-cover))
    cx, cy = (x1+x2) / 2., (y1+y2 + cover*units) / 2.
    hw, hh = (right-left) * units / 2., (bottom-top) * units / 2.
    return cx-hw, cy-hh, cx+hw, cy+hh


def toolbar_rectangle(window):
    from System.Windows.Interop import WindowInteropHelper
    from pyrevit import labs
    try:
        return rectangle(labs.Common.User32.GetWindowRect(WindowInteropHelper(window).Handle))
    except Exception:
        return None


def fit_toolbar(app, window):
    """Move only our owned WPF toolbar; leave Revit's document windows untouched."""
    from System import IntPtr
    from System.Windows import WindowState
    from System.Windows.Interop import WindowInteropHelper
    from System.Windows.Media import VisualTreeHelper
    if window.WindowState == WindowState.Minimized:
        window.WindowState = WindowState.Normal
    try:
        rect = rectangle(app.DrawingAreaExtents)
        if rect is None:
            return
        import clr
        clr.AddReference('ControlzEx')
        from ControlzEx.Standard import NativeMethods, SWP
        flag = SWP.NOACTIVATE | SWP.NOZORDER
        handle = WindowInteropHelper(window).Handle
        left, top, right, bottom = rect
        # Move first: WPF updates the HWND's monitor DPI when it changes monitor.
        height_dip = window.ActualHeight
        NativeMethods.SetWindowPos(handle, IntPtr.Zero, left, top, 0, 0, flag | SWP.NOSIZE)
        dpi = VisualTreeHelper.GetDpi(window).DpiScaleY
        height = max(1, min(bottom - top, int(round(height_dip * dpi))))
        NativeMethods.SetWindowPos(handle, IntPtr.Zero, left, top, right-left, height, flag)
    except Exception:
        # On hosts without geometry or native positioning the owner-centred toolbar still works.
        return
