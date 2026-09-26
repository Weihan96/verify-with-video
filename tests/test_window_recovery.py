"""Offline lifecycle regression tests; desktop and real queue access are forbidden."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    spec = importlib.util.spec_from_file_location("window_recovery_desktop", SCRIPTS / "desktop.py")
    desktop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desktop)
finally:
    sys.path.pop(0)


class WindowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / "evidence"
        self.work.mkdir()
        self.own = "window-recovery-test"
        self.exe = str(Path(sys.executable).resolve())
        self.pid = 4242
        self.birth = "original process identity"
        self.receipt_path = self.root / "launch.json"
        self.record = dict(thread_id=self.own, pid=self.pid, identity=self.birth,
                           executable=self.exe, receipt=self.receipt())
        self.write(self.receipt_path, self.record)
        for mocker in (
            patch.dict(os.environ, {"CODEX_THREAD_ID": self.own, "CODEX_HOME": str(self.root)}),
            patch.object(desktop, "check", return_value=self.own),
            patch.object(desktop, "identity", return_value=self.birth),
            patch.object(desktop, "process_executable", return_value=self.exe),
            patch.object(desktop.subprocess, "check_output", return_value=self.exe + " " + self.record["receipt"]["owner"]["marker"]),
            patch.object(desktop, "native", side_effect=AssertionError("Real desktop forbidden")),
            patch.object(desktop.os, "kill", side_effect=AssertionError("Real signals forbidden")),
            patch.object(desktop.time, "sleep"),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def receipt(self, basis="codex_thread", who=None):
        owner_id = hashlib.sha256(f"{basis}:{who or self.own}".encode()).hexdigest()[:20]
        return dict(status="started", pid=self.pid,
                    owner=dict(basis=basis, id=owner_id, marker=f"--codex-task-owner={owner_id}"))

    def cli(self, *args):
        with patch.object(sys, "argv", ["desktop.py", *map(str, args)]):
            return desktop.main()

    def close_receipt(self):
        return self.cli("close", "--lease-id", "lease", "--launch-record", self.receipt_path)

    def registry(self):
        return desktop.registry_path(self.own, self.pid, self.birth)

    def session(self):
        session = self.root / "session.json"
        self.write(self.registry(), {"recording": None})
        self.write(session, dict(thread_id=self.own, lease_id="lease", pid=self.pid,
                                window=10, executable=self.exe, identity=self.birth,
                                work=str(self.work), registry=str(self.registry()),
                                launch=self.record, recording=None))
        return session

    def test_valid_receipt_closes_without_window_or_focus_and_verifies_exit(self):
        killed = []
        def identify(pid):
            if killed:
                raise subprocess.CalledProcessError(1, ["ps", "-p", str(pid)])
            return self.birth
        with patch.object(desktop, "identity", side_effect=identify), patch.object(desktop.os, "kill", side_effect=lambda pid, sig: killed.append((pid, sig))):
            result = self.close_receipt()
        self.assertEqual(killed, [(self.pid, 15)])
        self.assertTrue(result["verified_exited"])
        self.assertIn("closed", json.loads(self.receipt_path.read_text()))
        desktop.native.assert_not_called()

    def test_transient_termination_identity_then_absence_succeeds_with_one_signal(self):
        absent = subprocess.CalledProcessError(1, ["ps", "-p", str(self.pid)])
        with patch.object(desktop, "identity", side_effect=[self.birth, self.birth, "transient zombie name", absent]), patch.object(desktop.os, "kill") as signal:
            result = self.close_receipt()
        signal.assert_called_once_with(self.pid, 15)
        self.assertTrue(result["verified_exited"])
        self.assertIn("closed", json.loads(self.receipt_path.read_text()))
        desktop.time.sleep.assert_called_once_with(.1)

    def test_persistent_changed_identity_fails_without_another_signal(self):
        with patch.object(desktop, "identity", side_effect=[self.birth, self.birth] + ["replacement process"] * 100), patch.object(desktop.os, "kill") as signal:
            with self.assertRaisesRegex(ValueError, "PID identity changed after signal.*no further signal"):
                self.close_receipt()
        signal.assert_called_once_with(self.pid, 15)
        self.assertNotIn("closed", json.loads(self.receipt_path.read_text()))
        self.assertEqual(desktop.time.sleep.call_count, 100)

    def test_launcher_environment_owner_override_is_rejected_before_launch(self):
        with patch.dict(os.environ, {"PROJECT_CONTROL_TASK_ID": "another-task"}):
            with self.assertRaisesRegex(ValueError, "task override conflicts"):
                self.cli("launch", "--lease-id", "lease", "--work", self.work,
                         "--launch-record", self.root / "new-launch.json", "--executable", self.exe,
                         "--bonsai-launcher", self.root / "launcher.ts", "--worktree", self.root)
        desktop.subprocess.check_output.assert_not_called()
        desktop.os.kill.assert_not_called()

    def test_launcher_argument_owner_override_is_rejected_before_launch(self):
        for index, args in enumerate((["--task-id", "another-task"], ["--task-id=another-task"])):
            with self.subTest(args=args), patch.dict(os.environ, {"PROJECT_CONTROL_TASK_ID": ""}):
                with self.assertRaisesRegex(ValueError, "Do not override current task identity"):
                    self.cli("launch", "--lease-id", "lease", "--work", self.work,
                             "--launch-record", self.root / f"new-launch-{index}.json", "--executable", self.exe,
                             "--bonsai-launcher", self.root / "launcher.ts", "--worktree", self.root, "--", *args)
                desktop.subprocess.check_output.assert_not_called()
                desktop.os.kill.assert_not_called()

    def test_valid_current_task_explicit_owner_receipt_is_accepted(self):
        self.record["receipt"] = self.receipt("explicit_task")
        self.write(self.receipt_path, self.record)
        with patch.object(desktop.subprocess, "check_output", return_value=self.exe + " " + self.record["receipt"]["owner"]["marker"]):
            loaded = desktop.load_launch(self.receipt_path, self.own)
        self.assertEqual(loaded["receipt"]["owner"]["basis"], "explicit_task")

    def test_existing_launcher_process_never_creates_close_ownership(self):
        receipt = self.root / 'not-new.json'
        with patch.dict(os.environ, {'PROJECT_CONTROL_TASK_ID': ''}), patch.object(desktop, 'launcher_output', return_value=json.dumps({'status':'existing','pid':self.pid})):
            with self.assertRaisesRegex(ValueError, 'existing process'):
                self.cli('launch','--lease-id','lease','--work',self.work,'--launch-record',receipt,
                         '--executable',self.exe,'--bonsai-launcher',self.root/'launcher.ts','--worktree',self.root)
        self.assertFalse(receipt.exists())
        desktop.os.kill.assert_not_called()

    def test_launcher_failures_preserve_only_uncertain_launch_receipts(self):
        for index,(response,error,retained) in enumerate([
            (json.dumps({'status':'not_started','error':'invalid setup'}),None,False),
            (None,subprocess.CalledProcessError(1,['bun']),True),
        ]):
            receipt=self.root/f'failure-{index}.json'
            with self.subTest(index=index), patch.dict(os.environ, {'PROJECT_CONTROL_TASK_ID':''}), patch.object(desktop,'launcher_output',return_value=response,side_effect=error):
                with self.assertRaises((ValueError,OSError,subprocess.CalledProcessError)):
                    self.cli('launch','--lease-id','lease','--work',self.work,'--launch-record',receipt,
                             '--executable',self.exe,'--bonsai-launcher',self.root/'launcher.ts','--worktree',self.root)
                self.assertEqual(receipt.exists(),retained)
        desktop.os.kill.assert_not_called()

    def test_only_failure_to_spawn_launcher_clears_pending_receipt(self):
        pending={'thread_id':self.own,'status':'launching','request_id':'test'}
        self.write(self.receipt_path,pending)
        with patch.object(desktop.subprocess,'Popen',side_effect=FileNotFoundError('bun missing')):
            with self.assertRaises(FileNotFoundError):desktop.launcher_output(['bun'],self.receipt_path,pending)
        self.assertFalse(self.receipt_path.exists())
        self.write(self.receipt_path,pending)
        with patch.object(desktop.subprocess,'Popen') as spawn:
            spawn.return_value.communicate.side_effect=OSError('pipe read failed after spawn')
            with self.assertRaises(OSError):desktop.launcher_output(['bun'],self.receipt_path,pending)
        self.assertEqual(json.loads(self.receipt_path.read_text()),pending)

    def test_foreign_thread_receipt_is_rejected_before_signal(self):
        self.write(self.receipt_path, {**self.record, "thread_id": "another-task"})
        with self.assertRaises(ValueError):
            self.close_receipt()
        desktop.os.kill.assert_not_called()

    def test_stale_process_identity_is_rejected_before_signal(self):
        with patch.object(desktop, "identity", return_value="reused PID"):
            with self.assertRaises(ValueError):
                self.close_receipt()
        desktop.os.kill.assert_not_called()

    def test_changed_executable_is_rejected_before_signal(self):
        with patch.object(desktop, "process_executable", return_value="/another/app"):
            with self.assertRaises(ValueError):
                self.close_receipt()
        desktop.os.kill.assert_not_called()

    def test_foreign_owner_marker_is_rejected_even_when_process_command_matches(self):
        self.record["receipt"] = self.receipt(who="another-task")
        self.write(self.receipt_path, self.record)
        with patch.object(desktop.subprocess, "check_output", return_value=self.exe + " " + self.record["receipt"]["owner"]["marker"]):
            with self.assertRaises(ValueError):
                self.close_receipt()
        desktop.os.kill.assert_not_called()

    def test_owner_marker_must_be_a_whole_process_argument(self):
        marker = self.record["receipt"]["owner"]["marker"]
        with patch.object(desktop.subprocess, "check_output", return_value=self.exe + " " + marker + "-different"):
            with self.assertRaises(ValueError):
                self.close_receipt()
        desktop.os.kill.assert_not_called()

    def test_malformed_or_nonstarted_receipts_never_signal(self):
        for receipt in (None, {}, [], ["invalid"], "invalid", {"status": "existing", "pid": self.pid},
                        {**self.receipt(), "owner": None}, {**self.receipt(), "pid": self.pid + 1}):
            with self.subTest(receipt=receipt):
                self.write(self.receipt_path, {**self.record, "receipt": receipt})
                with self.assertRaises(ValueError):
                    self.close_receipt()
                desktop.os.kill.assert_not_called()

    def test_incomplete_launch_record_never_signals(self):
        for record in ({"thread_id": self.own, "status": "launching"},
                       {**self.record, "pid": True}, {**self.record, "pid": 1}):
            with self.subTest(record=record):
                self.write(self.receipt_path, record)
                with self.assertRaises(ValueError):
                    self.close_receipt()
                desktop.os.kill.assert_not_called()

    def test_nonobject_launch_record_is_rejected_without_signal(self):
        for record in (None, [], "invalid"):
            with self.subTest(record=record):
                self.write(self.receipt_path, record)
                with self.assertRaises(ValueError):
                    self.close_receipt()
                desktop.os.kill.assert_not_called()

    def test_mismatched_session_launch_is_rejected_before_input_release(self):
        path = self.session()
        session = json.loads(path.read_text())
        session["launch"]["thread_id"] = "another-task"
        self.write(path, session)
        with patch.object(desktop, "native", return_value={"event": "input_released"}) as native:
            with self.assertRaisesRegex(ValueError, "ownership mismatch"):
                self.cli("close", "--session", path)
        native.assert_not_called()
        desktop.os.kill.assert_not_called()

    def test_receipt_close_is_blocked_by_process_recording_registry(self):
        self.write(self.registry(), {"recording": {"pid": 4343}})
        with self.assertRaisesRegex(ValueError, "Stop recorder"):
            self.close_receipt()
        desktop.os.kill.assert_not_called()
        desktop.native.assert_not_called()

    def test_unscoped_windows_do_not_request_hidden_desktop_enumeration(self):
        with patch.object(desktop, "native", return_value={"windows": []}) as native:
            self.cli("windows", "--lease-id", "lease", "--work", self.work)
        self.assertEqual(native.call_args.args[0], {"command": "windows"})

    def test_receipt_scopes_all_window_enumeration_to_verified_process(self):
        with patch.object(desktop, "native", return_value={"windows": []}) as native:
            result = self.cli("windows", "--lease-id", "lease", "--work", self.work,
                              "--launch-record", self.receipt_path)
        self.assertEqual(native.call_args.args[0], dict(command="windows", pid=self.pid,
                                                       executable=self.exe, include_hidden=True))
        self.assertEqual(result["identity"], self.birth)

    def test_conflicting_pid_does_not_enumerate_any_windows(self):
        with self.assertRaises(ValueError):
            self.cli("windows", "--lease-id", "lease", "--work", self.work,
                     "--launch-record", self.receipt_path, "--pid", self.pid + 1)
        desktop.native.assert_not_called()

    def test_pid_identity_change_during_discovery_rejects_result(self):
        with patch.object(desktop, "native", return_value={"windows": []}), patch.object(desktop, "identity", side_effect=[self.birth, "reused PID"]):
            with self.assertRaisesRegex(ValueError, "identity changed during window discovery"):
                self.cli("windows", "--lease-id", "lease", "--work", self.work,
                         "--pid", self.pid, "--executable", self.exe)

    def test_hidden_window_can_bind_without_implicit_restore(self):
        path = self.root / "bound.json"
        window = dict(pid=self.pid, window=10, executable=self.exe, onscreen=False)
        with patch.object(desktop, "native", return_value={"windows": [window]}) as native:
            result = self.cli("bind", "--lease-id", "lease", "--work", self.work,
                              "--launch-record", self.receipt_path, "--window", 10, "--session", path)
        self.assertFalse(result["target"]["onscreen"])
        self.assertEqual(native.call_count, 1)
        self.assertEqual(json.loads(path.read_text())["window"], 10)

    def test_bind_rejects_another_process_window(self):
        with patch.object(desktop, "native", return_value={"windows": [dict(pid=self.pid + 1, window=10, executable=self.exe)]}):
            with self.assertRaisesRegex(ValueError, "Exact PID/window/executable"):
                self.cli("bind", "--lease-id", "lease", "--work", self.work,
                         "--launch-record", self.receipt_path, "--window", 10,
                         "--session", self.root / "bound.json")
        self.assertFalse((self.root / "bound.json").exists())

    def test_restore_success_captures_bound_window_and_keeps_ui_unverified(self):
        session = self.session()
        restored = dict(event="restored", pid=self.pid, window=10, onscreen=True, focused=True, ui_verified=False)
        with patch.object(desktop, "native", side_effect=[restored, {"event": "snapshot"}]) as native:
            result = self.cli("restore", "--session", session)
        self.assertEqual([call.args[0]["command"] for call in native.call_args_list], ["restore", "snapshot"])
        self.assertEqual(native.call_args_list[1].args[0]["window"], 10)
        self.assertFalse(result["ui_verified"])
        self.assertEqual(len(list(self.work.glob("*-restored.json"))), 1)

    def test_restore_failure_does_not_claim_success_or_take_after_snapshot(self):
        session = self.session()
        with patch.object(desktop, "native", side_effect=ValueError("Bound window could not be restored")) as native:
            with self.assertRaisesRegex(ValueError, "could not be restored"):
                self.cli("restore", "--session", session)
        self.assertEqual(native.call_count, 1)
        self.assertEqual(list(self.work.glob("*-restored.json")), [])

    def test_failed_recorder_blocks_restore_before_desktop_access(self):
        session = self.session()
        log = self.root / "record.jsonl"
        log.write_text('{"event":"capture_failed","error":"lost stream"}\n')
        self.write(self.registry(), {"recording": dict(pid=4343, identity="recorder", log=str(log))})
        with self.assertRaisesRegex(ValueError, "Recording ended or failed"):
            self.cli("restore", "--session", session)
        desktop.native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
