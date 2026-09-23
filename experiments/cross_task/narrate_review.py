"""Add bounded Chinese synthesis to the final chapter map, preserving its timing."""
import argparse,concurrent.futures,json,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('output',type=pathlib.Path);p.add_argument('--prepare-only',action='store_true');args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True);audio=out/'audio';audio.mkdir(exist_ok=True)
texts=[
'两个真实任务，在不同桌面全屏操作 Blender。输入、点击、拖动和视口旋转同时进行。A、B 光标是辅助标注。',
'A 停止并重新开始自己的录屏时，B 继续操作，录像帧数也持续增加。',
'交换角色后，B 停录和重录，A 的输入与录像同样继续。',
'主会话确认 A 任务已经结束后，B 又完成三组操作，随后清理自己的实例。',
'前台持续收到鼠标、点击和键盘输入，焦点没有被抢走。这里使用自动化探针，并非真人。',
'独立任务与原片交叉核对通过。操作两倍速，已剪去调度停顿；不代表应用响应速度。']
if (out/'edit-map.json').exists() and json.loads((out/'edit-map.json').read_text()).get('queue_handoff'):
 texts[0]='准备完成就释放队列，另一任务已接手。两个真实任务的 Blender 仍在后台同时输入、点击、拖动和旋转。'
starts=[0,16,28,40,50,60];ends=starts[1:]+[70]
voice='zh-CN-XiaoxiaoNeural'
if not (out/'edit-map.json').exists() or not json.loads((out/'edit-map.json').read_text()).get('full_trial_passed'):
 texts[-1]='隔离场景已通过，收尾校验误报已修正。整轮复测尚未完成，暂不发布。'
def synth(i):
 path=audio/f'{i}.mp3'
 receipt=audio/f'{i}.txt'
 if not path.exists() or not receipt.exists() or receipt.read_text()!=texts[i]:subprocess.run([str(pathlib.Path.home()/'.local/bin/edge-tts'),'--voice',voice,'--text',texts[i],'--write-media',str(path)],check=True,timeout=60)
 receipt.write_text(texts[i])
 duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]));assert duration<ends[i]-starts[i]-.25,(i,duration)
 return dict(text=texts[i],start=starts[i]+.1,end=starts[i]+.1+duration,duration=duration,voice=voice,file=str(path),synthetic=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:narration=list(pool.map(synth,range(len(texts))))
(out/'narration.json').write_text(json.dumps(narration,ensure_ascii=False,indent=2)+'\n');print(json.dumps(narration,ensure_ascii=False,indent=2),flush=True)
if args.prepare_only:raise SystemExit
mapping=json.loads((out/'edit-map.json').read_text());assert [c['start'] for c in mapping['chapters']]==starts
inputs=[];filters=[]
for i,n in enumerate(narration):inputs+=['-i',n['file']];filters.append(f'[{i+1}:a]adelay={round(n["start"]*1000)}:all=1[a{i}]')
filters.append(''.join(f'[a{i}]' for i in range(len(narration)))+f'amix=inputs={len(narration)}:normalize=0,apad=whole_dur=70[a]')
subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/'silent.mp4'),*inputs,'-filter_complex',';'.join(filters),'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k','-t','70','-movflags','+faststart',str(out/'review.mp4')],check=True)
mapping['narration']=narration;(out/'edit-map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
