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

**The bit that gives the edges back does not know about maximizing.** Windows
does not let you resize a maximized window -- there is nothing to resize it to
-- but `WS_THICKFRAME` is a style, not a state, so a maximized window still had
eight live grab areas and could be dragged smaller by its edge without ever
leaving the maximized state. The bit follows the state now: off while
maximized, back on when restored, and `resized` is the event that says which,
because it fires whichever way the window got there.

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
GWLP_WNDPROC = -4
WM_NCCALCSIZE = 0x0083
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000

# Windows 11 (build 22000) and later. DWMWA_COLOR_NONE is the documented
# "draw no border at all", as distinct from drawing one in no particular
# colour.
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE

# Rounded corners, the Windows 11 look. Maximized windows are square, because
# a rounded corner against the edge of the screen is a notch out of it.
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2

# "The left button went down in the non-client area", and where. Windows runs
# its own loop from these: HTCAPTION moves the window, the eight others size
# it, both with all the snapping that goes with them.
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
EDGES = {
    "left": 10,
    "right": 11,
    "top": 12,
    "top-left": 13,
    "top-right": 14,
    "bottom": 15,
    "bottom-left": 16,
    "bottom-right": 17,
}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
)


def _declare(user32) -> None:
    """Tell ctypes the shapes of the two calls that pass pointers.

    ctypes defaults a function's return type to `c_int`, and on 64-bit that
    truncates the window procedure `SetWindowLongPtrW` hands back. Chaining to
    a pointer with its top half cut off does not fail: the window stops
    answering, which is the hang this cost an evening to.
    """
    user32.SetWindowLongPtrW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.CallWindowProcW.restype = LRESULT

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


def corner_preference(maximized: bool) -> int:
    """How the window's corners should be drawn in this state.

    Rounded when the window floats, square when it is maximized -- a rounded
    corner against the edge of the screen is a notch out of the screen, and
    Windows draws its own windows square for exactly that reason.

    It has to be DWM rather than a border-radius on the page: the page is
    drawn inside the window, and a radius there rounds the content while the
    window stays square, so the corners fill with whatever is behind.
    """
    return DWMWCP_DONOTROUND if maximized else DWMWCP_ROUND


