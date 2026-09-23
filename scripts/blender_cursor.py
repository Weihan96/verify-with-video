"""Optional, window-bound Blender input marker. Import inside Blender's main thread.

The input driver calls marker.update(window, x, y) after successful event dispatch.
This module draws evidence annotations only; it does not send or observe input.
"""
import math
import threading

import blf
import bpy
from bpy.app.handlers import persistent

_KEY = '_verify_with_video_cursor_v1'


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Blender cursor must run on the main thread')


def _windows():
    return {w.as_pointer(): w for w in bpy.context.window_manager.windows}


def _registry():
    return bpy.app.driver_namespace.setdefault(_KEY, {})


def _redraw(window):
    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


class CursorMarker:
    """A label in VIEW_3D WINDOW/UI regions, scoped to one exact Window pointer."""

    def __init__(self, window, label, color, size):
        self.window_pointer = window.as_pointer()
        self.label, self.color, self.size = label, color, size
        self.position = None
        self.closed = False
        self._handles = []
        @persistent
        def before_load(_):
            self.stop()
        self._load_handler = before_load
        try:
            for kind in ('WINDOW', 'UI'):
                self._handles.append((bpy.types.SpaceView3D.draw_handler_add(
                    self._draw, (), kind, 'POST_PIXEL'), kind))
            bpy.app.handlers.load_pre.append(self._load_handler)
        except Exception:
            self.stop()
            raise

    def update(self, window, x, y):
        """Mirror dispatched window-local, bottom-left pixel coordinates.

        Returns False for off-window points (marker hidden). A stale/wrong window
        raises instead of silently retargeting. This is not an input-success flag.
        """
        _main_thread()
        if self.closed:
            raise RuntimeError('Cursor marker is closed; enable for the current window')
        live = _windows()
        if self.window_pointer not in live:
            self.stop()
            raise RuntimeError('Cursor target disappeared; explicitly rebind')
        if window.as_pointer() != self.window_pointer:
            raise ValueError('Cursor window mismatch')
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in (x, y)):
            raise ValueError('Cursor coordinates must be finite numbers')
        # On Retina, Window.width/height can be points while Area/Region and
        # event_simulate use backing pixels. Use the actual screen layout.
        areas = window.screen.areas
        width = max((a.x + a.width for a in areas), default=0)
        height = max((a.y + a.height for a in areas), default=0)
        self.position = (x, y) if 0 <= x < width and 0 <= y < height else None
        _redraw(window)
        return self.position is not None

    def hide(self):
        _main_thread()
        self.position = None
        window = _windows().get(self.window_pointer)
        if window:
            _redraw(window)

    def _draw(self):
        if self.closed or self.position is None:
            return
        context = bpy.context
        window, region = context.window, context.region
        if not window or window.as_pointer() != self.window_pointer or not region:
            return
        # A sidebar may overlap the WINDOW region; draw it only in UI.
        if region.type == 'WINDOW' and context.area:
            for other in context.area.regions:
                if other.type == 'UI' and other.width > 1 and (
                    other.x <= self.position[0] < other.x + other.width and
                    other.y <= self.position[1] < other.y + other.height):
                    return
        x, y = self.position[0] - region.x, self.position[1] - region.y
        if not (0 <= x < region.width and 0 <= y < region.height):
            return
        # Clip to this region; never repeat the marker in a neighboring sidebar.
        text = '+ ' + self.label
        blf.size(0, self.size)
        width, height = blf.dimensions(0, text)
        tx = max(1, min(x + 5, region.width - width - 1))
        ty = max(1, min(y + 8, region.height - height - 1))
        blf.enable(0, blf.CLIPPING)
        try:
            blf.clipping(0, 0, 0, region.width, region.height)
            blf.position(0, tx, ty, 0)
            blf.color(0, *self.color)
            blf.draw(0, text)
        finally:
            blf.disable(0, blf.CLIPPING)

    def stop(self):
        """Remove this marker's draw handlers. Safe to call repeatedly."""
        _main_thread()
        self.closed, self.position = True, None
        for handle, kind in self._handles[:]:
            bpy.types.SpaceView3D.draw_handler_remove(handle, kind)
            self._handles.remove((handle, kind))
        registry = _registry()
        if registry.get(self.window_pointer) is self:
            del registry[self.window_pointer]
        if self._load_handler in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.remove(self._load_handler)
        window = _windows().get(self.window_pointer)
        if window:
            _redraw(window)


def enable(window, label='A', color=None, size=17):
    """Enable/replace a marker; default A orange, other labels yellow.

    Does not store scene properties, register operators, timers or input handlers,
    save files, or alter Blender preferences. Call update only after dispatch.
    """
    _main_thread()
    if not isinstance(label, str) or not 1 <= len(label) <= 16 or not label.isprintable():
        raise ValueError('Use a printable label of 1–16 characters')
    if not isinstance(size, int) or isinstance(size, bool) or not 10 <= size <= 48:
        raise ValueError('Font size must be an integer from 10 to 48')
    if color is None:
        color = (1.0, 0.25 if label == 'A' else 0.8, 0.2, 1.0)
    if len(color) != 4 or not all(isinstance(c, (int, float)) and math.isfinite(c)
                                  and 0 <= c <= 1 for c in color):
        raise ValueError('Use four finite RGBA components in [0, 1]')
    pointer = window.as_pointer()
    if pointer not in _windows():
        raise ValueError('Cursor target is not a current Blender window')
    registry = _registry()
    # Reap closed windows when enabling; never reuse their bindings.
    for key, marker in list(registry.items()):
        if key == pointer or key not in _windows():
            marker.stop()
    marker = CursorMarker(window, label, tuple(color), size)
    registry[pointer] = marker
    return marker


def disable_all():
    """Clean up markers, including instances created by earlier imports."""
    _main_thread()
    for marker in list(_registry().values()):
        marker.stop()
