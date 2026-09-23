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
        self.g=dict(id='test-group',run=str(pathlib.Path(self.tmp.name)/'run'),coordinator='test-coordinator',reservation=self.lease,phase='preparing',preparing='A',members={'A':dict(label='A',thread_id='test-a',state='enrolled',token_hash=access.digest('token-a')),'B':dict(label='B',thread_id='test-b',state='enrolled',token_hash=access.digest('token-b'))})
        self.save()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def save(self):access.queue.atomic_json(self.path,self.g)
    def check(self,op='launch',token='token-a',thread='test-a'):return access.authorize(self.path,token,thread,op)
    def formal(self):
        for label,m in self.g['members'].items():
            m.update(state='ready',run='/run/'+label,session='/run/'+label+'/session.json',pid=123 if label=='A' else 456,window=1 if label=='A' else 2,identity='birth-'+label,blender_window=label)
        access.admit(self.g);self.save()
    def release(self):
        access.queue.execute(access.shared(),'release','test-coordinator',self.lease)
    def test_formal_survives_release_and_another_queue_owner(self):
        self.formal();self.release()
        q=access.queue.execute(access.shared(),'request','test-outsider')['queue']['current']
        for op in ('simulate','record-control','record-read','close'):self.check(op)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'test-outsider'}):
            with self.assertRaisesRegex(ValueError,'not an invited'):self.check('simulate',thread='test-outsider')
        access.mutate(self.path,lambda g:g['members']['A'].update(state='closed'))
        access.mutate(self.path,lambda g:g['members']['B'].update(state='closed'))
        access.mutate(self.path,access.finish)
        current=access.queue.execute(access.shared(),'status')['queue']['current']
        self.assertEqual(q,current)
        with self.assertRaisesRegex(ValueError,'closed'):self.check('simulate')
    def test_release_before_admission_cannot_be_promoted(self):
        self.release()
        with self.assertRaisesRegex(ValueError,'global reservation'):self.formal()
    def test_formal_without_admission_rejected(self):
        self.formal();self.g.pop('admission');self.save()
        with self.assertRaisesRegex(ValueError,'admission missing'):self.check('simulate')
    def test_changed_admitted_identity_rejected(self):
        self.formal();self.release()
        for field,value in [('pid',999),('window',999),('identity','new'),('token_hash','new'),('run','/foreign'),('session','/foreign/session')]:
            with self.subTest(field=field):
                old=self.g['members']['A'][field];self.g['members']['A'][field]=value;self.save()
                with self.assertRaisesRegex(ValueError,'binding changed'):self.check('simulate')
                self.g['members']['A'][field]=old
    def test_coordinator_background_authority_without_queue(self):
        self.formal();self.release()
        with self.assertRaisesRegex(ValueError,'Coordinator'):access.coordinator(self.g)
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'test-coordinator'}):access.coordinator(self.g)
    def test_cannot_finish_group_before_broker_finalization(self):
        self.formal();self.release()
        for m in self.g['members'].values():m['state']='closed'
        capture=pathlib.Path(self.g['run'])/'capture';capture.mkdir(parents=True)
        log=capture/'capture.jsonl';log.write_text('')
        (capture/'broker.json').write_text(json.dumps(dict(coordinator='test-coordinator',log=str(log))))
        with self.assertRaisesRegex(ValueError,'Finalize recorder'):access.finish(self.g)
        self.assertEqual(self.g['phase'],'formal')
        log.write_text('{"event":"capture_finished"}\n');access.finish(self.g)
        self.assertEqual(self.g['phase'],'closed')
    def test_exclusive_preparation(self):
        self.check()
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'test-b'}):
            with self.assertRaisesRegex(ValueError,'Exclusive preparation'):self.check(token='token-b',thread='test-b')
    def test_cannot_claim_another_task(self):
        with self.assertRaisesRegex(ValueError,'actual environment'):self.check(token='token-b',thread='test-b')
    def test_capability_is_subject_bound(self):
        with self.assertRaisesRegex(ValueError,'capability mismatch'):self.check(token='token-b')
    def test_system_input_is_never_participant_permission(self):
        self.formal();self.release()
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
