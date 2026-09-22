"""The Windows bits of running without a titlebar.

Taking the OS titlebar off is one flag; keeping the window usable afterwards
is this file. Three things break when the frame goes, and each was measured
rather than assumed -- the numbers are from this machine, a 1920x1080 screen
with a taskbar 60 pixels tall.

**The resize border goes with the titlebar.** `frameless=True` sets
`FormBorderStyle.None`, and Windows reports the window style without
`WS_THICKFRAME`: a hit test on the bottom-right corner comes back `HTCLIENT`,
so there is nothing to drag. Putting the style bit back -- and only that bit,
leaving `WS_CAPTION` off -- gives `HTBOTTOMRIGHT`, `HTRIGHT`, `HTBOTTOM` and
`HTTOP` again with no titlebar and no message-loop code.

**A borderless window maximizes over the taskbar.** Windows hands a bordered
window the monitor's work area and a borderless one the whole screen, which is
full-screen behaviour rather than maximize: measured at 1928x1088 against a
work area of 1920x1020, so the bottom 68 pixels -- including the Convert
button -- sat behind the taskbar. `MaximizedBounds` is the documented answer.

**`MaximizedBounds` is per monitor**, so it is set again before every maximize
rather than once at startup. A window moved to a second screen with a
different taskbar would otherwise be given the first screen's rectangle.

Everything here is a no-op off Windows, so the app still runs on another
machine -- with an ordinary titlebar, which is the right fallback.
"""

from __future__ import annotations

import ctypes
import sys

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


def on_windows() -> bool:
    return sys.platform == "win32"


class WindowFrame:
    """What the window needs done to it once its frame is gone.

    Holds the pywebview window privately: it is handed to `Api`, and anything
    public on that object is walked -- and recursed into -- when pywebview
    builds the JavaScript proxy.
    """

    def __init__(self, window: object) -> None:
        self._window = window
        self._handle = 0

    # -- called once, when the window is up --------------------------------

    def settle(self) -> None:
        """Put back what framelessness took away. Call from `shown`.

        On the GUI thread, because that is the only thread the form may be
        touched from -- reading `window.native` from another one produces a
        stream of COM errors and no useful result.
        """
        if not on_windows():
            return

        self._handle = self._native_handle()
        self._restore_sizing_border()
        self.before_maximize()

    def _native_handle(self) -> int:
        """The window's HWND, as a number ctypes will take.

        `Handle` is a .NET `IntPtr`, and `int()` will not convert one -- it
        raises a TypeError that pywebview catches and logs, so the whole of
        `settle` silently did nothing and the window came up with no resize
        border and a maximize button that would not restore. `ToInt64` is the
        conversion; pywebview's own code uses `ToInt32` for the same reason.
        """
        try:
            handle = self._window.native.Handle
        except Exception:
            # Every use of the handle is guarded, so a backend that does not
            # offer one costs the frameless extras and nothing else.
            return 0

        for convert in ("ToInt64", "ToInt32"):
            if hasattr(handle, convert):
                return int(getattr(handle, convert)())
        try:
            return int(handle)
        except (TypeError, ValueError):
            return 0

    def _restore_sizing_border(self) -> None:
        """Add WS_THICKFRAME back, leaving the caption off.

        This is the whole of "frameless but still resizable" -- Windows draws
        the invisible grab areas at the edges from this bit alone.
        WS_MINIMIZEBOX goes back with it, because it is what lets the window
        minimize and restore through the taskbar in the ordinary way.
        """
        if not self._handle:
            return

        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(self._handle, GWL_STYLE)
        user32.SetWindowLongW(
            self._handle, GWL_STYLE, style | WS_THICKFRAME | WS_MINIMIZEBOX
        )
        # Without SWP_FRAMECHANGED the new style is stored and not applied:
        # the window keeps the frame it was drawn with until something else
        # makes it recalculate.
        user32.SetWindowPos(
            self._handle,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    # -- called before every maximize --------------------------------------

    def before_maximize(self) -> None:
        """Say how big "maximized" is allowed to be, on this monitor.

        Before *every* maximize, not once: it is a property of the screen the
        window is currently on, and the window can be dragged to another one
        with a taskbar somewhere else.
        """
        if not on_windows():
            return

        try:
            from System.Windows.Forms import Screen

            form = self._window.native
            form.MaximizedBounds = Screen.FromControl(form).WorkingArea
        except Exception:
            # Worth trying and not worth failing over: without it a maximized
            # window covers the taskbar, which is ugly rather than fatal.
            pass

    def follow_monitor(self, *_: object) -> None:
        """Re-apply the maximized bounds when the window moves. Hook to `moved`.

        `before_maximize` is also called from the titlebar's own handler, but
        that runs on the thread serving the page, and the form may only be
        touched from the GUI thread. This runs on the GUI thread, and a move
        is exactly when the answer changes -- dragging to a second screen with
        its taskbar somewhere else is the case it exists for.
        """
        self.before_maximize()

    # -- asked whenever the page needs to know -----------------------------

    def is_maximized(self) -> bool:
        """Whether Windows considers the window maximized.

        Asked of Windows rather than remembered, because the window can be
        maximized without going through this app at all -- Aero Snap, a drag
        to the top edge, Win+Up -- and a remembered flag would then be wrong
        and would stay wrong.
        """
        if not (on_windows() and self._handle):
            return False
        return bool(ctypes.windll.user32.IsZoomed(self._handle))
