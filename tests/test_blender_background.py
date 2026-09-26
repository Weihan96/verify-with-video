"""Public single-task CLI against disposable state, never the live desktop."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SingleTaskCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.run = self.root / 'run'
        self.env = dict(os.environ, CODEX_HOME=str(self.root), CODEX_THREAD_ID='isolated-owner')
        self.lease = self.invoke('scripts/desktop_queue.py', 'request')['queue']['current']['lease_id']

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, script, *args, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(result.stdout) if ok else result

    def create(self, *extra, ok=True):
        return self.invoke('experiments/cross_task/group.py', 'create', '--solo',
                           '--run', self.run, '--lease', self.lease, *extra, ok=ok)

    def test_create_uses_actual_task_and_can_close_failed_preparation(self):
        receipt = self.create()
        (self.run / 'background.json').write_text(json.dumps(receipt))
        group = json.loads(pathlib.Path(receipt['group']).read_text())
        self.assertEqual(group['members']['A']['thread_id'], self.env['CODEX_THREAD_ID'])
        self.assertEqual(set(group['members']), {'A'})
        closed = self.invoke('scripts/blender_background.py', 'close', '--run', self.run)
        self.assertTrue(closed['preparation_lease_retained'])
        self.assertEqual(self.invoke('scripts/desktop_queue.py', 'status')['queue']['current']['lease_id'], self.lease)
        self.assertTrue(self.invoke('scripts/blender_background.py', 'close', '--run', self.run)['already_closed'])

    def test_solo_cannot_invite_and_does_not_leave_run_on_rejection(self):
        self.create('--member', 'B=another-task', ok=False)
        self.assertFalse(self.run.exists())

    def test_foreign_task_cannot_operate_or_close(self):
        receipt = self.create()
        (self.run / 'background.json').write_text(json.dumps(receipt))
        self.env['CODEX_THREAD_ID'] = 'another-task'
        for command in ('status', 'admit', 'start', 'close'):
            with self.subTest(command=command):
                result = self.invoke('scripts/blender_background.py', command, '--run', self.run, ok=False)
                self.assertIn('another task', result.stderr)

    def test_invalid_workfile_fails_before_creating_group(self):
        self.invoke('scripts/blender_background.py', 'prepare', '--run', self.run,
                    '--lease', self.lease, '--blend', self.root / 'missing.blend', ok=False)
        self.assertFalse(self.run.exists())

    def test_existing_run_never_overwritten(self):
        self.create()
        self.create(ok=False)

    def test_prepare_requires_real_reservation(self):
        self.invoke('scripts/blender_background.py', 'prepare', '--run', self.run,
                    '--lease', 'wrong', ok=False)
        self.assertFalse(self.run.exists())


if __name__ == '__main__':
    unittest.main()
