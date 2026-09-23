"""Edit actual recordings; retain raw-to-final mapping and explicit result freezes."""
import argparse,concurrent.futures,json,pathlib,subprocess
from PIL import Image,ImageDraw,ImageFont
p=argparse.ArgumentParser();p.add_argument('run',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);args=p.parse_args();r=args.run;out=args.output;out.mkdir(parents=True,exist_ok=True);edit=r/'edit';edit.mkdir(exist_ok=True)
load=lambda p:json.loads(p.read_text())
audit=load(r/'audit.json');assert audit['scenario_checks_passed'],'Scenario checks must be independently reviewed before rendering'
rows=lambda p:[json.loads(s) for s in p.read_text().splitlines() if s.startswith('{')]
t0=load(r/'schedule.json')['start_at'];capture=rows(r/'capture/capture.jsonl');first={pathlib.Path(x['output']).stem:x['wall_time'] for x in capture if x['event']=='first_frame'}
# A normal queue owner may record the foreground probe independently.
if 'Foreground' not in first:
 logs=list((r/'Foreground').glob('record-*.jsonl'));assert len(logs)==1
 first['Foreground']=next(x['wall_time'] for x in rows(logs[0]) if x.get('event')=='first_frame')
font='/System/Library/Fonts/STHeiti Medium.ttc';clips=[]
def add(src,b,e,title,subtitle,speed=2,hold=0):clips.append(dict(source=str(r/'capture'/(src+'.mp4')),source_key=src,begin=b-first[src],end=e-first[src],wall_begin=b,wall_end=e,speed=speed,freeze_seconds=hold,title=title,subtitle=subtitle))
add('A-1',t0,t0+12,'A 独立输入、点击、拖动与旋转',('准备队列已释放 · A/B 后台同时操作；彩色光标为标注' if audit.get('queue_handoff') else '任务 A · 两个真实任务同时操作；A/B 光标是辅助标注'))
add('B-1',t0,t0+12,'同一时段回放 · B 独立操作','任务 B · 同步原片顺序回放，不是左右分屏')
add('Foreground',t0,t0+8,'同一时段回放 · 前台输入','自动化探针接收原生鼠标与键盘；不是人工作业')
add('B-1',t0+20,t0+44,'A 停录、重录 · B 继续工作','两次录屏控制均由 A task 自己发出；此片为 B 原片')
add('A-3',t0+60,t0+84,'B 停录、重录 · A 继续工作','交换角色；此片为 A 原片，实际事件与帧数均持续增加')
btrial=rows(r/'B/trial.jsonl');after=next(x['time'] for x in btrial if x['event']=='batch_sent' and x.get('stage')=='after-A');end=next(x['time'] for x in reversed(btrial) if x['event']=='batch_observed' and x.get('stage')=='after-A')
# Preserve all three post-completion batches, then clearly freeze the final result.
duration=int((end-after)/2*30)/30;assert duration<10
add('B-3',after,after+duration*2,'A task 已结束 · B 再完成三组操作','依据 Codex 实际 completed 状态放行；结尾标注暂停查看',hold=10-duration)
clips[-1]['freeze_source_time']=end-first['B-3']
add('Foreground',t0+60,t0+80,'前台保持正常输入 · 焦点未转到 Blender','自动化探针 · 同期鼠标、点击、键盘事件均已记录')
bduration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(r/'capture/B-3.mp4')]))
last=first['B-3']+bduration-.1
add('B-3',last,last,('完整复测结论 · 受限操作范围内通过' if audit['original_runner_passed'] else '隔离场景已核对 · 完整流程尚未全绿'),('独立任务完整复测、实际操作日志与原片交叉核对通过' if audit['original_runner_passed'] else '首轮收尾校验误报已修正；第二轮因前台切换提前中止'),speed=1,hold=10)
t=0
for i,x in enumerate(clips):
 frames=round((x['end']-x['begin'])/x['speed']*30)+round(x['freeze_seconds']*30)
 x.update(index=i,output_start=t,output_end=t+frames/30);t=x['output_end']
