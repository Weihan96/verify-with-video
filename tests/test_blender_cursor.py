"""Lifecycle/coordinate contract tests with Blender drawing API doubles.

These do not replace the real Blender recording before a release.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/blender_cursor.py'


class Window:
    def __init__(self, pointer):
        self.pointer, self.width, self.height = pointer, 1000, 800
        self.screen = types.SimpleNamespace(areas=[types.SimpleNamespace(type='VIEW_3D', x=0, y=0, width=1000, height=800, tag_redraw=MagicMock())])

    def as_pointer(self):
        return self.pointer


class CursorTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Window(1), Window(2)
        self.region = types.SimpleNamespace(type='WINDOW', x=0, y=0, width=700, height=800)
        self.handlers = types.ModuleType('bpy.app.handlers')
        self.handlers.persistent = lambda fn: fn
        self.handlers.load_pre = []
        self.handles = {}
        self.counter = 0

        def add(fn, args, kind, stage):
            self.counter += 1
            self.handles[self.counter] = (fn, kind)
            return self.counter

        def remove(handle, kind):
            self.assertEqual(self.handles.pop(handle)[1], kind)

        self.bpy = types.SimpleNamespace(
            app=types.SimpleNamespace(driver_namespace={}, handlers=self.handlers),
            context=types.SimpleNamespace(window=self.a, region=self.region, area=None,
                window_manager=types.SimpleNamespace(windows=[self.a, self.b])),
            types=types.SimpleNamespace(SpaceView3D=types.SimpleNamespace(
                draw_handler_add=add, draw_handler_remove=remove)))
        self.blf = MagicMock()
        self.blf.dimensions.return_value = (30, 17)
        self.patch = patch.dict(sys.modules, {'bpy': self.bpy, 'blf': self.blf, 'bpy.app.handlers': self.handlers})
        self.patch.start()
        self.module = self.import_module()

    def import_module(self):
        spec = importlib.util.spec_from_file_location('cursor_under_test', SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def tearDown(self):
        self.module.disable_all()
        self.patch.stop()

    def test_only_target_window_and_containing_region_draw(self):
        marker = self.module.enable(self.a)
        marker.update(self.a, 710, 200)
        marker._draw()
        self.blf.draw.assert_not_called()
        self.region.x, self.region.width = 700, 300
        marker._draw()
        self.blf.draw.assert_called_once_with(0, '+ A')
        self.blf.draw.reset_mock()
        self.bpy.context.window = self.b
        marker._draw()
        self.blf.draw.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            marker.update(self.b, 1, 1)

    def test_retina_layout_is_not_clipped_to_window_points(self):
        self.a.width, self.a.height = 500, 400
        marker = self.module.enable(self.a)
        self.assertTrue(marker.update(self.a, 900, 700))

    def test_overlapping_sidebar_draws_only_once(self):
        self.region.width = 1000
        sidebar = types.SimpleNamespace(type='UI', x=700, y=0, width=300, height=800)
        self.bpy.context.area = types.SimpleNamespace(regions=[self.region, sidebar])
        marker = self.module.enable(self.a)
        marker.update(self.a, 710, 100)
        marker._draw()
        self.blf.draw.assert_not_called()
        self.bpy.context.region = sidebar
        marker._draw()
        self.blf.draw.assert_called_once_with(0, '+ A')

    def test_repeat_enable_and_cross_import_cleanup(self):
        first = self.module.enable(self.a)
        second_module = self.import_module()
        second = second_module.enable(self.a, 'B')
        self.assertTrue(first.closed)
        self.assertEqual(len(self.handles), 2)
        self.assertEqual(len(self.handlers.load_pre), 1)
        self.module.disable_all()
        self.assertTrue(second.closed)
        self.assertEqual(self.handles, {})
        self.assertEqual(self.handlers.load_pre, [])
        second.stop()

    def test_file_load_clears_all_bindings(self):
        markers = [self.module.enable(w) for w in [self.a, self.b]]
        for callback in list(self.handlers.load_pre):
            callback(None)
        self.assertEqual(self.handles, {})
        self.assertEqual(self.handlers.load_pre, [])
        for marker in markers:
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                marker.update(self.a, 2, 2)

    def test_closed_window_and_new_binding(self):
        marker = self.module.enable(self.a)
        self.bpy.context.window_manager.windows.remove(self.a)
        with self.assertRaisesRegex(RuntimeError, 'disappeared'):
            marker.update(self.a, 1, 1)
        self.assertTrue(marker.closed)
        with self.assertRaisesRegex(ValueError, 'current'):
            self.module.enable(self.a)

    def test_hide_and_outside_have_no_marker(self):
        marker = self.module.enable(self.a)
        self.assertTrue(marker.update(self.a, 10, 20))
        marker.hide()
        marker._draw()
        self.blf.draw.assert_not_called()
        self.assertFalse(marker.update(self.a, 1000, 800))
        self.assertIsNone(marker.position)

    def test_invalid_inputs_do_not_replace_good_marker(self):
        marker = self.module.enable(self.a)
        for kwargs in [{'label':'a\nb'}, {'size':0}, {'color':(1, 2, 3, 4)}]:
            with self.assertRaises(ValueError):
                self.module.enable(self.a, **kwargs)
        self.assertFalse(marker.closed)
        for xy in [(float('nan'), 2), (1, float('inf')), (True, 3)]:
            with self.assertRaises(ValueError):
                marker.update(self.a, *xy)
        self.assertIsNone(marker.position)

    def test_failed_draw_restores_clipping_state(self):
        marker = self.module.enable(self.a)
        marker.update(self.a, 30, 30)
        self.blf.draw.side_effect = RuntimeError('draw failed')
        with self.assertRaises(RuntimeError):
            marker._draw()
        self.blf.disable.assert_called_once_with(0, self.blf.CLIPPING)

    def test_partial_registration_failure_is_cleaned(self):
        add = self.bpy.types.SpaceView3D.draw_handler_add
        calls = []
        def fail_second(*args):
            calls.append(args)
            if len(calls) == 2:
                raise RuntimeError('registration failed')
            return add(*args)
        self.bpy.types.SpaceView3D.draw_handler_add = fail_second
        with self.assertRaises(RuntimeError):
            self.module.enable(self.a)
        self.assertEqual(self.handles, {})
        self.assertEqual(self.handlers.load_pre, [])


if __name__ == '__main__':
    unittest.main()
