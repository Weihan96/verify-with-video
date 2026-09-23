"""Render the experiment's review page from its final edit map (no timing copy)."""
import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('mapping',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);p.add_argument('--video',required=True);args=p.parse_args();mapping=json.loads(args.mapping.read_text())
chapters=mapping['chapters'];assert len(chapters)>1 and all(0<=c['start']<mapping['duration'] for c in chapters)
assert [c['start'] for c in chapters]==sorted(set(c['start'] for c in chapters))
status='完整复测通过。' if mapping.get('full_trial_passed') else '隔离场景已核对；完整流程复测尚未完成。'
if mapping.get('queue_handoff'):status+=' 准备队列已释放；B 取得新租约操作前台，A/B 的 Blender 同时在后台继续。'
data=json.dumps(dict(chapters=chapters,duration=mapping['duration'],video=args.video),ensure_ascii=False).replace('<','\\u003c')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Blender 跨任务验收</title><link rel="icon" href="data:,"><style>
*{box-sizing:border-box}body{margin:0;background:#101827;color:#edf3fb;font:16px/1.6 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:24px 16px}h1{font-size:26px;line-height:1.3;margin:0 0 8px}p{color:#c0ccdc;margin:8px 0 18px}video{display:block;width:100%;background:#000;border-radius:8px}nav{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}button{font:inherit;font-size:16px;line-height:1.4;text-align:left;min-height:44px;padding:10px 14px;border:1px solid #586b85;border-radius:8px;background:#1b2a40;color:#edf3fb;white-space:normal;cursor:pointer;max-width:100%}button:focus-visible{outline:3px solid #a9d9ff;outline-offset:3px}button[aria-current=true]{background:#cbe5ff;color:#10213a}#current{font-size:14px;margin:0}small{display:block;color:#a5b4c8;margin-top:16px}@media(max-width:500px){main{padding:20px 12px}h1{font-size:23px}nav{gap:8px}button{flex:1 1 100%}}
</style><main><h1>Blender 跨任务验收</h1><p>两个真实任务、两个全屏桌面。同步素材按章节顺序回放。</p><p>__STATUS__</p><video id="video" controls playsinline preload="metadata"></video><nav aria-label="验收章节"></nav><p id="current" aria-live="polite"></p><small>前台鼠标键盘由自动化探针操作。操作片段为 2 倍速，任务调度停顿已剪除；成片节奏不代表应用响应速度。原片及剪辑映射单独保留。</small></main><script>
const review=__DATA__;window.review=review;const video=document.querySelector('video');video.src=review.video;
function timestamp(seconds){const h=Math.floor(seconds/3600),m=Math.floor(seconds/60)%60,s=+(seconds%60).toFixed(3);const parts=String(s).split('.');const ss=parts[0].padStart(2,'0')+(parts[1]?'.'+parts[1]:'');return(h?String(h).padStart(2,'0')+':':'')+String(m).padStart(2,'0')+':'+ss}
for(const chapter of review.chapters){const b=document.createElement('button');b.type='button';b.textContent=timestamp(chapter.start)+' '+chapter.title;b.dataset.seconds=String(chapter.start);b.onclick=()=>{video.currentTime=chapter.start;document.querySelector('#current').textContent=b.textContent;for(const other of document.querySelectorAll('nav button'))other.setAttribute('aria-current',String(other===b))};document.querySelector('nav').append(b)}
</script></html>'''.replace('__DATA__',data).replace('__STATUS__',status)
args.output.write_text(html)
