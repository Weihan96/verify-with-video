import Foundation
import Darwin

struct CaptureFault: Error, CustomStringConvertible {
 let kind:String,detail:String
 var description:String {"\(kind): \(detail)"}
}
struct KernelIdentity:Equatable {
 let pid:pid_t,seconds:UInt64,microseconds:UInt64,executable:String
 func validate(_ current:KernelIdentity)throws {
  guard pid==current.pid && seconds==current.seconds && microseconds==current.microseconds else{throw CaptureFault(kind:"process_identity_changed",detail:"Expected PID \(pid) birth \(seconds).\(microseconds); observed PID \(current.pid) birth \(current.seconds).\(current.microseconds)")}
  guard executable==current.executable else{throw CaptureFault(kind:"process_executable_changed",detail:"Expected \(executable); observed \(current.executable)")}
 }
 static func read(_ pid:pid_t)throws->KernelIdentity {
  func info()throws->proc_bsdinfo {
   var value=proc_bsdinfo();errno=0
   let count=proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&value,Int32(MemoryLayout<proc_bsdinfo>.size)),code=errno
   guard count==MemoryLayout<proc_bsdinfo>.size else{throw CaptureFault(kind:code==ESRCH ? "process_exited":"process_identity_unavailable",detail:"proc_pidinfo PID=\(pid) bytes=\(count) expected=\(MemoryLayout<proc_bsdinfo>.size) errno=\(code)")}
   guard value.pbi_status != SZOMB else{throw CaptureFault(kind:"process_exited",detail:"PID \(pid) is a zombie")}
   return value
  }
  let first=try info()
  var path=[CChar](repeating:0,count:4*Int(MAXPATHLEN));errno=0
  let count=proc_pidpath(pid,&path,UInt32(path.count)),code=errno
  guard count>0 else{throw CaptureFault(kind:code==ESRCH ? "process_exited":"process_executable_unavailable",detail:"proc_pidpath PID=\(pid) bytes=\(count) errno=\(code)")}
  let last=try info()
  guard first.pbi_start_tvsec==last.pbi_start_tvsec && first.pbi_start_tvusec==last.pbi_start_tvusec else{throw CaptureFault(kind:"process_identity_changed",detail:"PID changed during identity query")}
  return KernelIdentity(pid:pid,seconds:first.pbi_start_tvsec,microseconds:first.pbi_start_tvusec,executable:URL(fileURLWithPath:String(cString:path)).resolvingSymlinksInPath().path)
 }
}
enum WindowObservation {
 case present
 case unavailable(String)
 case absent
 case wrongOwner(pid_t)
}
struct WindowPresenceGuard {
 let expectedPID:pid_t
 let graceSeconds:Double
 private(set) var firstMissing:Double?=nil
 private(set) var missingCount=0
 private(set) var recoveries=0
 private(set) var totalMissing=0
 private var firstReason=""
 init(expectedPID:pid_t,graceSeconds:Double){self.expectedPID=expectedPID;self.graceSeconds=graceSeconds}
 mutating func observe(_ value:WindowObservation,now:Double)throws->[String:Any]? {
  switch value {
  case .wrongOwner(let actual):throw CaptureFault(kind:"window_owner_changed",detail:"Expected PID \(expectedPID); window now belongs to \(actual)")
  case .present:
   guard let first=firstMissing else{return nil}
   guard now-first<graceSeconds else{throw CaptureFault(kind:"window_observation_timeout",detail:"Recovered only after grace: \(now-first)s; \(firstReason)")}
   let event:[String:Any]=["event":"target_observation_recovered","gap_seconds":now-first,"missed_checks":missingCount,"first_reason":firstReason]
   firstMissing=nil;missingCount=0;recoveries+=1;return event
  case .absent,.unavailable:
   let reason:String
   if case .unavailable(let detail)=value {reason="window_query_unavailable: "+detail}else{reason="window_absent_from_successful_query"}
   totalMissing+=1;missingCount+=1
   if firstMissing==nil {firstMissing=now;firstReason=reason;return ["event":"target_observation_uncertain","reason":reason,"grace_seconds":graceSeconds]}
   guard now-firstMissing!<graceSeconds else{throw CaptureFault(kind:"window_observation_timeout",detail:"\(firstReason); latest=\(reason); duration=\(now-firstMissing!)s checks=\(missingCount)")}
   return nil
  }
 }
 func finish()throws {
  if firstMissing != nil {throw CaptureFault(kind:"window_observation_unresolved",detail:"Capture stopped during uncertain target observation: \(firstReason)")}
 }
}
