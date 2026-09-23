# Blender isolated input feasibility experiment

This directory preserves research on `experiment/blender-independent-input`.
It is **not installed or published on main**, and is not a replacement for the
skill's shared desktop queue. Never install this branch as a completed concurrent
acceptance feature. The stable main tree was restored with `208a535`, exactly
matching the skill content at `20f7e2b`.

## Result, 2026-09-22

Blender 4.5.3 LTS on macOS can support the tested dedicated worker mode: two
Blender processes in separate native full-screen Spaces receive independent
`Window.event_simulate` events, while a third foreground AppKit application
receives native system mouse and keyboard events. A shared capture process can
start and stop each target stream independently without ending its other streams.

This establishes a feasible backend, **not universal desktop isolation or a
completed cross-task service**. All experiment clients belonged to one real
Codex task and held its existing shared desktop lease. The foreground input was
a controlled surrogate, not a claim that a human physically operated the mouse.

| Check | Observed result |
| --- | --- |
| Default Save As creates a separate file window | Failed twice: foreground switched from the probe to A, then to B in an independent repetition. The native input guard refused the next probe action. |
| Save As in the original full-screen window | Passed in both A and B; actual file browser recorded; foreground received `a` and `b`. |
| Stop A, restart A, stop B, restart B | Four overlapping cases passed; the other worker completed text input and its stream continued. |
| Native mouse moves and keys during lifecycle changes | Probe received `1`, `2`, `3`, `4`, with no observed foreground, modifier or system clipboard change. |
| A numeric drag while B types and the system mouse moves | Actual value changed; the foreground received `x`; releasing the simulated drag did not restore or move the system mouse. |
| Input after that target's recorder stops | Rejected before sending; B continued to operate; A then restarted. |
| Separate copy/paste buffers | A recovered `A-local-clip`, B recovered `B-local-clip`; system pasteboard revision remained unchanged. |
| Real Blender Transform property and persistence | X was entered as 1000 mm through the UI and saved; independent readback of the saved blend returned location `[1.0, 0.0, 0.0]` meters. |
| Perspective viewport orbit | B received middle-mouse orbit events; recorded viewport remained Perspective. |
| Cleanup | All streams finalized; three task-owned temporary applications exited; lease released and next waiting task notified. |

The shared broker lived about 299 seconds, including idle periods and independent
stream lifecycles. ScreenCaptureKit produces sparse frames for unchanged windows;
raw MP4 duration is not equivalent to the broker's wall duration. Preserve raw
timestamps and normalize to CFR **before seeking/editing**. Do not interpret a
held/static frame as either new activity or a failure without checking the log.

## Runtime profile tested

The two workers were launched with the actual user startup scene/preferences and
`--no-window-focus --window-fullscreen --enable-event-simulate --python worker.py`.
The fixture is temporary; launch paths, labels and actual ownership receipts are
provided by the experiment runner, never fabricated. Use `desktop.py launch` and
its real PID/window binding. Do not reuse another task's process.

Before the successful same-window tests, the following **temporary runtime**
settings were entered through each worker's Python Console as preparation and
read back from that same process:

```python
bpy.app.use_userpref_skip_save_on_exit = True
bpy.context.preferences.view.filebrowser_display_type = 'SCREEN'
bpy.context.preferences.view.render_display_type = 'AREA'
bpy.context.preferences.inputs.use_mouse_continuous = False
```

No global preferences were saved. Rendering was configured but actual rendering
was **not tested**. Numeric drag sensitivity differs when continuous mouse mode
is disabled; it is a deliberate worker behavior change, not transparent emulation
of every user preference.

The launch/setup stage still affects global macOS state. Separate Spaces alone
do not provide separate OS mice. Unrestricted native child windows, eyedroppers,
arbitrary add-ons, opening URLs, system dialogs, crashes, permission revocation
and all possible Blender operators are not covered. The shared capture broker
itself remains a single point of failure. Cross-task authorization, queue policy,
worker admission, readiness, teardown and service recovery require a separate
implementation and acceptance pass before shipping.

## Files and execution boundaries

- `worker.py`: disposable UI fixture and finite event receiver; direct assignments
  prepare the fixture only. It is not an authenticated or production RPC server.
- `foreground_probe.swift`: native event receipts and change-only observation of
  system cursor, foreground PID, modifier flags and clipboard revision; never
  reads clipboard contents.
- `broker.py` / `broker.swift`: finite prebound capture harness, retaining actual
  task lease, launch ownership, kernel birth identity and exact window guards.
- `control.py`: one-shot start/stop client for a prebound target. One writer per
  target is assumed; no claim of concurrent request arbitration.
- `send.py`: finite sender with target recorder readiness gating.
- `scenarios.py`, `co_use.py`, `lifecycle.py`, `final_checks.py`: measured UI probes.
  Remeasure coordinates after layout/DPI changes. Current scenario scripts use
  the observed 1280-by-803 Retina fixture; they are not general UI locators.

Launch/bind the owned workers and probe under the real lease first. For the
recording experiment, run `broker.py <new-run-dir> --session <A-session> --session
<B-session> --session <foreground-session> --seconds 480`. Wait for all first
frames. Then use the scenario scripts with their required actual run/lease
arguments. The ordinary `desktop.py stop` is reserved for final collection of
**all** broker streams; the experimental `control.py` changes individual streams.
After input finishes, collect every registered session before closing any app.
Never bypass identity or lease checks to force a test through.

The final review footage replays complete windows sequentially, labels clips
from the same wall interval, speeds ordinary actions to 2x, and keeps key results
at 1x. The default-mode focus failure is supported by observer logs and a child
window snapshot; it was not captured as a complete child-window video and is not
presented as one. Experimental evidence stays local, outside this public repo.

## Why default behavior fails

Blender's simulated event path substitutes some cursor/clipboard state. It does
not isolate the entire macOS application. Its Cocoa new-window/focus code still
uses `makeKeyAndOrderFront` and `activateIgnoringOtherApps`; cursor grab/warp paths
also have OS-level effects and are not uniformly guarded by simulated-event mode.
This explains the reproduced file-window focus theft and why universal claims
would be unjustified. A dedicated profile can avoid tested paths; broader
isolation may require Blender/GHOST changes or separate OS sessions.

[Blender 4.5.3 Cocoa window implementation](https://github.com/blender/blender/blob/v4.5.3/intern/ghost/intern/GHOST_WindowCocoa.mm)

[Blender 4.5.3 window manager](https://github.com/blender/blender/blob/v4.5.3/source/blender/windowmanager/intern/wm_window.cc)

[Blender 4.5.3 cursor implementation](https://github.com/blender/blender/blob/v4.5.3/source/blender/windowmanager/intern/wm_cursors.cc)