chapters=[dict(start=s,title=title) for s,title in [(0,'并行输入与视口'),(16,'A 停录与重录'),(28,'B 停录与重录'),(40,'A 结束后 B 继续'),(50,'前台输入'),(60,'核验结论')]]
assert abs(t-70)<.001 and [clips[i]['output_start'] for i in (0,3,4,5,6,7)]==[c['start'] for c in chapters]
def normalize(key):
 target=edit/(key+'-cfr.mp4')
 if not target.exists():subprocess.run(['ffmpeg','-v','error','-y','-i',str(r/'capture'/(key+'.mp4')),'-vf','fps=30','-an','-c:v','libx264','-preset','ultrafast','-crf','21',str(target)],check=True)
 return key,target
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:normalized=dict(pool.map(normalize,first))
def banner(x,freeze=False):
 im=Image.new('RGB',(1280,134),'#101827');d=ImageDraw.Draw(im)
 d.text((22,9),x['title'],font=ImageFont.truetype(font,27),fill='white')
 d.text((22,51),x['subtitle'],font=ImageFont.truetype(font,21),fill='#d0dfef')
 detail='暂停查看 · 原片结果定格' if freeze else f"操作 {x['speed']} 倍速 · 任务调度停顿已剪除 · 成片节奏不代表应用响应速度"
 d.text((22,91),detail,font=ImageFont.truetype(font,19),fill='#9fb2ca');path=edit/f'banner-{x["index"]}-{freeze}.png';im.save(path);return path
def render(x):
 i=x['index'];segments=[];moving=(x['end']-x['begin'])/x['speed']
 base='scale=1280:804:force_original_aspect_ratio=decrease,pad=1280:804:(ow-iw)/2:(oh-ih)/2:color=0x101827,format=yuv420p,pad=1280:938:0:134:color=0x101827'
 for freeze,duration in [(False,moving),(True,x['freeze_seconds'])]:
  if duration<=0:continue
  overlay=banner(x,freeze);target=edit/f'clip-{i}-{freeze}.mp4'
  if freeze:
   frame=edit/f'freeze-{i}.png';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(max(0,x.get('freeze_source_time',x['end'])-.04)),'-i',str(normalized[x['source_key']]),'-frames:v','1',str(frame)],check=True);inputs=['-loop','1','-i',str(frame)];pts='setpts=PTS-STARTPTS'
  else:inputs=['-ss',str(x['begin']),'-t',str(x['end']-x['begin']),'-i',str(normalized[x['source_key']])];pts=f"setpts=(PTS-STARTPTS)/{x['speed']}"
  graph=f'[0:v]{pts},fps=30,{base}[v];[v][1:v]overlay=0:0:shortest=1[out]'
  subprocess.run(['ffmpeg','-v','error','-y',*inputs,'-loop','1','-i',str(overlay),'-filter_complex',graph,'-map','[out]','-frames:v',str(round(duration*30)),'-an','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(target)],check=True);segments.append(target)
 print('Rendered',i,flush=True);return segments
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:segments=sum(pool.map(render,clips),[])
concat=edit/'concat.txt';concat.write_text(''.join("file '"+str(s)+"'\n" for s in segments))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(out/'silent.mp4')],check=True)
mapping=dict(queue_handoff=audit.get('queue_handoff'),full_trial_passed=audit['original_runner_passed'],duration=t,chapters=chapters,clips=clips,alignment='Source video zero aligned to logged first-frame wall receipt; boundary frames independently reviewed.',waiting=dict(agent_scheduling='cut',application_long_waits='none observed in selected formal operations; no invented computation duration'),raw_run=str(r),foreground_input='automated native probe, not a human',narration='synthetic Chinese narration added after editing')
(out/'edit-map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(duration=t,chapters=chapters),ensure_ascii=False))
