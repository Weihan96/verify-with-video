// Disposable foreground input receiver. Receipts are actual AppKit events.
// Records mouse/foreground/flags and pasteboard revision, never clipboard text.
import AppKit
import CoreGraphics
let run = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
let path = run.appendingPathComponent("foreground.jsonl")
FileManager.default.createFile(atPath: path.path, contents: nil)
let log = try FileHandle(forWritingTo: path)
func record(_ data:[String:Any]) {
 var d=data;d["time"]=Date().timeIntervalSince1970
 let bytes=try! JSONSerialization.data(withJSONObject:d,options:[.sortedKeys])
 try! log.write(contentsOf:bytes);try! log.write(contentsOf:Data([10]))
}
class InputView:NSView {
 var clicks=0, moves=0, text="", pos=NSPoint.zero
 override var acceptsFirstResponder:Bool {true}
 override var isFlipped:Bool {true}
 override func draw(_ dirtyRect:NSRect) {
  NSColor(calibratedRed:0.08,green:0.12,blue:0.2,alpha:1).setFill();bounds.fill()
  let lines=["Foreground mouse and keyboard probe", "Actual mouse clicks: \(clicks)  |  moves: \(moves)", "Actual key input: \(text)", "Blender A and B operate in separate full-screen Spaces.", "This window receives native system input during the test."]
  for (i,s) in lines.enumerated() {
   (s as NSString).draw(at:NSPoint(x:35,y:35+i*50),withAttributes:[.font:NSFont.systemFont(ofSize:i==0 ? 25:18),.foregroundColor:NSColor.white])
  }
  NSColor.systemCyan.setStroke();let p=NSBezierPath(ovalIn:NSRect(x:pos.x-12,y:pos.y-12,width:24,height:24));p.lineWidth=3;p.stroke()
 }
 override func mouseMoved(with e:NSEvent) {moves+=1;pos=convert(e.locationInWindow,from:nil);record(["event":"mouse_move","x":pos.x,"y":pos.y]);needsDisplay=true}
 override func mouseDragged(with e:NSEvent){mouseMoved(with:e)}
 override func mouseDown(with e:NSEvent){clicks+=1;record(["event":"click","count":clicks]);needsDisplay=true}
 override func keyDown(with e:NSEvent){let s=e.characters ?? "";text+=s;record(["event":"key","characters":s,"keycode":e.keyCode]);needsDisplay=true}
}
let app=NSApplication.shared
app.setActivationPolicy(.regular)
let window=NSWindow(contentRect:NSRect(x:40,y:60,width:1180,height:700),styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false)
window.title="Independent input acceptance — foreground probe"
let view=InputView(frame:NSRect(x:0,y:0,width:1180,height:700));window.contentView=view
window.acceptsMouseMovedEvents=true
window.makeKeyAndOrderFront(nil);window.makeFirstResponder(view);app.activate(ignoringOtherApps:true)
var last: String=""
let timer=Timer.scheduledTimer(withTimeInterval:0.01,repeats:true){ _ in
 let p=CGEvent(source:nil)!.location
 let data:[String:Any]=["event":"sample","cursor_x":p.x,"cursor_y":p.y,"front_pid":NSWorkspace.shared.frontmostApplication?.processIdentifier ?? -1,"flags":CGEventSource.flagsState(.combinedSessionState).rawValue,"clipboard_revision":NSPasteboard.general.changeCount]
 let signature="\(p.x),\(p.y),\(data["front_pid"]!),\(data["flags"]!),\(data["clipboard_revision"]!)"
 if signature != last {record(data);last=signature}
}
record(["event":"ready","pid":ProcessInfo.processInfo.processIdentifier,"window":window.windowNumber])
app.run()
