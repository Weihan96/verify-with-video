"""Compile and exercise the actual Swift capture guard without any desktop API.

Only the last test starts a harmless, task-owned /bin/sleep process; it verifies
kernel identity rejection after that process has been terminated and reaped.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HARNESS = r'''
import Foundation
import Darwin

struct HarnessFailure: Error, CustomStringConvertible {
 let description:String
}
func insist(_ condition:Bool,_ message:String)throws {
 if !condition {throw HarnessFailure(description:message)}
}
func fault(_ kind:String,_ operation:() throws -> Void)throws->CaptureFault {
 do {try operation()} catch let error as CaptureFault {
  try insist(error.kind==kind,"Expected \(kind), got \(error.kind)")
  return error
 }
 throw HarnessFailure(description:"Expected fault \(kind)")
}
func run(_ scenario:String,_ args:[String])throws->[String:Any] {
 switch scenario {
 case "self":
  let identity=try KernelIdentity.read(getpid())
  try identity.validate(KernelIdentity.read(getpid()))
  try insist(identity.pid==getpid() && identity.seconds>0 && identity.microseconds<1_000_000,"Invalid kernel birth")
  try insist(identity.executable==URL(fileURLWithPath:CommandLine.arguments[0]).resolvingSymlinksInPath().path,"Executable differs from running harness")
  return ["pid":identity.pid,"seconds":identity.seconds,"microseconds":identity.microseconds,"executable":identity.executable]
 case "identity-mismatch":
  let original=KernelIdentity(pid:4242,seconds:100,microseconds:123,executable:"/expected/app")
  let changes=[KernelIdentity(pid:4243,seconds:100,microseconds:123,executable:original.executable),
               KernelIdentity(pid:4242,seconds:101,microseconds:123,executable:original.executable),
               KernelIdentity(pid:4242,seconds:100,microseconds:124,executable:original.executable)]
  for changed in changes {_=try fault("process_identity_changed"){try original.validate(changed)}}
  _=try fault("process_executable_changed"){try original.validate(KernelIdentity(pid:4242,seconds:100,microseconds:123,executable:"/another/app"))}
  return ["rejected_changes":4]
 case "absent-recovery","null-recovery":
  var guardState=WindowPresenceGuard(expectedPID:4242,graceSeconds:2)
  let first:WindowObservation=scenario=="absent-recovery" ? .absent:.unavailable("CG query returned nil")
  let uncertain=try guardState.observe(first,now:100)
  try insist(uncertain?["event"] as? String=="target_observation_uncertain","Missing uncertainty event")
  try insist(try guardState.observe(.absent,now:101)==nil,"Repeated missing observation should not flood events")
  let recovered=try guardState.observe(.present,now:101.999)
  try insist(recovered?["event"] as? String=="target_observation_recovered","Missing recovery event")
  try insist(recovered?["missed_checks"] as? Int==2,"Lost missed checks")
  try insist(guardState.firstMissing==nil && guardState.missingCount==0 && guardState.recoveries==1 && guardState.totalMissing==2,"Incorrect recovery state")
  try guardState.finish()
  return ["uncertain":uncertain!,"recovered":recovered!]
 case "timeout","late-present":
  var guardState=WindowPresenceGuard(expectedPID:4242,graceSeconds:2)
  _=try guardState.observe(.unavailable("original query failure"),now:100)
  let next:WindowObservation=scenario=="timeout" ? .absent:.present
  let failure=try fault("window_observation_timeout"){_=try guardState.observe(next,now:102)}
  try insist(failure.detail.contains("original query failure"),"Initial query reason was lost")
  return ["kind":failure.kind,"detail":failure.detail]
 case "wrong-owner":
  var guardState=WindowPresenceGuard(expectedPID:4242,graceSeconds:2)
  _=try guardState.observe(.absent,now:100)
  let failure=try fault("window_owner_changed"){_=try guardState.observe(.wrongOwner(9898),now:100.01)}
  try insist(failure.detail.contains("4242") && failure.detail.contains("9898"),"Missing ownership detail")
  return ["kind":failure.kind,"detail":failure.detail]
 case "pending-finish":
  var guardState=WindowPresenceGuard(expectedPID:4242,graceSeconds:2)
  _=try guardState.observe(.unavailable("pending CG query"),now:100)
  let failure=try fault("window_observation_unresolved"){try guardState.finish()}
  try insist(failure.detail.contains("pending CG query"),"Pending reason was lost")
  return ["kind":failure.kind]
 case "normal-finish":
  var guardState=WindowPresenceGuard(expectedPID:4242,graceSeconds:2)
  try guardState.finish()
  try insist(try guardState.observe(.present,now:100)==nil,"Unexpected event for stable target")
  try guardState.finish()
  return ["finished":true,"recoveries":guardState.recoveries]
 case "pid-read":
  let identity=try KernelIdentity.read(Int32(args[0])!)
  return ["pid":identity.pid,"seconds":identity.seconds,"microseconds":identity.microseconds,"executable":identity.executable]
 case "pid-rejected":
  do {_=try KernelIdentity.read(Int32(args[0])!)}catch let failure as CaptureFault {
   try insist(["process_exited","process_identity_unavailable","process_executable_unavailable"].contains(failure.kind),"Unexpected failed read kind")
   return ["rejected":true,"kind":failure.kind,"detail":failure.detail]
  }
  throw HarnessFailure(description:"Terminated process accepted")
 default:throw HarnessFailure(description:"Unknown scenario")
 }
}
@main struct Main {
 static func main() {
  do {
   let result=try run(CommandLine.arguments[1],Array(CommandLine.arguments.dropFirst(2)))
   let data=try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys])
   print(String(data:data,encoding:.utf8)!)
  }catch {
   fputs("\(error)\n",stderr);exit(1)
  }
 }
}
'''


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("swiftc"), "macOS Swift toolchain required")
class CaptureGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name)
        harness = root / "Harness.swift"
        harness.write_text(HARNESS)
        cls.binary = root / "guard-test"
        result = subprocess.run(
            ["swiftc", "-parse-as-library", "-import-objc-header", str(SCRIPTS / "native-process.h"),
             str(SCRIPTS / "capture_guard.swift"), str(harness), "-o", str(cls.binary)],
            text=True, capture_output=True, timeout=60)
        if result.returncode:
            raise AssertionError("Actual capture guard failed to compile:\n" + result.stdout + result.stderr)

    def run_scenario(self, scenario, *args):
        result = subprocess.run([str(self.binary), scenario, *map(str, args)],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_actual_kernel_identity_of_running_harness(self):
        # Foundation and pathlib can spell macOS /var vs /private/var aliases
        # differently; assert the actual executable file, not Python's spelling.
        self.assertTrue(Path(self.run_scenario("self")["executable"]).samefile(self.binary))

    def test_pid_birth_seconds_microseconds_and_executable_mismatch_rejected(self):
        self.assertEqual(self.run_scenario("identity-mismatch")["rejected_changes"], 4)

    def test_successful_enumeration_absence_can_recover_inside_grace(self):
        result = self.run_scenario("absent-recovery")
        self.assertEqual(result["recovered"]["first_reason"], "window_absent_from_successful_query")

    def test_nullable_enumeration_can_recover_without_losing_reason(self):
        result = self.run_scenario("null-recovery")
        self.assertIn("CG query returned nil", result["recovered"]["first_reason"])

    def test_missing_at_two_second_boundary_is_failure(self):
        self.assertEqual(self.run_scenario("timeout")["kind"], "window_observation_timeout")

    def test_present_at_two_second_boundary_does_not_erase_timeout(self):
        self.assertEqual(self.run_scenario("late-present")["kind"], "window_observation_timeout")

    def test_wrong_owner_rejected_immediately_during_grace(self):
        self.assertEqual(self.run_scenario("wrong-owner")["kind"], "window_owner_changed")

    def test_stop_during_pending_observation_cannot_claim_success(self):
        self.assertEqual(self.run_scenario("pending-finish")["kind"], "window_observation_unresolved")

    def test_finish_with_confirmed_target_succeeds(self):
        self.assertTrue(self.run_scenario("normal-finish")["finished"])

    def test_real_task_owned_sleep_is_read_live_then_rejected_after_exit(self):
        process = subprocess.Popen(["/bin/sleep", "30"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            live = self.run_scenario("pid-read", process.pid)
            self.assertEqual(live["pid"], process.pid)
            self.assertEqual(live["executable"], str(Path("/bin/sleep").resolve()))
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        dead = self.run_scenario("pid-rejected", process.pid)
        self.assertTrue(dead["rejected"])
        self.assertIn("errno=", dead["detail"])


if __name__ == "__main__":
    unittest.main()
