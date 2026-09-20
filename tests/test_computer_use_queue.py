import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "computer_use_queue.py"
spec = importlib.util.spec_from_file_location("computer_use_queue", SCRIPT)
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def run_command(self, command, who=None, **kwargs):
        return queue.execute(self.directory, command, who, **kwargs)

    def cli(self, command, who, *args):
        environment = {**os.environ, "CODEX_THREAD_ID": who}
        return subprocess.run([sys.executable, str(SCRIPT), command, "--state-dir", str(self.directory), *args],
                              env=environment, capture_output=True, text=True, timeout=15)

    def history(self):
        return queue.read_json(self.directory / "history.json")["sessions"]

    def test_fifo_idempotency_handoff_and_no_cutting(self):
        first = self.run_command("request", "A")["queue"]["current"]
        self.assertEqual(self.run_command("request", "A")["queue"]["current"], first)
        self.assertEqual(self.run_command("request", "B")["position"], 1)
        self.assertEqual(self.run_command("request", "B")["position"], 1)
        self.assertEqual(self.run_command("request", "C")["position"], 2)
        released = self.run_command("release", "A", lease_id=first["lease_id"])
        self.assertIsNone(released["queue"]["current"])
        self.assertEqual(released["notify"]["arguments"]["threadId"], "B")
        self.assertEqual(self.run_command("request", "D")["result"], "waiting")
        self.assertEqual(self.run_command("request", "C")["position"], 2)
        self.assertEqual(self.run_command("request", "B")["result"], "acquired")
        self.assertEqual(self.run_command("release", "A", lease_id=first["lease_id"])["result"], "already_released")
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(self.run_command("status")["queue"]["current"]["thread_id"], "B")

    def test_foreign_release_wrong_lease_and_owner_cancel_rejected(self):
        lease = self.run_command("request", "A")["queue"]["current"]["lease_id"]
        for command, who, arguments in [("release", "B", {"lease_id": lease}),
                                         ("release", "A", {"lease_id": "wrong"}),
                                         ("check", "B", {"lease_id": lease}),
                                         ("cancel", "A", {})]:
            with self.assertRaises(ValueError):
                self.run_command(command, who, **arguments)
        self.assertEqual(self.run_command("check", "A", lease_id=lease)["result"], "owner")
        self.assertEqual(self.history(), [])
        conflict = self.cli("cancel", "B", "--thread-id", "A")
        self.assertNotEqual(conflict.returncode, 0)

    def test_pending_notification_survives_failure_and_stale_ack(self):
        lease = self.run_command("request", "A")["queue"]["current"]["lease_id"]
        self.run_command("request", "B")
        self.run_command("request", "C")
        notice = self.run_command("release", "A", lease_id=lease)["notify"]
        # No delivery acknowledgement: subsequent checks retain the same message.
        self.assertEqual(self.run_command("notifications")["notify"], notice)
        next_notice = self.run_command("cancel", "B")["notify"]
        self.assertEqual(next_notice["arguments"]["threadId"], "C")
        self.assertNotEqual(notice["id"], next_notice["id"])
        stale = self.run_command("notified", "A", notification_id=notice["id"])
        self.assertEqual(stale["result"], "obsolete_notification")
        self.assertEqual(stale["notify"], next_notice)
        sent = self.run_command("notified", "B", notification_id=next_notice["id"])
        self.assertIsNone(sent["notify"])
        self.assertEqual(sent["queue"]["notification"]["status"], "sent")
        self.assertEqual(self.run_command("request", "C")["result"], "acquired")

    def test_old_release_cannot_release_same_threads_new_lease(self):
        old = self.run_command("request", "A")["queue"]["current"]["lease_id"]
        self.run_command("release", "A", lease_id=old)
        new = self.run_command("request", "A")["queue"]["current"]["lease_id"]
        self.run_command("release", "A", lease_id=old)
        self.assertEqual(self.run_command("check", "A", lease_id=new)["result"], "owner")

    def test_cancel_preserves_others_order(self):
        self.run_command("request", "A")
        for who in ("B", "C", "D"):
            self.run_command("request", who)
        result = self.run_command("cancel", "C")
        self.assertEqual([entry["thread_id"] for entry in result["queue"]["waiting"]], ["B", "D"])
        self.assertIsNone(result["notify"])
        self.assertEqual(self.run_command("request", "C")["position"], 3)

    def test_concurrent_processes_get_one_owner_and_unique_fifo_tickets(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda index: self.cli("request", "thread-" + str(index)), range(24)))
        self.assertTrue(all(result.returncode == 0 for result in results), [result.stderr for result in results])
        state = self.run_command("status")["queue"]
        self.assertEqual(len(state["waiting"]), 23)
        self.assertEqual(state["current"]["ticket"], 1)
        self.assertEqual([entry["ticket"] for entry in state["waiting"]], list(range(2, 25)))
        self.assertEqual(sum(json.loads(result.stdout)["result"] == "acquired" for result in results), 1)

    def test_process_death_recovers_transaction_and_releases_write_lock(self):
        lease = self.run_command("request", "A")["queue"]["current"]["lease_id"]
        self.run_command("request", "B")
        child = """
import importlib.util, os, pathlib, sys
spec = importlib.util.spec_from_file_location('q', sys.argv[1])
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
original = q.atomic_json
def interrupted(path, value):
    original(path, value)
    if path.name == 'history.json':
        os._exit(77)
q.atomic_json = interrupted
q.execute(pathlib.Path(sys.argv[2]), 'release', 'A', lease_id=sys.argv[3])
"""
        process = subprocess.run([sys.executable, "-c", child, str(SCRIPT), str(self.directory), lease], timeout=10)
        self.assertEqual(process.returncode, 77)
        self.assertTrue((self.directory / ".transaction.json").exists())
        result = self.run_command("status")
        self.assertIsNone(result["queue"]["current"])
        self.assertEqual(result["notify"]["arguments"]["threadId"], "B")
        self.assertEqual(len(self.history()), 1)
        self.assertFalse((self.directory / ".transaction.json").exists())
        self.run_command("release", "A", lease_id=lease)
        self.assertEqual(len(self.history()), 1)

    def test_corrupt_or_missing_state_is_not_reset(self):
        self.run_command("request", "A")
        path = self.directory / "queue.json"
        path.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_command("request", "B")
        self.assertEqual(path.read_text(), "broken")
        path.unlink()
        with self.assertRaises(ValueError):
            self.run_command("request", "B")
        self.assertFalse(path.exists())

    def test_no_timeout_eviction(self):
        lease = self.run_command("request", "A")["queue"]["current"]["lease_id"]
        with queue.locked(self.directory):
            state, history = queue.load(self.directory)
            state["current"]["acquired_at"] = "2000-01-01T00:00:00+00:00"
            queue.save(self.directory, state, history)
        self.assertEqual(self.run_command("request", "B")["result"], "waiting")
        self.assertEqual(self.run_command("check", "A", lease_id=lease)["result"], "owner")


if __name__ == "__main__":
    unittest.main()
