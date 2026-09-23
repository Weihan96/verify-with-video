"""Isolated authorization tests; synthetic IDs never touch the live desktop queue."""
import importlib.util,json,os,pathlib,sys,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/cross_task'))
import access
import desktop

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'CODEX_HOME':self.tmp.name,'CODEX_THREAD_ID':'test-a'});self.env.start()
        q=access.queue.execute(access.shared(),'request','test-coordinator');self.lease=q['queue']['current']['lease_id']
        directory=access.shared()/'isolation-groups';directory.mkdir();self.path=directory/'test.json'
        self.g=dict(coordinator='test-coordinator',reservation=self.lease,phase='preparing',preparing='A',members={'A':dict(label='A',thread_id='test-a',state='enrolled',token_hash=access.digest('token-a')),'B':dict(label='B',thread_id='test-b',state='enrolled',token_hash=access.digest('token-b'))})
        self.save()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def save(self):access.queue.atomic_json(self.path,self.g)
    def check(self,op='launch',token='token-a',thread='test-a'):return access.authorize(self.path,token,thread,op)
    def test_exclusive_preparation(self):
        self.check()
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'test-b'}):
            with self.assertRaisesRegex(ValueError,'Exclusive preparation'):self.check(token='token-b',thread='test-b')
    def test_cannot_claim_another_task(self):
        with self.assertRaisesRegex(ValueError,'actual environment'):self.check(token='token-b',thread='test-b')
    def test_capability_is_subject_bound(self):
        with self.assertRaisesRegex(ValueError,'capability mismatch'):self.check(token='token-b')
    def test_system_input_is_never_participant_permission(self):
        self.g.update(phase='formal',preparing=None);self.g['members']['A']['state']='ready';self.save()
        self.check('simulate')
        for op in ('action','record','stop','restore','fullscreen'):
            with self.subTest(op=op),self.assertRaises(ValueError):self.check(op)
    def test_released_parent_lease_invalidates_children(self):
        access.queue.execute(access.shared(),'release','test-coordinator',self.lease)
        with self.assertRaisesRegex(ValueError,'global reservation'):self.check()
    def test_closed_member_cannot_resume(self):
        self.g['members']['A']['state']='closed';self.save()
        with self.assertRaisesRegex(ValueError,'already closed'):self.check('close')
    def test_arbitrary_group_file_rejected(self):
        other=pathlib.Path(self.tmp.name)/'other.json';other.write_text(json.dumps(self.g))
        with self.assertRaisesRegex(ValueError,'subordinate'):access.authorize(other,'token-a','test-a','launch')
    def test_recorder_requires_matching_ready_generation(self):
        root=pathlib.Path(self.tmp.name);log=root/'capture.jsonl';registry=root/'registry.json'
        r=dict(pid=123,identity='birth',label='A',generation=1,log=str(log),cross_task_broker=True)
        registry.write_text(json.dumps(dict(recording=r)));session=dict(registry=str(registry))
        rows=[dict(event='capture_started',label='A',generation=1,output='A-1.mp4')]
        def write():log.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        write()
        with patch.object(desktop,'identity',return_value='birth'):
            with self.assertRaisesRegex(ValueError,'not ready'):access.recording(session)
            rows.append(dict(event='first_frame',output='A-1.mp4'));write();access.recording(session)
            rows.append(dict(event='target_stopped',label='A',generation=2));write()
            with self.assertRaisesRegex(ValueError,'stopped or failed'):access.recording(session)

if __name__=='__main__':unittest.main()
