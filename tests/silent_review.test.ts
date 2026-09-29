import { test, expect } from 'bun:test';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';

function review(search: string) {
  const dir=mkdtempSync(join(tmpdir(),'silent-review-'));
  try {
    writeFileSync(join(dir,'map.json'),JSON.stringify({duration:30,chapters:[{title:'Start',start:0},{title:'Next',start:12}]}));
    const result=Bun.spawnSync(['python3','experiments/cross_task/review_page.py',join(dir,'map.json'),join(dir,'index.html'),'--video','with-audio.mp4']);
    expect(result.exitCode).toBe(0);
    const html=readFileSync(join(dir,'index.html'),'utf8');
    const buttons: any[]=[];
    let mutedAtSource: boolean|undefined;
    const video: any={muted:false,defaultMuted:false,autoplay:false,paused:true,currentTime:0,
      set src(value) { this.source=value; mutedAtSource=this.muted; }};
    const current={textContent:''};
    const document={querySelector:(s: string)=>s==='video'?video:s==='#current'?current:{append:(b: any)=>buttons.push(b)},
      querySelectorAll:()=>buttons,createElement:()=>({dataset:{},setAttribute(){}})};
    runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)![1],{document,location:{search},URLSearchParams,window:{}});
    return {video,buttons,mutedAtSource};
  } finally {rmSync(dir,{recursive:true,force:true});}
}

test('QA sets mute before media source and retains it through playing chapter seeks',()=>{
  const {video,buttons,mutedAtSource}=review('?qa=muted');
  expect(mutedAtSource).toBe(true);expect(video.autoplay).toBe(false);
  video.paused=false;
  for (const [i,button] of buttons.entries()) {
    button.onclick();expect(video.muted).toBe(true);expect(video.paused).toBe(false);expect(video.currentTime).toBe(i===0?0:12);
  }
  expect(review('?qa=muted').mutedAtSource).toBe(true);
});

test('ordinary delivery is paused, has the same audio-capable source and permits user volume choice',()=>{
  const {video,buttons,mutedAtSource}=review('');
  expect(mutedAtSource).toBe(false);expect(video.defaultMuted).toBe(false);expect(video.autoplay).toBe(false);
  expect(video.source).toBe('with-audio.mp4');expect(video.paused).toBe(true);
  video.muted=true;buttons[1].onclick();expect(video.muted).toBe(true);
  video.muted=false;buttons[0].onclick();expect(video.muted).toBe(false);
});

test('chapter checker refuses an unmuted player before any chapter or playback action',async()=>{
  const check=runInNewContext(readFileSync('experiments/cross_task/browser_check.js','utf8'));
  let reads=0,actions=0;
  const page={evaluate:async()=>++reads===1?{chapters:[{start:0,title:'Start'}]}:false,
    waitForFunction:async()=>{},setViewportSize:async()=>{actions++},getByRole:()=>{actions++;throw Error('Unexpected interaction')}};
  await expect(check(page)).rejects.toThrow('Mute the target player');
  expect(actions).toBe(0);
});
