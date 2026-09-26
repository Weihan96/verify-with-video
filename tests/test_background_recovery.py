"""Interrupted start retains authority to collect, never permission to input."""
import json
import os
import pathlib
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/cross_task'))
import access
import control
import desktop

class RecoveryTests(unittest.TestCase):
    def test_interrupted_close_recovers_only_matching_receipt_and_dead_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            run=pathlib.Path(directory);registry=run/'registry.json';desktop.dump(registry,dict(recording=None))
            record=dict(thread_id='owner',pid=123,identity='birth',executable='/test/app',closed=42)
            session=dict(record,launch=dict(record),registry=str(registry),work=str(run))
            session.pop('closed');path=run/'session.json';receipt=run/'closed-123.json';desktop.dump(receipt,record)
            with patch.dict(os.environ,{'CODEX_THREAD_ID':'owner'}),patch.object(os,'kill') as kill:
                with patch.object(desktop,'identity',return_value='birth'):
                    with self.assertRaisesRegex(ValueError,'PID is live'):desktop.recover_closed_session(session,path)
                with patch.object(desktop,'identity',side_effect=subprocess.CalledProcessError(1,['ps'])):
                    desktop.dump(receipt,dict(record,thread_id='other'))
                    with self.assertRaisesRegex(ValueError,'ownership mismatch'):desktop.recover_closed_session(session,path)
                    desktop.dump(receipt,record)
                    result=desktop.recover_closed_session(session,path)
                self.assertTrue(result['recovered']);self.assertEqual(json.loads(path.read_text())['closed'],42)
                kill.assert_not_called()
    def test_interruption_before_demand_can_be_collected_without_start_frame(self):
        self.interrupted_start(False)

    def test_interruption_after_capture_started_collects_failure_and_preserves_other_target(self):
        self.interrupted_start(True)

    def interrupted_start(self, started):
        with tempfile.TemporaryDirectory() as directory:
            run=pathlib.Path(directory);registry=run/'registry.json';log=run/'capture.jsonl';log.write_text('')
            group=run/'group.json';demand=run/'desired-A.json'
            other=run/'desired-B.json';desktop.dump(other,dict(generation=3,active=True));other_before=other.read_bytes()
            desktop.dump(demand,dict(generation=0,active=False));desktop.dump(registry,dict(recording=None))
            broker=dict(label='A',group=str(group),pid=123,identity='birth',output=str(run),log=str(log),cross_task_broker=True,generation=0)
            session=dict(registry=str(registry),isolation_broker=broker)
            participant=dict(run=str(run),group=str(group),token='own-token')
            member=dict(label='A');real_dump=desktop.dump
            def interrupted_dump(path,value):
                if path==demand and value['active']:
                    if started:
                        real_dump(path,value)
                        log.write_text(json.dumps(dict(event='capture_started',label='A',generation=value['generation'],output=str(run/'A-1.mp4')))+'\n')
                    raise KeyboardInterrupt('test interruption')
                real_dump(path,value)
                if path==demand:
                    with log.open('a') as f:
                        if started:f.write(json.dumps(dict(event='writer_finished',label='A',output=str(run/'A-1.mp4'),valid=True,frames=1))+'\n')
                        f.write(json.dumps(dict(event='target_stopped',label='A',generation=value['generation']))+'\n')
            with patch.object(desktop,'isolation_context'),patch.object(desktop,'load_session',return_value=session),patch.object(control,'alive',return_value=True),patch.object(control,'input_control'),patch.object(control,'validate_video',return_value=dict(valid=True,decoded_frames=1)),patch.object(access,'own',return_value='owner'),patch.object(desktop,'dump',side_effect=interrupted_dump):
                with self.assertRaises(KeyboardInterrupt):control._control(participant,{},member,'start')
                pending=json.loads(registry.read_text())['recording']
                self.assertEqual(pending['state'],'starting')
                self.assertEqual(pending['generation'],1)
                with self.assertRaisesRegex(ValueError,'pending'):access.recording(session)
                result=control._control(participant,{},member,'collect')
                self.assertFalse(result['capture_valid'])
                if not started:self.assertTrue(result['collected'])
                self.assertEqual(other.read_bytes(),other_before)
                self.assertIsNone(json.loads(registry.read_text())['recording'])
                self.assertFalse(json.loads(demand.read_text())['active'])

if __name__=='__main__':unittest.main()
