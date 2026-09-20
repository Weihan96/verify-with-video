"""Failure-path tests: never call the real desktop, recorder, or shared queue.

Swift event delivery/cleanup still needs the recorded native UI probe. These tests
exercise Python orchestration and durable evidence, not whether an app saw input.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    spec = importlib.util.spec_from_file_location("native_contract_desktop", SCRIPTS / "desktop.py")
    desktop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desktop)
finally:
    sys.path.pop(0)


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / "evidence"
        self.work.mkdir()
        self.registry = self.root / "process.json"
        self.write(self.registry, {"recording": None})
        self.session = self.root / "main.json"
        self.data = dict(thread_id="contract-test", lease_id="lease", pid=4242,
                         window=10, executable=str(Path(sys.executable).resolve()),
                         identity="original process", registry=str(self.registry),
                         work=str(self.work), launch={"identity": "original process"},
                         recording=None)
        self.write(self.session, self.data)
        for mocker in (
            patch.dict(os.environ, {"CODEX_THREAD_ID": "contract-test", "CODEX_HOME": str(self.root)}),
            patch.object(desktop, "check", return_value="contract-test"),
            patch.object(desktop, "identity", return_value="original process"),
            patch.object(desktop, "native", side_effect=AssertionError("Real desktop forbidden")),
            patch.object(desktop.os, "kill", side_effect=AssertionError("Real signals forbidden")),
            patch.object(desktop.subprocess, "Popen", side_effect=AssertionError("Real launch forbidden")),
            patch.object(desktop.time, "sleep"),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def run_cli(self, *arguments):
        with patch.object(sys, "argv", ["desktop.py", *map(str, arguments)]):
            return desktop.main()

    def action(self):
        return self.run_cli("action", "--session", self.session, "--action",
                            json.dumps({"op": "key", "code": 36}))

    def log(self):
        return [json.loads(line) for line in (self.work / "actions.jsonl").read_text().splitlines()]

    def test_failed_before_capture_logs_attempt_without_sending_input(self):
        with patch.object(desktop, "native", side_effect=ValueError("capture unavailable")) as native:
            with self.assertRaisesRegex(ValueError, "capture unavailable"):
                self.action()
        self.assertEqual(native.call_count, 1)
        entry, = self.log()
        self.assertFalse(entry["ui_verified"])
        self.assertNotIn("sent_at", entry)
        self.assertIn("capture unavailable", entry["error"])

    def test_partial_input_failure_keeps_error_and_attempt_timing(self):
        with patch.object(desktop, "native", side_effect=[{"event": "snapshot"}, ValueError("dialog closed after keydown")]):
            with self.assertRaisesRegex(ValueError, "dialog closed"):
                self.action()
        entry, = self.log()
        self.assertEqual(entry["action"]["code"], 36)
        self.assertIn("sent_at", entry)
        self.assertIn("dialog closed", entry["error"])
        self.assertFalse(entry["ui_verified"])

    def test_after_capture_failure_preserves_sent_result(self):
        sent = {"event": "sent", "ui_verified": False}
        with patch.object(desktop, "native", side_effect=[{}, sent, ValueError("target disappeared")]):
            with self.assertRaisesRegex(ValueError, "target disappeared"):
                self.action()
        entry, = self.log()
        self.assertEqual(entry["result"], sent)
        self.assertIn("target disappeared", entry["error"])
        self.assertFalse(entry["ui_verified"])

    def test_success_is_logged_but_does_not_claim_ui_verification(self):
        with patch.object(desktop, "native", side_effect=[{}, {"event": "sent"}, {}]):
            result = self.action()
        entry, = self.log()
        self.assertEqual(result, entry)
        self.assertFalse(entry["ui_verified"])
        self.assertNotIn("error", entry)

    def launch(self, record):
        return self.run_cli("launch", "--lease-id", "lease", "--work", self.work,
                            "--executable", sys.executable, "--launch-record", record)

    def test_launch_prepares_missing_parent_before_starting_process(self):
        record = self.root / "new-directory" / "launch.json"
        process = Mock(pid=4242)
        def started(*args, **kwargs):
            self.assertEqual(json.loads(record.read_text())["status"], "launching")
            return process
        with patch.object(desktop.subprocess, "Popen", side_effect=started):
            result = self.launch(record)
        self.assertEqual(result["pid"], 4242)
        self.assertEqual(json.loads(record.read_text())["identity"], "original process")
        process.terminate.assert_not_called()

    def test_launch_preflight_write_failure_does_not_start_process(self):
        with patch.object(desktop, "dump", side_effect=OSError("disk full")), patch.object(desktop.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(OSError, "disk full"):
                self.launch(self.root / "launch.json")
        spawn.assert_not_called()

    def test_launch_final_record_failure_terminates_own_new_process(self):
        process = Mock(pid=4242)
        original_dump = desktop.dump
        def save(path, data):
            if "pid" in data:
                raise OSError("disk full after spawn")
            original_dump(path, data)
        with patch.object(desktop, "dump", side_effect=save), patch.object(desktop.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(OSError, "disk full after spawn"):
                self.launch(self.root / "launch.json")
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once()

    def test_second_window_session_cannot_close_or_record_over_shared_recorder(self):
        self.write(self.registry, {"recording": {"pid": 4343}})
        dialog = self.root / "dialog.json"
        self.write(dialog, {**self.data, "window": 11, "recording": None})
        with self.assertRaisesRegex(ValueError, "Stop recorder"):
            self.run_cli("close", "--session", dialog)
        with self.assertRaisesRegex(ValueError, "Recorder already registered"):
            self.run_cli("record", "--session", dialog, "--output", self.root / "video.mp4")
        desktop.native.assert_not_called()
        desktop.os.kill.assert_not_called()

    def test_stop_via_other_window_clears_shared_registry_even_after_lease_loss(self):
        log = self.root / "record.jsonl"
        log.write_text('{"event":"capture_finished","frames":30}\n')
        stop = self.root / "record.stop"
        self.write(self.registry, {"recording": dict(pid=4343, identity="recorder", stop=str(stop), log=str(log))})
        dialog = self.root / "dialog.json"
        self.write(dialog, {**self.data, "window": 11, "recording": None})
        with patch.object(desktop, "check", side_effect=AssertionError("Lease no longer owned")):
            result = self.run_cli("stop", "--session", dialog)
        self.assertTrue(result["stopped"])
        self.assertTrue(stop.exists())
        self.assertIsNone(json.loads(self.registry.read_text())["recording"])

    def test_changed_pid_identity_rejects_action_before_native_call(self):
        with patch.object(desktop, "identity", return_value="different process"):
            with self.assertRaisesRegex(ValueError, "PID identity changed"):
                self.action()
        desktop.native.assert_not_called()

    def active_recording(self, contents='{"event":"first_frame"}\n'):
        log = self.root / "capture.jsonl"
        log.write_text(contents)
        self.write(self.registry, {"recording": dict(pid=4343, identity="original process", log=str(log))})
        return log

    def test_dead_recorder_blocks_input_and_keeps_failure_log(self):
        self.active_recording()
        def identify(pid):
            if pid == 4343:
                raise subprocess.CalledProcessError(1, ["ps", "-p", str(pid)])
            return "original process"
        with patch.object(desktop, "identity", side_effect=identify):
            with self.assertRaises(subprocess.CalledProcessError):
                self.action()
        desktop.native.assert_not_called()
        entry, = self.log()
        self.assertIn("error", entry)
        self.assertNotIn("sent_at", entry)
        self.assertIsNotNone(json.loads(self.registry.read_text())["recording"])

    def test_failed_or_finished_recorder_blocks_input_without_clearing_evidence(self):
        for event in ('{"event":"capture_failed","error":"stream lost"}\n',
                      '{"event":"capture_finished","frames":30}\n'):
            with self.subTest(event=event):
                log = self.active_recording(event)
                with self.assertRaisesRegex(ValueError, "Recording ended or failed"):
                    self.action()
                desktop.native.assert_not_called()
                self.assertEqual(log.read_text(), event)
                self.assertIsNotNone(json.loads(self.registry.read_text())["recording"])
        self.assertEqual(len(self.log()), 2)

    def test_reused_recorder_pid_blocks_input(self):
        self.active_recording()
        with patch.object(desktop, "identity", side_effect=lambda pid: "replacement process" if pid == 4343 else "original process"):
            with self.assertRaisesRegex(ValueError, "Recorder exited or identity changed"):
                self.action()
        desktop.native.assert_not_called()

    def test_recorder_failing_during_action_preserves_sent_result_and_reports_failure(self):
        log = self.active_recording()
        def operation(request, directory):
            if request["command"] == "action":
                log.write_text('{"event":"capture_failed","error":"stream lost"}\n')
                return {"event": "sent", "ui_verified": False}
            return {"event": "snapshot"}
        with patch.object(desktop, "native", side_effect=operation):
            with self.assertRaisesRegex(ValueError, "Recording ended or failed"):
                self.action()
        entry, = self.log()
        self.assertEqual(entry["result"]["event"], "sent")
        self.assertIn("stream lost", entry["error"])
        self.assertFalse(entry["ui_verified"])

    def test_healthy_recorder_allows_action_but_does_not_verify_ui(self):
        self.active_recording()
        with patch.object(desktop, "native", side_effect=[{}, {"event": "sent"}, {}]) as native:
            result = self.action()
        self.assertEqual(native.call_count, 3)
        self.assertFalse(result["ui_verified"])


if __name__ == "__main__":
    unittest.main()
