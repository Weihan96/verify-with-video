#!/usr/bin/env python3
"""Cooperative FIFO for one desktop. Never controls or preempts shared desktop."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + str(uuid.uuid4()) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Keep this inode: unlinking a flock file can create two independent locks.
    with (directory / ".write.lock").open("a+") as stream:
        deadline = time.monotonic() + 5
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, "Queue writer busy; retry later. Do not delete the lock file.")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def validate(queue, history):
    require(queue["version"] == history["version"] == 1, "Unsupported state version; do not reset it.")
    require(queue["revision"] == history["revision"], "State revisions disagree; stop for inspection.")
    require(isinstance(queue["waiting"], list) and isinstance(history["sessions"], list), "Invalid state arrays.")
    entries = ([queue["current"]] if queue["current"] else []) + queue["waiting"]
    ids = [entry["thread_id"] for entry in entries]
    tickets = [entry["ticket"] for entry in entries]
    require(all(isinstance(value, str) and value for value in ids), "Missing thread identity.")
    require(len(ids) == len(set(ids)), "Duplicate thread in queue; do not reorder or reset it.")
    require(all(type(ticket) is int and ticket > 0 for ticket in tickets), "Invalid tickets.")
    require(tickets == sorted(set(tickets)), "Invalid FIFO order; do not reorder it.")
    historical_tickets = [entry["ticket"] for entry in history["sessions"]]
    require(queue["next_ticket"] > max(tickets + historical_tickets, default=0), "Ticket counter regressed.")
    leases = [entry["lease_id"] for entry in history["sessions"]]
    require(len(leases) == len(set(leases)), "Duplicate history entry.")
    if queue["current"]:
        require(queue["current"]["lease_id"] not in leases, "Current lease is already released.")
        require(bool(queue["current"]["acquired_at"]), "Missing acquisition time.")
    notice = queue["notification"]
    if notice:
        require(not queue["current"] and bool(queue["waiting"]), "Notification has no eligible recipient.")
        require(notice["thread_id"] == queue["waiting"][0]["thread_id"] and
                notice["ticket"] == queue["waiting"][0]["ticket"], "Notification is not for the head.")
        require(notice["status"] in ("pending", "sent"), "Invalid notification status.")


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def install(directory, transaction):
    validate(transaction["queue"], transaction["history"])
    atomic_json(directory / "history.json", transaction["history"])
    atomic_json(directory / "queue.json", transaction["queue"])
    (directory / ".transaction.json").unlink(missing_ok=True)
    sync_directory(directory)


def save(directory, queue, history):
    queue["revision"] += 1
    history["revision"] = queue["revision"]
    validate(queue, history)
    transaction = {"queue": queue, "history": history}
    # Replay an interrupted commit before accepting another command.
    atomic_json(directory / ".transaction.json", transaction)
    install(directory, transaction)


def load(directory):
    journal = directory / ".transaction.json"
    if journal.exists():
        install(directory, read_json(journal))
    queue_path, history_path = directory / "queue.json", directory / "history.json"
    require(queue_path.exists() == history_path.exists(), "One state file is missing; do not create a replacement.")
    if not queue_path.exists():
        queue = {"version": 1, "revision": 0, "next_ticket": 1,
                 "current": None, "waiting": [], "notification": None}
        history = {"version": 1, "revision": 0, "sessions": []}
        save(directory, queue, history)
    queue, history = read_json(queue_path), read_json(history_path)
    validate(queue, history)
    return queue, history


def handoff(queue, sender):
    queue["notification"] = None
    if queue["current"] is None and queue["waiting"]:
        head = queue["waiting"][0]
        queue["notification"] = {
            "id": str(uuid.uuid4()), "thread_id": head["thread_id"],
            "ticket": head["ticket"], "from_thread_id": sender,
            "created_at": now(), "status": "pending", "sent_at": None,
        }


def notification_payload(queue):
    notice = queue["notification"]
    if not notice or notice["status"] != "pending":
        return None
    return {
        **notice,
        "tool": "mcp__codex_app__send_message_to_thread",
        "arguments": {
            "threadId": notice["thread_id"],
            "prompt": (
                "shared desktop 排队通知（通知 ID：" + notice["id"] + "）：前一会话已释放协调占用，"
                "你是队首，号码 " + str(notice["ticket"]) + "。请按 $verify-with-video 的队列流程，"
                "使用自己的真实会话 ID 运行 request，重新核对 current 和 lease_id 后继续原验收任务。"
                "此消息只提示轮到你，不代表已获得工具占用；不要抢占、重置或结束其他会话。"
                "如已取消或完成，请忽略过期通知；仍在排队但无需使用时，仅取消自己的号码并通知下一位。"
            ),
        },
    }


def execute(directory, command, thread_id=None, lease_id=None, notification_id=None, outcome="completed"):
    require(command in ("status", "notifications", "request", "check", "release", "cancel", "notified"), "Unknown command.")
    if command not in ("status", "notifications"):
        require(bool(thread_id), "Use CODEX_THREAD_ID or a verified --thread-id; never guess an ID.")
    with locked(directory):
        queue, history = load(directory)
        before = json.dumps([queue, history], sort_keys=True)
        current = queue["current"]
        result = command
        if command == "request":
            if not current or current["thread_id"] != thread_id:
                if not any(entry["thread_id"] == thread_id for entry in queue["waiting"]):
                    queue["waiting"].append({"thread_id": thread_id, "ticket": queue["next_ticket"], "requested_at": now()})
                    queue["next_ticket"] += 1
                if current is None and queue["waiting"][0]["thread_id"] == thread_id:
                    queue["current"] = {**queue["waiting"].pop(0), "lease_id": str(uuid.uuid4()), "acquired_at": now()}
                    queue["notification"] = None
            result = "acquired" if queue["current"] and queue["current"]["thread_id"] == thread_id else "waiting"
        elif command == "check":
            require(current and current["thread_id"] == thread_id and current["lease_id"] == lease_id,
                    "This thread does not hold that lease; do not use shared desktop.")
            result = "owner"
        elif command == "release":
            require(bool(lease_id), "release requires the lease_id returned by request.")
            if any(entry["thread_id"] == thread_id and entry["lease_id"] == lease_id for entry in history["sessions"]):
                result = "already_released"
            else:
                require(current and current["thread_id"] == thread_id and current["lease_id"] == lease_id,
                        "Only the current thread may release its own matching lease.")
                require(outcome in ("completed", "aborted", "backend_busy"), "Invalid outcome.")
                history["sessions"].append({**current, "released_at": now(), "outcome": outcome})
                queue["current"] = None
                handoff(queue, thread_id)
                result = "released"
        elif command == "cancel":
            require(not current or current["thread_id"] != thread_id, "Owner must stop using shared desktop and release its lease.")
            old_head = queue["waiting"][0] if queue["waiting"] else None
            queue["waiting"] = [entry for entry in queue["waiting"] if entry["thread_id"] != thread_id]
            if old_head and old_head["thread_id"] == thread_id:
                handoff(queue, thread_id)
            result = "cancelled"
        elif command == "notified":
            require(bool(notification_id), "notified requires the delivered notification ID.")
            notice = queue["notification"]
            if notice and notice["id"] == notification_id:
                notice["status"], notice["sent_at"] = "sent", now()
                result = "notification_recorded"
            else:
                result = "obsolete_notification"
        if json.dumps([queue, history], sort_keys=True) != before:
            save(directory, queue, history)
        position = next((index + 1 for index, entry in enumerate(queue["waiting"]) if entry["thread_id"] == thread_id), None)
        return {"result": result, "state_dir": str(directory), "queue": queue,
                "position": position, "notify": notification_payload(queue)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "request", "check", "release", "cancel", "notifications", "notified"])
    parser.add_argument("--thread-id", help="Own verified thread ID; defaults to CODEX_THREAD_ID")
    parser.add_argument("--lease-id")
    parser.add_argument("--notification-id")
    parser.add_argument("--outcome", choices=["completed", "aborted", "backend_busy"], default="completed")
    parser.add_argument("--state-dir", type=Path, help="Isolated tests only; all real sessions must use the shared default")
    args = parser.parse_args()
    try:
        own_id = os.environ.get("CODEX_THREAD_ID")
        require(not (own_id and args.thread_id and own_id != args.thread_id), "--thread-id differs from CODEX_THREAD_ID; cannot act for another thread.")
        directory = args.state_dir or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "state" / "computer-use"
        result = execute(directory.resolve(), args.command, args.thread_id or own_id,
                         args.lease_id, args.notification_id, args.outcome)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error), "action": "Stop; preserve state. Never reset, reorder or preempt another session."}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
