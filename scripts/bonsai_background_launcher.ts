/** Adapt the installed Bonsai launch plan; its owner lock and loader remain authoritative. */
import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

export async function backgroundPlan(values: Record<string, string | boolean | undefined>) {
  if (!process.env.CODEX_THREAD_ID) throw new Error("Actual CODEX_THREAD_ID required");
  const launcher = await import(pathToFileURL(realpathSync(String(values.launcher))).href);
  const plan = launcher.makePlan(values);
  if (plan.kind !== "ifc") throw new Error("Background Bonsai adapter requires --ifc");
  const worker = realpathSync(String(values.worker));
  const run = realpathSync(String(values.run));
  const separator = plan.args.indexOf("--");
  if (separator < 0) throw new Error("Unsupported Bonsai launch plan");
  const requestMarker = "--codex-task-request=" + createHash("sha256")
    .update(JSON.stringify([plan.requestMarker, "verify-background-v1", worker, run])).digest("hex").slice(0, 20);
  const args = ["--no-window-focus", "--window-fullscreen", "--enable-event-simulate",
    ...plan.args.slice(0, separator), "--python", worker, "--",
    ...plan.args.slice(separator + 1).map((arg: string) => arg === plan.requestMarker ? requestMarker : arg),
    "--probe-dir", run, "--probe-label", String(values.label), "--preserve-scene"];
  return { launcher, plan: { ...plan, args, requestMarker } };
}

export async function launchBackground(values: Record<string, string | boolean | undefined>) {
  let prepared;
  try { prepared = await backgroundPlan(values); }
  catch (error) { return { status: "not_started", error: String(error) }; }
  // Once launch is invoked, a thrown error can mean a partially started process.
  // Preserve the pending receipt in that case; never infer absence from an error.
  return prepared.launcher.launch(prepared.plan);
}

if (import.meta.main) {
  try {
    const { values } = parseArgs({ args: Bun.argv.slice(2), strict: true, allowPositionals: false, options: {
      worktree: { type: "string" }, blender: { type: "string" }, ifc: { type: "string" },
      "prepare-script": { type: "string" }, "task-title": { type: "string" },
      launcher: { type: "string" }, worker: { type: "string" }, run: { type: "string" }, label: { type: "string" },
    } });
    // Never replace an existing instance or borrow another task identity.
    console.log(JSON.stringify(await launchBackground(values)));
  } catch (error) { console.error(String(error)); process.exitCode = 1; }
}
