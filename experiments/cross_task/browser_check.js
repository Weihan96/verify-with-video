async (page) => {
  const mapping=await page.evaluate(async()=>await(await fetch('edit-map.json')).json());
  await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
  const requireMuted=async()=>{if(!await page.evaluate(()=>document.querySelector('video').muted))throw Error('Mute the target player before any playback or chapter click')};
  await requireMuted();
  const report=[];
  try {
  for(const width of [1100,390]){
    await page.setViewportSize({width,height:1000});
    for(let i=0;i<mapping.chapters.length;i++){
      const c=mapping.chapters[i],button=page.getByRole('navigation',{name:'验收章节'}).getByRole('button').nth(i);
      const expected=String(Math.floor(c.start/60)).padStart(2,'0')+':'+String(c.start%60).padStart(2,'0')+' '+c.title;
      if(await button.textContent()!==expected)throw Error('Wrong chapter label');
      await requireMuted();
      await page.evaluate(()=>document.querySelector('video').pause());
      await button.click();
      await page.waitForFunction(s=>{const v=document.querySelector('video');return !v.seeking&&v.readyState>=3&&Math.abs(v.currentTime-s)<.034},c.start);
      await page.waitForTimeout(300); // Let native media-control seek feedback settle for visual evidence.
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const observed=await page.evaluate(i=>{const v=document.querySelector('video'),b=document.querySelectorAll('nav button')[i],r=b.getBoundingClientRect();return {time:v.currentTime,duration:v.duration,width:v.videoWidth,height:v.videoHeight,button:{x:r.x,y:r.y,width:r.width,height:r.height,fontSize:getComputedStyle(b).fontSize,scrollWidth:b.scrollWidth,clientWidth:b.clientWidth},pageWidth:document.documentElement.scrollWidth,viewport:innerWidth}},i);
      if(observed.button.height<44||parseFloat(observed.button.fontSize)<16||observed.pageWidth>width||observed.button.scrollWidth>observed.button.clientWidth)throw Error('Mobile legibility or target failed');
      await page.locator('video').screenshot({path:`output/playwright/chapter-${width}-${i}.png`});
      await requireMuted();
      await page.evaluate(()=>{const v=document.querySelector('video');if(!v.muted)throw Error('Player lost mute');return v.play()});
      await page.waitForFunction(t=>{const v=document.querySelector('video');if(!v.muted)throw Error('Player lost mute');return v.currentTime>t+.15},observed.time);
      const next=(i+1)%mapping.chapters.length;
      await requireMuted();
      await page.getByRole('navigation',{name:'验收章节'}).getByRole('button').nth(next).click();
      await page.waitForFunction(t=>{const v=document.querySelector('video');if(!v.muted)throw Error('Chapter reset mute');return !v.seeking&&!v.paused&&v.currentTime>t+.15&&v.currentTime<t+2},mapping.chapters[next].start);
      const playback=await page.evaluate(()=>{const v=document.querySelector('video');v.pause();return {muted:v.muted,time:v.currentTime}});
      if(!playback.muted)throw Error('Playback was not muted');
      report.push({viewport:width,index:i,label:expected,mapped:c.start,...observed,playingJumpTarget:mapping.chapters[next].start,playback});
    }
    const rects=await page.getByRole('navigation').getByRole('button').evaluateAll(bs=>bs.map(b=>{const r=b.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}}));
    for(let i=0;i<rects.length;i++)for(let j=i+1;j<rects.length;j++){const a=rects[i],b=rects[j];if(Math.min(a.right,b.right)>Math.max(a.x,b.x)&&Math.min(a.bottom,b.bottom)>Math.max(a.y,b.y))throw Error('Buttons overlap')}
    await page.screenshot({path:`output/playwright/page-${width}.png`,fullPage:true});
  }
  return {passed:true,checks:report};
  } finally { await page.evaluate(()=>document.querySelector('video')?.pause()); }
}
