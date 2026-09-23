// Read-only corroboration for explicitly supplied owned window IDs.
import Foundation
import CoreGraphics
import Darwin
let handle=dlopen("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics",RTLD_LAZY)!
typealias Connection = @convention(c) () -> Int32
typealias Spaces = @convention(c) (Int32,Int32,CFArray) -> Unmanaged<CFArray>?
guard let connectionSymbol=dlsym(handle,"CGSMainConnectionID"),let spacesSymbol=dlsym(handle,"CGSCopySpacesForWindows") else {fatalError("Read-only Spaces API unavailable")}
let connection=unsafeBitCast(connectionSymbol,to:Connection.self)()
let spaces=unsafeBitCast(spacesSymbol,to:Spaces.self)
var results:[[String:Any]]=[]
for arg in CommandLine.arguments.dropFirst() {
 guard let id=UInt32(arg) else{fatalError("Expected explicit window ID")}
 let value=spaces(connection,7,[NSNumber(value:id)] as CFArray)?.takeRetainedValue() as? [NSNumber] ?? []
 results.append(["window":id,"spaces":value])
}
let data=try JSONSerialization.data(withJSONObject:["time":Date().timeIntervalSince1970,"windows":results],options:[.sortedKeys])
print(String(data:data,encoding:.utf8)!)