def with_sizing_border(style: int) -> int:
    """The window style a frameless window needs to still be a window.

    `WS_THICKFRAME` is what Windows reads to decide a window may be sized at
    all -- and with it, snapped to an edge, maximized to the work area, moved
    by Win+arrow. `WS_MINIMIZEBOX` is what lets it minimize and restore
    through the taskbar. Neither is about the frame being drawn: the frame
    they bring is taken away again in `_take_the_frame`.

    It was `sizing_style(style, maximized)`, and it took the border off a
    maximized window so its edges could not resize it. That is the page's job
    now -- it hides its edges when maximized -- because doing it here meant a
    style change on every maximize, and that is what repainted the frame
    white.
    """
    return style | WS_THICKFRAME | WS_MINIMIZEBOX


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
        # The subclass, and the two things that must outlive this call: a
        # WNDPROC that Python may not collect while Windows still calls it,
        # and the proc it replaced.
        self._proc = None
        self._old_proc = None

    # -- called once, when the window is up --------------------------------

    def settle(self) -> None:
        """Put back what framelessness took away. Call from `shown`.

        On the GUI thread, because that is the only thread the form may be
        touched from -- reading `window.native` from another one produces a
        stream of COM errors and no useful result.
        """
        if not on_windows():
            return

        if not self._ensure_handle():
            # `shown` fires before the native window has a handle to give --
            # measured: at this point the form reports none, so every call
            # below used to bail and the window came up with no resize border,
            # no rounded corners and its frame colour untouched. The first
            # `moved` or `resized` picks it up instead.
            return

        self._take_the_frame()
        self._restore_sizing_border()
        self._hide_frame_border()
        self.follow_state()
        self.before_maximize()

    def _ensure_handle(self) -> bool:
        """The handle, once there is one. Asked again until there is.

        `shown` is too early -- see `settle` -- so every entry point that
        needs the handle asks through here rather than trusting what `settle`
        found, and the whole setup runs the first time one succeeds.
        """
        if self._handle:
            return True

        self._handle = self._native_handle()
        return bool(self._handle)

    def _restore_sizing_border(self) -> None:
        """Add WS_THICKFRAME back, leaving the caption off, and leave it on.

        It is what Windows reads to decide a window may be snapped to an edge,
        maximized to the work area and sized at all -- the whole of "frameless
        but still resizable". WS_MINIMIZEBOX goes with it, because it is what
        lets the window minimize and restore through the taskbar.

        It stays on in every state now. Taking it off a maximized window --
        which is how the edges were stopped from resizing one -- meant a style
        change and `SWP_FRAMECHANGED` on every maximize, and that is what
        repainted the frame white. `_take_the_frame` removes the frame it
        brings, and the page stops offering its edges when maximized.
        """
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(self._handle, GWL_STYLE)
        wanted = with_sizing_border(style)
        if wanted == style:
            return

        user32.SetWindowLongW(self._handle, GWL_STYLE, wanted)
        # Without SWP_FRAMECHANGED the new style is stored and not applied:
        # the window keeps the frame it was drawn with until something else
        # makes it recalculate. Here it is wanted -- it is what makes Windows
        # ask WM_NCCALCSIZE again, and the hook answers "all of it".
        user32.SetWindowPos(
            self._handle,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    def _take_the_frame(self) -> None:
        """Make the client area the whole window, frame included.

        `WS_THICKFRAME` is the only way to get the resize edges and the
        snapping back, and it comes with a non-client frame: measured on this
        machine at 8px on every side, with the web view moved to +8,+8 and
        those 8 pixels painted by nobody -- black at first, white after the
        frame is recalculated. That is the border that was never a border.

        `WM_NCCALCSIZE` is where a window says how much of itself is client.
        Answering "all of it" leaves the style bit -- so Windows still snaps
        the window and still maximizes it to the work area -- with nothing
        left over to paint. The page then reaches all four edges, which is the
        whole point of drawing our own titlebar.

        What it costs is the mouse: with no non-client area there is nothing
        for Windows to hit-test, so the edges stop being draggable. `app.js`
        puts that back, the same way it drags the window -- see `begin_resize`.
        """
        if self._proc is not None:
            return

        user32 = ctypes.windll.user32
        _declare(user32)

        def hook(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_NCCALCSIZE and wparam:
                    # The proposed window rectangle, unmodified, becomes the
                    # client rectangle.
                    return 0
                return user32.CallWindowProcW(
                    self._old_proc, hwnd, msg, wparam, lparam
                )
            except Exception:
                # This runs on the GUI thread inside Windows' own dispatch.
                # Raising here would take the window with it.
                return 0

        proc = WNDPROC(hook)
        old = user32.SetWindowLongPtrW(
            self._handle, GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p)
        )
        if not old:
            # Nothing to chain to. Leaving the hook installed would be a
            # window that answers no message at all.
            return

        # Only now, and in this order: the hook can be called the instant it
        # is installed, and it reads both of these.
        self._old_proc = old
        self._proc = proc

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

    def follow_state(self, *_: object) -> None:
        """What changes when the window is maximized or put back.

        Hooked to `resized`, which fires however the window got there -- this
        app's own maximize button, Aero Snap, Win+Up, a drag to the top edge,
        the taskbar. On the GUI thread, like `moved`. It is also the first
        thing to run with a usable handle, so it finishes what `settle` could
        not start.

        Only the corners now. It used to take `WS_THICKFRAME` off a maximized
        window as well, to stop the edges resizing one -- and that meant a
        style change and `SWP_FRAMECHANGED` on every maximize, which is what
        repainted the non-client frame white. There is no non-client frame any
        more, and no style to toggle: the edges belong to the page, and it
        stops offering them when the window is maximized.
        """
        if not (on_windows() and self._ensure_handle()):
            return

        if self._proc is None:
            # `settle` ran before there was a handle. Everything it does is
            # idempotent, so this is where it actually happens.
            self.settle()

        self._set_corners(self.is_maximized())

    def _set_corners(self, maximized: bool) -> None:
        """Round the window's corners, or square them off.

        Windows 11 only, and silent about it: on 10 the attribute is unknown,
        the call returns a failure HRESULT, and the window keeps the square
        corners every window on that desktop has.
        """
        self._set_dwm_attribute(
            DWMWA_WINDOW_CORNER_PREFERENCE, corner_preference(maximized)
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
        self._set_dwm_attribute(DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)

    def _set_dwm_attribute(self, attribute: int, value: int) -> None:
        """One DWORD to the compositor, and never a reason to fail.

        Every attribute used here is Windows 11's. On 10 the call returns a
        failure HRESULT and the window looks the way it did before, which is
        the right outcome for all of them.
        """
        if not (on_windows() and self._handle):
            return

        try:
            word = ctypes.c_uint(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(self._handle),
                ctypes.c_uint(attribute),
                ctypes.byref(word),
                ctypes.sizeof(word),
            )
        except Exception:
            # Worth trying and not worth failing over, the same as the
            # maximized bounds: square corners and a visible border are ugly
            # rather than fatal.
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
        if not (on_windows() and self._ensure_handle()):
            return False

        # A refusal leaves the page to fall back to pywebview's own drag,
        # which moves the window without any of the above -- worse, and not
        # broken.
        return self._hand_over(HTCAPTION)

    def begin_resize(self, edge: str) -> bool:
        """Hand a resize to Windows, from one of the page's eight edges.

        The same trade as `begin_drag`, and the other half of
        `_take_the_frame`: with no non-client area there is nothing for
        Windows to hit-test, so the edges stopped being draggable by the
        mouse. The page knows where the pointer is and says which edge;
        Windows runs the loop and brings its snapping with it.
        """
        code = EDGES.get(edge)
        if code is None or not (on_windows() and self._ensure_handle()):
            return False

        return self._hand_over(code)

    def _hand_over(self, code: int) -> bool:
        """Start one of Windows' own loops: move for the caption, size for an
        edge.

        Marshalled onto the GUI thread, and posted rather than sent -- both
        for the reasons in `begin_drag`.
        """
        try:
            from System import Action

            form = self._window.native
            form.Invoke(Action(lambda: self._grab(code)))
            return True
        except Exception:
            return False

    def _grab(self, code: int) -> None:
        """The two calls, on the GUI thread. See `begin_drag`."""
        user32 = ctypes.windll.user32
        user32.ReleaseCapture()
        user32.PostMessageW(self._handle, WM_NCLBUTTONDOWN, code, 0)

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
