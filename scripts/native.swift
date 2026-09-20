import AppKit
import ApplicationServices
import ScreenCaptureKit
import AVFoundation
import CoreImage
import Darwin
var interrupted=false

struct Failure: Error, CustomStringConvertible { let description: String; init(_ s:String){description=s} }
func require(_ b:Bool,_ s:String) throws {if !b {throw Failure(s)}}
func emit(_ v:[String:Any]) {let d=try! JSONSerialization.data(withJSONObject:v,options:[.sortedKeys]);print(String(data:d,encoding:.utf8)!);fflush(stdout)}
func windows(onscreen:Bool=true)->[[String:Any]] {CGWindowListCopyWindowInfo(onscreen ? [.optionOnScreenOnly,.excludeDesktopElements]:[.optionAll,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []}
func rect(_ w:[String:Any])->CGRect {CGRect(dictionaryRepresentation:w[kCGWindowBounds as String] as! CFDictionary)!}
func bounds(_ r:CGRect)->[String:Double] {["x":r.minX,"y":r.minY,"width":r.width,"height":r.height]}
func attr(_ e:AXUIElement,_ name:String)->CFTypeRef? {var v:CFTypeRef?;AXUIElementCopyAttributeValue(e,name as CFString,&v);return v}
func axRect(_ e:AXUIElement)->CGRect? {
 guard let p=attr(e,kAXPositionAttribute),let z=attr(e,kAXSizeAttribute),CFGetTypeID(p)==AXValueGetTypeID(),CFGetTypeID(z)==AXValueGetTypeID() else{return nil}
 var point=CGPoint.zero,size=CGSize.zero
 AXValueGetValue(p as! AXValue,.cgPoint,&point);AXValueGetValue(z as! AXValue,.cgSize,&size)
 return CGRect(origin:point,size:size)
}
func pause(_ s:Double=0.1){RunLoop.current.run(until:Date().addingTimeInterval(s))}
struct Target {
 let pid:pid_t,id:CGWindowID,executable:String
 func window(onscreen:Bool=true) throws->[String:Any] {
  guard let app=NSRunningApplication(processIdentifier:pid) else{throw Failure("AppKit process lookup returned nil for PID \(pid)")}
  guard app.executableURL?.resolvingSymlinksInPath().path == executable else{throw Failure("AppKit executable mismatch for PID \(pid): observed=\(app.executableURL?.path ?? "nil") terminated=\(app.isTerminated)")}
  let candidates = windows(onscreen:onscreen)
  guard let w=candidates.first(where:{($0[kCGWindowNumber as String] as? UInt32)==id && ($0[kCGWindowOwnerPID as String] as? Int32)==pid}) else{throw Failure("Target window missing/offscreen or owner changed")}
  return w
 }
 func focus() throws {
  try require(AXIsProcessTrusted(),"Accessibility permission required to restore window")
  _=try window(onscreen:false)
  guard let app=NSRunningApplication(processIdentifier:pid) else{throw Failure("Process exited")}
  let root=AXUIElementCreateApplication(pid)
  // Unhide only the verified process, then raise/unminimize the explicitly bound window.
  app.unhide();app.activate(options:[.activateIgnoringOtherApps]);pause(0.3)
  let w=try window(onscreen:false),r=rect(w)
  let matches=(attr(root,kAXWindowsAttribute) as? [AXUIElement] ?? []).filter {e in guard let a=axRect(e) else{return false};return abs(a.minX-r.minX)<2 && abs(a.minY-r.minY)<2 && abs(a.width-r.width)<2 && abs(a.height-r.height)<2}
  try require(matches.count<=1,"Ambiguous accessibility window bounds; no window raised")
  if matches.count==1 {
   AXUIElementSetAttributeValue(matches[0],kAXMinimizedAttribute as CFString,kCFBooleanFalse)
   AXUIElementPerformAction(matches[0],kAXRaiseAction as CFString)
   AXUIElementSetAttributeValue(root,kAXFocusedWindowAttribute as CFString,matches[0])
  }
  let deadline=Date().addingTimeInterval(2)
  repeat {
   if (try? checkFocus()) != nil {return}
   pause(0.1)
  }while Date()<deadline
  throw Failure("Bound window could not be restored to a visible focused state; no input sent")
 }
 func checkFocus() throws {
  _=try window()
  try require(NSWorkspace.shared.frontmostApplication?.processIdentifier==pid,"Focus lost; action stopped")
  let root=AXUIElementCreateApplication(pid),r=rect(try window())
  if let focused=attr(root,kAXFocusedWindowAttribute),CFGetTypeID(focused)==AXUIElementGetTypeID(),let f=axRect(focused as! AXUIElement) {
   try require(abs(f.minX-r.minX)<2 && abs(f.minY-r.minY)<2 && abs(f.width-r.width)<2 && abs(f.height-r.height)<2,"A different accessibility window is focused; bind the dialog explicitly")
  } else {
   let top=windows().first {($0[kCGWindowLayer as String] as? Int)==0}
   try require(top?[kCGWindowNumber as String] as? UInt32 == id,"Another normal window is active; inspect and bind the dialog explicitly")
  }
 }
 func point(_ a:[String:Any]) throws->CGPoint {
  let r=rect(try window())
  guard let x=a["x"] as? Double,let y=a["y"] as? Double else{throw Failure("x/y required")}
  try require(x.isFinite && y.isFinite && x>=0 && y>=0 && x<1 && y<1,"Coordinates must be normalized window fractions in [0,1)")
  return CGPoint(x:r.minX+x*r.width,y:r.minY+y*r.height)
 }
 func hit(_ p:CGPoint) throws {
  var element:AXUIElement?
  let status=AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(),Float(p.x),Float(p.y),&element)
  var owner:pid_t=0
  if status == .success,let element=element {AXUIElementGetPid(element,&owner)}
  try require(status == .success && owner == pid,"Point hit-test does not belong to target: AX=\(status.rawValue) owner=\(owner)")
 }
}
final class Input {
 let target:Target
 let birth:Date?
 let src=CGEventSource(stateID:.hidSystemState)!
 var held:[CGKeyCode]=[]
 var mouseHeld:CGEventType?=nil
 var last=CGPoint.zero
 init(_ t:Target){target=t;birth=NSRunningApplication(processIdentifier:t.pid)?.launchDate;src.localEventsSuppressionInterval=0}
 func validProcess()->Bool {guard let app=NSRunningApplication(processIdentifier:target.pid) else{return false};return app.executableURL?.resolvingSymlinksInPath().path == target.executable && app.launchDate == birth}
 func post(_ e:CGEvent) throws {
  try require(!interrupted,"Interrupted; releasing owned input")
  if [.keyUp,.leftMouseUp,.rightMouseUp].contains(e.type) {try require(validProcess(),"Process identity changed before release")} else{try target.checkFocus()}
  if [.mouseMoved,.leftMouseDown,.leftMouseUp,.rightMouseDown,.rightMouseUp,.leftMouseDragged,.scrollWheel].contains(e.type) {e.post(tap:.cghidEventTap)} else{e.postToPid(target.pid)}
 }
 func keyEvent(_ k:CGKeyCode,_ down:Bool,_ flags:CGEventFlags)->CGEvent {let e=CGEvent(keyboardEventSource:src,virtualKey:k,keyDown:down)!;e.flags=flags;return e}
 func clean() {
  // Cleanup targets only the verified process; never refocus or send global key-up.
  guard validProcess() else{return}
  for k in held.reversed()+[55,54,56,60,59,62,58,61] {keyEvent(k,false,[]).postToPid(target.pid)}
  if let t=mouseHeld {let e=CGEvent(mouseEventSource:src,mouseType:t,mouseCursorPosition:last,mouseButton:t == .rightMouseUp ? .right:.left)!;e.flags=[];e.post(tap:.cghidEventTap)}
  held=[];mouseHeld=nil
 }
 func run(_ a:[String:Any]) throws {
  try require(AXIsProcessTrusted() && CGPreflightPostEventAccess(),"Accessibility/input permission missing")
  try target.focus();clean();defer{clean()}
  let spec:[String:(CGKeyCode,CGEventFlags)]=["cmd":(55,.maskCommand),"ctrl":(59,.maskControl),"shift":(56,.maskShift),"alt":(58,.maskAlternate)]
  let mods=a["modifiers"] as? [String] ?? []
  try require(mods.allSatisfy{spec[$0] != nil},"Unknown modifier")
  var flags=CGEventFlags()
  for m in mods {let(k,f)=spec[m]!;flags.insert(f);held.append(k);try post(keyEvent(k,true,flags));pause(0.06)}
  guard let op=a["op"] as? String else{throw Failure("op required")}
  func mouse(_ type:CGEventType,_ p:CGPoint,_ button:CGMouseButton = .left,_ count:Int64=1) throws {
   last=p
   let e=CGEvent(mouseEventSource:src,mouseType:type,mouseCursorPosition:p,mouseButton:button)!
   e.flags=flags;e.setIntegerValueField(.mouseEventClickState,value:count)
   e.setIntegerValueField(.mouseEventWindowUnderMousePointer,value:Int64(target.id))
   e.setIntegerValueField(.mouseEventWindowUnderMousePointerThatCanHandleThisEvent,value:Int64(target.id))
   try post(e)
  }
  if ["click","move","scroll","drag"].contains(op) {
   let p=try target.point(a);try target.hit(p)
   try mouse(.mouseMoved,p);pause(0.12)
   if op == "click" {
    let right=a["button"] as? String == "right", count=a["count"] as? Int ?? 1
    try require((1...2).contains(count),"count must be 1 or 2")
    for i in 1...count {mouseHeld=right ? .rightMouseUp:.leftMouseUp;try mouse(right ? .rightMouseDown:.leftMouseDown,p,right ? .right:.left,Int64(i));pause(0.08);try mouse(right ? .rightMouseUp:.leftMouseUp,p,right ? .right:.left,Int64(i));mouseHeld=nil;pause(0.08)}
   } else if op == "scroll" {
    guard let delta=a["delta"] as? Int32 else{throw Failure("delta required")}
    let e=CGEvent(scrollWheelEvent2Source:src,units:.pixel,wheelCount:1,wheel1:delta,wheel2:0,wheel3:0)!;e.location=p;e.flags=flags;try post(e)
   } else if op == "drag" {
    let end=try target.point(["x":a["to_x"] as Any,"y":a["to_y"] as Any]);try target.hit(end)
    mouseHeld = .leftMouseUp;try mouse(.leftMouseDown,p)
    for i in 1...20 {let q=CGPoint(x:p.x+(end.x-p.x)*Double(i)/20,y:p.y+(end.y-p.y)*Double(i)/20);try target.hit(q);try mouse(.leftMouseDragged,q);pause(0.025)}
    try mouse(.leftMouseUp,end);mouseHeld=nil
   }
  } else if op == "key" {
   guard let k=a["code"] as? UInt16,k<128 else{throw Failure("code must be macOS virtual key 0..127")}
   held.append(k);try post(keyEvent(k,true,flags));pause(0.08);try post(keyEvent(k,false,flags));held.removeAll{$0==k}
  } else if op == "text" {
   guard let s=a["text"] as? String,!s.isEmpty,mods.isEmpty else{throw Failure("text required; no modifiers for Unicode text")}
   for character in s {
    let chars=Array(String(character).utf16)
    held.append(0)
    for down in [true,false] {let e=keyEvent(0,down,[]);e.keyboardSetUnicodeString(stringLength:chars.count,unicodeString:chars);try post(e);pause(0.015)}
    held.removeAll{$0==0}
   }
  } else if op != "reset" {throw Failure("Unknown operation")}
  pause(0.25)
 }
}
final class Recorder:NSObject,SCStreamOutput,SCStreamDelegate {
 let writer:AVAssetWriter,input:AVAssetWriterInput
 var started=false,frames=0,error:String?=nil
 init(_ path:String,_ w:Int,_ h:Int)throws {
  writer=try AVAssetWriter(outputURL:URL(fileURLWithPath:path),fileType:.mp4)
  input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:w,AVVideoHeightKey:h,AVVideoCompressionPropertiesKey:[AVVideoAverageBitRateKey:8000000]])
  input.expectsMediaDataInRealTime=true;writer.shouldOptimizeForNetworkUse=true
  super.init();try require(writer.canAdd(input),"Cannot add video input");writer.add(input)
 }
 func stream(_ s:SCStream,didStopWithError e:Error){error=e.localizedDescription}
 func stream(_ s:SCStream,didOutputSampleBuffer b:CMSampleBuffer,of type:SCStreamOutputType){
  guard type == .screen,b.isValid,CMSampleBufferGetImageBuffer(b) != nil,
   let attachments=CMSampleBufferGetSampleAttachmentsArray(b,createIfNecessary:false) as? [[SCStreamFrameInfo:Any]],let raw=attachments.first?[.status] as? Int,SCFrameStatus(rawValue:raw) == .complete else{return}
  if !started {guard writer.startWriting() else{error=writer.error?.localizedDescription;return};writer.startSession(atSourceTime:CMSampleBufferGetPresentationTimeStamp(b));started=true;emit(["event":"first_frame","wall_time":Date().timeIntervalSince1970,"pts":CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(b))])}
  if input.isReadyForMoreMediaData {if input.append(b){frames+=1}else{error=writer.error?.localizedDescription ?? "append failed"}}
 }
}
@main struct Main {
 static func main() async {
  signal(SIGINT){_ in interrupted=true};signal(SIGTERM){_ in interrupted=true}
  _=NSApplication.shared
  do {
   let args=CommandLine.arguments
   let a=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:args[1]))) as! [String:Any]
   if a["command"] as? String == "windows" {
    let scope=a["pid"] as? Int32,hidden=a["include_hidden"] as? Bool ?? false
    try require(!hidden || scope != nil,"Offscreen enumeration requires a verified PID and executable")
    var process:[String:Any]=[:]
    if let pid=scope {
     guard let app=NSRunningApplication(processIdentifier:pid),app.executableURL?.resolvingSymlinksInPath().path == a["executable"] as? String else{throw Failure("Requested PID/executable mismatch")}
     process=["pid":pid,"executable":app.executableURL!.resolvingSymlinksInPath().path,"hidden":app.isHidden,"active":app.isActive]
    }
    let rows=windows(onscreen:!hidden).filter {w in (w[kCGWindowLayer as String] as? Int)==0 && (scope == nil || w[kCGWindowOwnerPID as String] as? Int32 == scope)}
    emit(["windows":rows.map {w->[String:Any] in let pid=w[kCGWindowOwnerPID as String] as! Int32;return ["pid":pid,"window":w[kCGWindowNumber as String]!,"title":w[kCGWindowName as String] ?? "","app":w[kCGWindowOwnerName as String] ?? "","onscreen":w[kCGWindowIsOnscreen as String] as? Bool ?? false,"bounds":bounds(rect(w)),"executable":NSRunningApplication(processIdentifier:pid)?.executableURL?.resolvingSymlinksInPath().path ?? ""]},"process":process,"scope":hidden ? "all windows of verified process":"visible windows","input_permission":CGPreflightPostEventAccess(),"screen_permission":CGPreflightScreenCaptureAccess(),"accessibility":AXIsProcessTrusted()]);return
   }
   let t=Target(pid:a["pid"] as! Int32,id:a["window"] as! UInt32,executable:a["executable"] as! String)
   if a["command"] as? String == "release-input" {
    try require(AXIsProcessTrusted() && CGPreflightPostEventAccess(),"Input permission missing")
    Input(t).clean();emit(["event":"input_released","ui_verified":false]);return
   }
   if a["command"] as? String == "restore" {
    try t.focus();emit(["event":"restored","pid":t.pid,"window":t.id,"onscreen":true,"focused":true,"bounds":bounds(rect(try t.window())),"ui_verified":false]);return
   }
   if a["command"] as? String == "action" {
    try Input(t).run(a["action"] as! [String:Any]);emit(["event":"sent","ui_verified":false,"target_window_present":(try? t.window()) != nil,"wall_time":Date().timeIntervalSince1970]);return
   }
   let w=try t.window(),r=rect(w)
   try require(CGPreflightScreenCaptureAccess(),"Screen recording permission missing")
   if a["command"] as? String == "snapshot" {
    try require(a["display"] == nil,"Snapshot targets exactly one window; display mode is for recording")
    let option:CGWindowImageOption=(a["scale"] as? Int ?? 2)==1 ? [.boundsIgnoreFraming,.nominalResolution]:[.boundsIgnoreFraming,.bestResolution]
    guard let image=CGWindowListCreateImage(.null,.optionIncludingWindow,t.id,option) else{throw Failure("Window screenshot failed")}
    let rep=NSBitmapImageRep(cgImage:image)
    try rep.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:a["output"] as! String))
    var ids=[CGDirectDisplayID](repeating:0,count:16),count:UInt32=0
    CGGetActiveDisplayList(16,&ids,&count)
    emit(["event":"snapshot","bounds":bounds(r),"width":image.width,"height":image.height,"displays":ids.prefix(Int(count)).map{["id":$0,"bounds":bounds(CGDisplayBounds($0))] as [String:Any]}]);return
   }
   let captureIdentity=try KernelIdentity.read(t.pid)
   try require(captureIdentity.executable==t.executable,"Kernel executable does not match bound target")
   let content=try await SCShareableContent.excludingDesktopWindows(false,onScreenWindowsOnly:false)
   guard let sw=content.windows.first(where:{$0.windowID==t.id && $0.owningApplication?.processID==t.pid}) else{throw Failure("Capture target missing")}
   var filter=SCContentFilter(desktopIndependentWindow:sw)
   var size=r.size
   var captureDisplay:SCDisplay?=nil
   var captureWindowIDs:Set<CGWindowID>=[]
   if let displayID=a["display"] as? UInt32 {
    guard let display=content.displays.first(where:{$0.displayID==displayID}) else{throw Failure("Display not found")}
    let owned=content.windows.filter{$0.owningApplication?.processID==t.pid}
    captureDisplay=display;captureWindowIDs=Set(owned.map{$0.windowID})
    filter=SCContentFilter(display:display,including:owned);size=display.frame.size
   }
   let cfg=SCStreamConfiguration();let scale=Double(a["scale"] as? Int ?? 2)
   cfg.width=Int(size.width*scale)/2*2;cfg.height=Int(size.height*scale)/2*2
   cfg.minimumFrameInterval=CMTime(value:1,timescale:30);cfg.showsCursor=true;cfg.capturesAudio=false
   try require(a["command"] as? String == "record","Unknown command")
   let recorder=try Recorder(a["output"] as! String,cfg.width,cfg.height),q=DispatchQueue(label:"verify.video.frames")
   let stream=SCStream(filter:filter,configuration:cfg,delegate:recorder)
   try stream.addStreamOutput(recorder,type:.screen,sampleHandlerQueue:q);try await stream.startCapture()
   let start=Date(),seconds=a["seconds"] as! Double,stop=a["stop"] as! String
   emit(["event":"capture_started","wall_time":start.timeIntervalSince1970,"width":cfg.width,"height":cfg.height,"pid":t.pid,"window":t.id])
   var captureError:String?=nil
   var lastWindowRefresh=Date.distantPast
   var presence=WindowPresenceGuard(expectedPID:t.pid,graceSeconds:2)
   let monotonicStart=ProcessInfo.processInfo.systemUptime
   var lastHeartbeat=monotonicStart
   var identityChecks=0
   emit(["event":"target_identity_pinned","pid":t.pid,"birth_seconds":captureIdentity.seconds,"birth_microseconds":captureIdentity.microseconds,"executable":captureIdentity.executable,"window":t.id,"window_grace_seconds":2])
   do {
   while !interrupted && Date().timeIntervalSince(start)<seconds && !FileManager.default.fileExists(atPath:stop) {
    try await Task.sleep(nanoseconds:100_000_000)
    try captureIdentity.validate(KernelIdentity.read(t.pid));identityChecks+=1
    let now=ProcessInfo.processInfo.systemUptime
    let observation:WindowObservation
    if let rows=CGWindowListCopyWindowInfo([.optionAll,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] {
     if let candidate=rows.first(where:{($0[kCGWindowNumber as String] as? UInt32)==t.id}) {
      if let owner=candidate[kCGWindowOwnerPID as String] as? Int32 {observation=owner==t.pid ? .present:.wrongOwner(owner)}else{observation = .unavailable("Window record has no owner PID")}
     }else{observation = .absent}
    }else{observation = .unavailable("CGWindowListCopyWindowInfo returned nil/unreadable")}
    if var event=try presence.observe(observation,now:now) {event["wall_time"]=Date().timeIntervalSince1970;event["pid"]=t.pid;event["window"]=t.id;emit(event)}
    if now-lastHeartbeat>=10 {
     emit(["event":"capture_health","wall_time":Date().timeIntervalSince1970,"elapsed_seconds":now-monotonicStart,"identity_checks":identityChecks,"window_missing_checks":presence.totalMissing,"window_recoveries":presence.recoveries,"frames":q.sync{recorder.frames}]);lastHeartbeat=now
    }
    if let display=captureDisplay,Date().timeIntervalSince(lastWindowRefresh)>0.2 {
     let current=try await SCShareableContent.excludingDesktopWindows(false,onScreenWindowsOnly:false)
     let owned=current.windows.filter{$0.owningApplication?.processID==t.pid}
     let ids=Set(owned.map{$0.windowID})
     if ids != captureWindowIDs {try await stream.updateContentFilter(SCContentFilter(display:display,including:owned));captureWindowIDs=ids}
     lastWindowRefresh=Date()
    }
    if let e=q.sync(execute:{recorder.error}) {throw Failure(e)}
    if Date().timeIntervalSince(start)>5 && !q.sync(execute:{recorder.started}) {throw Failure("No complete frame within 5 seconds")}
   }
   try presence.finish()
   }catch{captureError=String(describing:error)}
   do{try await stream.stopCapture()}catch{captureError=captureError ?? String(describing:error)}
   if recorder.started {q.sync{recorder.input.markAsFinished()};await recorder.writer.finishWriting()}
   if let failure=captureError {emit(["event":"capture_failed","error":failure,"frames":recorder.frames,"wall_time":Date().timeIntervalSince1970]);exit(1)}
   try require(recorder.frames>0 && recorder.writer.status == .completed,recorder.writer.error?.localizedDescription ?? "No frames/finalization failed")
   emit(["event":"capture_finished","frames":recorder.frames,"wall_time":Date().timeIntervalSince1970])
  }catch{emit(["error":String(describing:error),"wall_time":Date().timeIntervalSince1970]);exit(1)}
 }
}
