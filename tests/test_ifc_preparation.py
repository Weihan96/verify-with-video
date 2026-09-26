import argparse,hashlib,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/cross_task'))
import scene_options

class IFCPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name).resolve()
        for name in ('model.ifc','prepare.py','launcher.ts','blender'):(self.root/name).write_text('fixture')
        self.parser=argparse.ArgumentParser();scene_options.add_arguments(self.parser)
    def tearDown(self):self.tmp.cleanup()
    def args(self,*more):
        return self.parser.parse_args(['--blender',str(self.root/'blender'),'--bonsai-launcher',str(self.root/'launcher.ts'),*map(str,more)])
    def test_ifc_project_script_and_title_forward_unchanged(self):
        title='🤖️ Task title with spaces'
        args=self.args('--ifc',self.root/'model.ifc','--worktree',self.root,'--prepare-script',self.root/'prepare.py','--task-title',title)
        scene_options.validate(args);passed=scene_options.forwarded(args)
        self.assertEqual(passed[passed.index('--task-title')+1],title)
        self.assertEqual(passed[passed.index('--prepare-script')+1],str(self.root/'prepare.py'))
    def test_project_script_requires_ifc_and_actual_worktree(self):
        for args in [self.args('--prepare-script',self.root/'prepare.py'),self.args('--ifc',self.root/'model.ifc')]:
            with self.assertRaises(ValueError):scene_options.validate(args)
    def test_receipt_requires_correct_source_pid_and_unsaved_session(self):
        source=self.root/'model.ifc';sha=hashlib.sha256(source.read_bytes()).hexdigest();log=self.root/'log'
        good=dict(pid=42,ifc=str(source),sha256=sha,blend_saved=False,has_blend_warning=False)
        for field,value in [('pid',43),('ifc',str(self.root/'other.ifc')),('sha256','wrong'),('blend_saved',True),('has_blend_warning',True)]:
            log.write_text('TASK_BLENDER_IFC_READY '+json.dumps(dict(good,**{field:value}))+'\n')
            with self.subTest(field=field),self.assertRaises(ValueError):scene_options.ifc_ready(log,source,42,sha)
        log.write_text('TASK_BLENDER_IFC_READY '+json.dumps(good)+'\n');self.assertEqual(scene_options.ifc_ready(log,source,42,sha),good)
        source.write_text('changed')
        with self.assertRaises(ValueError):scene_options.ifc_ready(log,source,42,sha)
    def test_failure_is_not_hidden_by_worker_readiness(self):
        source=self.root/'model.ifc';log=self.root/'log';log.write_text('TASK_BLENDER_IFC_FAILED {"error":"bootstrap"}\n')
        with self.assertRaisesRegex(ValueError,'bootstrap failed'):scene_options.ifc_ready(log,source,42,'hash')
        log.write_text('loading\n');self.assertIsNone(scene_options.ifc_ready(log,source,42,'hash'))

    def test_partial_receipt_waits_for_complete_line(self):
        source=self.root/'model.ifc';log=self.root/'log'
        log.write_text('loading\nTASK_BLENDER_IFC_READY {"pid":')
        self.assertIsNone(scene_options.ifc_ready(log,source,42,'hash'))

if __name__=='__main__':unittest.main()
