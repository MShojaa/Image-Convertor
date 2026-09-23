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

**pywebview drags the window itself, and Windows never finds out.** Its drag
region listens to `mousemove` in the page and calls `pywebviewMoveWindow` with
the offset, so the window is *placed*, frame by frame, by JavaScript. Every
behaviour Windows attaches to dragging a titlebar is attached to the modal move
loop that a real caption drag starts -- edge snapping and its preview, Snap
Assist, the layouts grid, drag-to-the-top to maximize, shake. A window moved by
`SetBounds` gets none of them, which is why the titlebar felt off the grid.

`begin_drag` hands the gesture over instead: release the capture and post
`WM_NCLBUTTONDOWN` with `HTCAPTION`, which is Windows' own "the user has taken
hold of the titlebar". Windows runs the loop from there and every one of those
behaviours comes back, because they are not being imitated.

**Putting `WS_THICKFRAME` back brings a visible frame with it.** The grab areas
are invisible, but DWM still draws the window's border around them -- a line in
the accent colour of whoever's theme is running, or black, outside a window
that is otherwise the app's own colour to its edge. `DWMWA_BORDER_COLOR` is the
one attribute that turns it off, and it is Windows 11 or nothing: on 10 the
call returns a failure HRESULT and the border stays, which is how it looked
before this existed.

Everything here is a no-op off Windows, so the app still runs on another
machine -- with an ordinary titlebar, which is the right fallback.
"""

from __future__ import annotations

import ctypes
import sys

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000

# Windows 11 (build 22000) and later. DWMWA_COLOR_NONE is the documented
# "draw no border at all", as distinct from drawing one in no particular
# colour.
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE

# "The left button went down in the non-client area, on the caption."
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2

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
        self._hide_frame_border()
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

    def _hide_frame_border(self) -> None:
        """Stop DWM drawing a border around the window.

        `WS_THICKFRAME` is what makes the edges draggable and it is also what
        makes them visible: the window came up with a line drawn around it,
        outside a titlebar that is otherwise the app's own colour to the very
        top edge. The style bit has to stay -- without it there is no resizing
        at all -- so the border is turned off at the compositor instead.

        Windows 11 only. On 10 the attribute is unknown, the call returns a
        failure HRESULT, and the border stays: the same window as before.
        """
        if not self._handle:
            return

        try:
            colour = ctypes.c_uint(DWMWA_COLOR_NONE)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(self._handle),
                ctypes.c_uint(DWMWA_BORDER_COLOR),
                ctypes.byref(colour),
                ctypes.sizeof(colour),
            )
        except Exception:
            # Worth trying and not worth failing over, the same as the
            # maximized bounds: a border is ugly rather than fatal.
            pass

    # -- called when the page's titlebar is grabbed ------------------------

    def begin_drag(self) -> bool:
        """Hand a titlebar drag to Windows. True if it took it.

        The page calls this on mousedown in its drag region, instead of
        letting pywebview move the window from JavaScript. Windows then runs
        its own move loop, and the snapping, the previews, Snap Assist and the
        layouts grid come with it -- none of which can be imitated from the
        page, because they are not window positions, they are a modal loop.

        Two details, both of which matter:

        `ReleaseCapture` only lets go of what the *calling thread* has hold
        of, and the mouse is captured by the web view on the GUI thread, while
        this runs on the thread serving the page. So the whole thing is
        marshalled with `Invoke` -- without that it releases nothing, the
        capture stays with the web view, and the move loop gets no mouse.

        `PostMessage`, not `SendMessage`: the move loop does not return until
        the drag ends, and sending would block this thread for as long as the
        user holds the button.
        """
        if not (on_windows() and self._handle):
            return False

        try:
            from System import Action

            form = self._window.native
            form.Invoke(Action(self._grab_caption))
            return True
        except Exception:
            # The page falls back to pywebview's own drag, which moves the
            # window without any of the above -- worse, and not broken.
            return False

    def _grab_caption(self) -> None:
        """The two calls, on the GUI thread. See `begin_drag`."""
        user32 = ctypes.windll.user32
        user32.ReleaseCapture()
        user32.PostMessageW(self._handle, WM_NCLBUTTONDOWN, HTCAPTION, 0)

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
