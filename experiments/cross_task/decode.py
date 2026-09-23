"""Validate VFR recordings without rounding decoded frames into an inferred FPS.

Null-output validation must retain the source time base. Otherwise ffmpeg can
report duplicate output DTS even while every source DTS and decoded PTS is valid.
"""
import json,pathlib,subprocess

def validate(output):
    output=pathlib.Path(output)
    command=['ffmpeg','-v','error','-xerror','-i',str(output),'-fps_mode','passthrough','-enc_time_base','-1','-f','null','-']
    result=dict(output=str(output),command=command,valid=False)
    try:
        decoded=subprocess.run(command,capture_output=True,text=True,timeout=30)
        result.update(returncode=decoded.returncode,stderr=decoded.stderr)
        probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_packets','-show_frames','-show_entries','packet=dts:frame=best_effort_timestamp','-of','json',str(output)],capture_output=True,text=True,timeout=30)
        result.update(probe_returncode=probe.returncode,probe_stderr=probe.stderr)
        if probe.returncode==0:
            rows=json.loads(probe.stdout)['packets_and_frames']
            dts=[r['dts'] for r in rows if r['type']=='packet']
            pts=[r['best_effort_timestamp'] for r in rows if r['type']=='frame']
            result.update(packets=len(dts),decoded_frames=len(pts),packet_dts_strict=bool(dts) and all(b>a for a,b in zip(dts,dts[1:])),decoded_pts_strict=bool(pts) and all(b>a for a,b in zip(pts,pts[1:])))
            result['valid']=decoded.returncode==0 and not decoded.stderr.strip() and not probe.stderr.strip() and result['packet_dts_strict'] and result['decoded_pts_strict'] and len(dts)==len(pts)
    except (subprocess.TimeoutExpired,OSError,ValueError,KeyError) as error:result['error']=str(error)
    return result

if __name__=='__main__':
    import sys
    results=[validate(p) for p in sys.argv[1:]];print(json.dumps(results,indent=2));sys.exit(0 if results and all(r['valid'] for r in results) else 1)
