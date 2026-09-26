import { test, expect } from 'bun:test';
import { mkdtempSync, writeFileSync, rmSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { backgroundPlan, launchBackground } from '../scripts/bonsai_background_launcher';

test('preserves launcher ownership and runs IFC loader before background worker', async () => {
 const root=realpathSync(mkdtempSync(join(tmpdir(),'background-plan-')));
 const old=process.env.CODEX_THREAD_ID;process.env.CODEX_THREAD_ID='isolated-test-owner';
 try {
  const launcher=join(root,'launcher.ts'), worker=join(root,'worker.py');writeFileSync(worker,'');
  writeFileSync(launcher,`export function makePlan(v) {return {root:v.worktree,binary:v.blender,kind:'ifc',owner:{marker:'--codex-task-owner=real'},requestMarker:'--codex-task-request=original',taskTitle:v['task-title'],args:['--python','load-ifc.py','--','--ifc',v.ifc,'--no-save','--prepare-script',v['prepare-script'],'--codex-task-owner=real','--codex-task-request=original']}}`);
  const {plan}=await backgroundPlan({launcher,worker,run:root,worktree:root,blender:'/test/Blender',ifc:'/source/model.ifc',label:'A','prepare-script':'/project/setup.py','task-title':'Exact task title'});
  const split=plan.args.indexOf('--');const flags=plan.args.slice(0,split),tail=plan.args.slice(split+1);
  expect(flags).toEqual(['--no-window-focus','--window-fullscreen','--enable-event-simulate','--python','load-ifc.py','--python',worker]);
  expect(tail).toContain('--codex-task-owner=real');expect(tail).toContain('--no-save');expect(tail).toContain('/project/setup.py');
  expect(tail).toContain(plan.requestMarker);expect(plan.requestMarker).not.toBe('--codex-task-request=original');
  expect(tail.slice(-5)).toEqual(['--probe-dir',root,'--probe-label','A','--preserve-scene']);
  expect(plan.taskTitle).toBe('Exact task title');
 } finally {if(old===undefined)delete process.env.CODEX_THREAD_ID;else process.env.CODEX_THREAD_ID=old;rmSync(root,{recursive:true,force:true});}
});

test('classifies only failures before invoking the launcher as not started', async () => {
 const root=realpathSync(mkdtempSync(join(tmpdir(),'background-failure-')));
 const old=process.env.CODEX_THREAD_ID;process.env.CODEX_THREAD_ID='isolated-test-owner';
 try {
  expect((await launchBackground({launcher:join(root,'missing.ts')})).status).toBe('not_started');
  const launcher=join(root,'uncertain.ts'),worker=join(root,'worker.py');writeFileSync(worker,'');
  writeFileSync(launcher,`export function makePlan(){return {kind:'ifc',args:['--'],requestMarker:'marker'}};export async function launch(){throw new Error('unknown process state')}`);
  await expect(launchBackground({launcher,worker,run:root,label:'A'})).rejects.toThrow('unknown process state');
 } finally {if(old===undefined)delete process.env.CODEX_THREAD_ID;else process.env.CODEX_THREAD_ID=old;rmSync(root,{recursive:true,force:true});}
});
