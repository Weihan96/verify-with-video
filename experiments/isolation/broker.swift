// Compiled with the native helper's shared types, without its @main entrypoint.
// One recorder process owns all streams and finalizes all writers before exit.
final class CaptureItem {
 let label:String,target:Target,identity:KernelIdentity,recorder:Recorder,queue:DispatchQueue,stream:SCStream
 var presence:WindowPresenceGuard
 init(_ spec:[String:Any],_ content:SCShareableContent)throws {
  label=spec["label"] as! String
  target=Target(pid:spec["pid"] as! Int32,id:spec["window"] as! UInt32,executable:spec["executable"] as! String)
  let r=rect(try target.window(onscreen:false))
  identity=try KernelIdentity.read(target.pid)
  let windowID=target.id,pid=target.pid
  guard let w=content.windows.first(where:{$0.windowID==windowID && $0.owningApplication?.processID==pid}) else {throw Failure("Capture window missing for "+label)}
  let config=SCStreamConfiguration()
  config.width=Int(r.width)/2*2;config.height=Int(r.height)/2*2
  config.minimumFrameInterval=CMTime(value:1,timescale:30)
  config.showsCursor=false;config.capturesAudio=false
  recorder=try Recorder(spec["output"] as! String,config.width,config.height)
  queue=DispatchQueue(label:"probe.capture."+label)
  stream=SCStream(filter:SCContentFilter(desktopIndependentWindow:w),configuration:config,delegate:recorder)
  presence=WindowPresenceGuard(expectedPID:target.pid,graceSeconds:2)
  try stream.addStreamOutput(recorder,type:.screen,sampleHandlerQueue:queue)
 }
}
// This bounded feasibility harness prebinds all targets before accepting demand.
// It deliberately does not implement cross-task authorization or discovery.
@main struct BrokerMain {
 static func finish(_ item:CaptureItem) async -> String? {
  var problem:String?
  do {try await item.stream.stopCapture()} catch {problem=String(describing:error)}
  if item.queue.sync(execute:{item.recorder.started}) {
   item.queue.sync{item.recorder.input.markAsFinished()}
   await item.recorder.writer.finishWriting()
  }
  if item.recorder.frames==0 || item.recorder.writer.status != .completed {problem=problem ?? "Writer incomplete"}
  emit(["event":"writer_finished","label":item.label,"output":item.recorder.writer.outputURL.path,"frames":item.recorder.frames,"valid":item.recorder.writer.status == .completed,"wall_time":Date().timeIntervalSince1970])
  return problem
 }
 static func main() async {
  signal(SIGINT){_ in interrupted=true};signal(SIGTERM){_ in interrupted=true}
  _=NSApplication.shared
  var active:[String:CaptureItem]=[:],identities:[String:KernelIdentity]=[:],generations:[String:Int]=[:],birth:[String:Double]=[:]
  var fatal:String?
  do {
   let a=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
   let specs=a["targets"] as! [[String:Any]],control=URL(fileURLWithPath:a["control"] as! String)
   for spec in specs {
    let id=try KernelIdentity.read(spec["pid"] as! Int32)
    try require(id.executable==spec["executable"] as! String,"Executable mismatch")
    identities[spec["label"] as! String]=id
   }
   let begin=ProcessInfo.processInfo.systemUptime;var last=begin
   while !interrupted && ProcessInfo.processInfo.systemUptime-begin<(a["seconds"] as! Double) && !FileManager.default.fileExists(atPath:a["stop"] as! String) {
    for var spec in specs {
     let label=spec["label"] as! String
     do {
      let demand=try JSONSerialization.jsonObject(with:Data(contentsOf:control.appendingPathComponent("desired-"+label+".json"))) as! [String:Any]
      let generation=demand["generation"] as! Int,wanted=demand["active"] as! Bool
      if generation != generations[label] {
       try require(generation>=0 && generation>(generations[label] ?? -1),"Generation must increase")
       generations[label]=generation
       if let item=active.removeValue(forKey:label) {
        if let problem=await finish(item){emit(["event":"target_finalize_failed","label":label,"detail":problem])}
       }
       if wanted {
        try identities[label]!.validate(KernelIdentity.read(spec["pid"] as! Int32))
        if generation>0 {spec["output"]=control.appendingPathComponent(label+"-"+String(generation)+".mp4").path}
        let content=try await SCShareableContent.excludingDesktopWindows(false,onScreenWindowsOnly:false)
        let item=try CaptureItem(spec,content)
        try await item.stream.startCapture();active[label]=item;birth[label]=ProcessInfo.processInfo.systemUptime
        emit(["event":"capture_started","label":label,"generation":generation,"output":item.recorder.writer.outputURL.path,"wall_time":Date().timeIntervalSince1970])
       } else {emit(["event":"target_stopped","label":label,"generation":generation,"wall_time":Date().timeIntervalSince1970])}
      }
     } catch {
      if let item=active.removeValue(forKey:label){_=await finish(item)}
      emit(["event":"target_failed","label":label,"detail":String(describing:error),"wall_time":Date().timeIntervalSince1970])
     }
    }
    let now=ProcessInfo.processInfo.systemUptime
    let rows=CGWindowListCopyWindowInfo([.optionAll,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]]
    for (label,item) in active {
     do {
      try identities[label]!.validate(KernelIdentity.read(item.target.pid))
      let observation:WindowObservation
      if let rows=rows {
       if let row=rows.first(where:{($0[kCGWindowNumber as String] as? UInt32)==item.target.id}),let pid=row[kCGWindowOwnerPID as String] as? Int32 {observation=pid==item.target.pid ? .present:.wrongOwner(pid)} else {observation = .absent}
      } else {observation = .unavailable("Window list unavailable")}
      if var e=try item.presence.observe(observation,now:now){e["label"]=label;emit(e)}
      if let e=item.queue.sync(execute:{item.recorder.error}){throw Failure(e)}
      if now-birth[label]!>8 && !item.queue.sync(execute:{item.recorder.started}){throw Failure("No first frame")}
      if now-last>=2 {emit(["event":"capture_health","label":label,"frames":item.queue.sync{item.recorder.frames},"wall_time":Date().timeIntervalSince1970])}
     } catch {
      active.removeValue(forKey:label);_=await finish(item)
      emit(["event":"target_failed","label":label,"detail":String(describing:error),"wall_time":Date().timeIntervalSince1970])
     }
    }
    if now-last>=2 {last=now}
    try await Task.sleep(nanoseconds:100_000_000)
   }
  } catch {fatal=String(describing:error)}
  for (_,item) in active {
   do {try item.presence.finish()} catch {fatal=fatal ?? String(describing:error)}
   if let problem=await finish(item){fatal=fatal ?? problem}
  }
  if let fatal=fatal{emit(["event":"capture_failed","error":fatal]);exit(1)}
  emit(["event":"capture_finished","wall_time":Date().timeIntervalSince1970])
 }
}
