import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from test_workflow import FakeDoska
from doska_flow.config import Config
from doska_flow.state import State
from doska_flow.workflow import Workflow
from doska_flow.model import FlowError,metadata,with_metadata
from doska_flow.hooks import offline_capture,begin
from doska_flow.recovery import origin_from_config,queue_operation,replay,bind_unassigned
from doska_flow.brief import brief,markdown

TASK='90236f32-9752-4b80-a64b-b9dde5436dca'
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=State(Path(self.tmp.name)/'state')
        self.config=Config('local','one',endpoint='http://127.0.0.1:3846/mcp')
        self.backend=FakeDoska();self.w=Workflow(self.config,self.state,self.backend)
        self.gate={'task_id':TASK,'mode':'offline','origin':origin_from_config(self.config),'turn_id':'t'}
    def tearDown(self):self.state.close();self.tmp.cleanup()
    def capture(self):
        return offline_capture(self.state,self.gate,{'project':'p','title':'Queued','body':'Human notes','state':'To do','task_id':TASK,'session':'s','owner':'','participants':[],'acceptance':'','reconsider_on':None})
    def test_offline_capture_change_chain_replay_once(self):
        self.capture()
        queue_operation(self.state,self.gate,TASK,{'operation':'change','request':{'task_id':TASK,'state':'Doing','summary':'Started','session':'s','activity':'running'}})
        queue_operation(self.state,self.gate,TASK,{'operation':'change','request':{'task_id':TASK,'state':'Review','summary':'Ready','session':'s','activity':'idle'}})
        report=replay(self.state,self.config,False,workflow=self.w)
        self.assertFalse(report['apply']);self.assertEqual(self.backend.boards,{})
        report=replay(self.state,self.config,True,workflow=self.w)
        self.assertFalse(report.get('blocked'),report)
        self.assertEqual(report['remaining'],0)
        self.assertEqual(self.w.info(TASK)['metadata']['state'],'Review')
        replay(self.state,self.config,True,workflow=self.w)
        self.assertEqual(len(self.state.events('applied')),3)
    def test_ambiguous_capture_and_retry_does_not_duplicate(self):
        self.capture();self.backend.fail_create=True
        self.assertTrue(replay(self.state,self.config,True,self.w)['blocked'])
        self.assertFalse(replay(self.state,self.config,True,self.w).get('blocked'))
        self.assertEqual(sum(len(c['cards']) for b in self.backend.boards.values() for c in b['columns']),2)
    def test_changed_backend_or_workspace_never_replayed(self):
        self.capture()
        for config in (Config('local','one',endpoint='http://127.0.0.1:9999/mcp'),Config('local','two',endpoint='http://127.0.0.1:3846/mcp')):
            self.assertTrue(replay(self.state,config,True,self.w)['blocked'])
        self.assertEqual(self.backend.boards,{})
    def test_unconfigured_queue_needs_explicit_bind(self):
        self.gate['origin']=None;self.capture()
        self.assertEqual(replay(self.state)['events'][0]['status'],'unassigned')
        self.assertTrue(replay(self.state,self.config,True,self.w)['blocked'])
        with self.assertRaises(FlowError):bind_unassigned(self.state,self.config,TASK,'00000000-0000-0000-0000-000000000000')
        bind_unassigned(self.state,self.config,TASK,TASK)
        self.assertFalse(replay(self.state,self.config,True,self.w).get('blocked'))
    def test_manual_edits_conflict_and_done_delete_not_replayed(self):
        self.w.capture('p','Task',task_id=TASK)
        queue_operation(self.state,self.gate,TASK,{'operation':'change','request':{'task_id':TASK,'summary':'Offline summary'}})
        item=self.w.info(TASK);col=next(c for c in self.backend.boards[item['record']['board_id']]['columns'] if c['id']==item['column']['id']);card=next(c for c in col['cards'] if c['id']==item['card']['id'])
        m=metadata(card['body']);m['summary']='Human change';card['body']=with_metadata(card['body'],m)
        self.assertTrue(replay(self.state,self.config,True,self.w)['blocked'])
        self.assertEqual(metadata(card['body'])['summary'],'Human change')
        for operation,request in [('change',{'task_id':TASK,'state':'Done'}),('delete',{'task_id':TASK})]:
            with tempfile.TemporaryDirectory() as d:
                state=State(Path(d));queue_operation(state,self.gate,TASK,{'operation':operation,'request':request})
                self.assertTrue(replay(state,self.config,True,self.w)['blocked']);state.close()
    def test_two_pc_states_share_board_and_card_identity(self):
        r=self.w.capture('p','Task',task_id=TASK)
        with tempfile.TemporaryDirectory() as d:
            second=State(Path(d));other=Workflow(self.config,second,self.backend)
            attached=other.attach(TASK,r['board_id'],'other_pc')
            self.assertEqual(attached['card_id'],r['card_id']);self.assertEqual(len(self.backend.boards),1);second.close()
    def test_offline_cli_capture_normalizes_intent_and_replays(self):
        from doska_flow.cli import parser,dispatch
        home=Path(self.tmp.name)/'home';home.mkdir()
        state=State(home/'doska-state');state.set('gate','s',self.gate);state.close()
        args=parser().parse_args(['capture','Later','--session','s','--project','p','--task-id',TASK,'--state','Procrastinated'])
        dispatch(args,home)
        state=State(home/'doska-state')
        try:
            report=replay(state,self.config,True,Workflow(self.config,state,self.backend))
            self.assertFalse(report.get('blocked'),report)
        finally:state.close()
    def test_brief_respects_fresh_matching_local_heartbeat(self):
        r=self.w.capture('p','Active',task_id=TASK,session='s')
        self.w.start(TASK,'s')
        self.state.set('session','s',{'task_id':TASK,'activity':'running','last_activity':9999999998})
        report=brief(self.w,now=9999999999)
        self.assertEqual(report['sections']['stale'],[])
        self.state.set('session','s',{'task_id':TASK,'activity':'idle','last_activity':9999999998})
        row=brief(self.w,now=9999999999)['sections']['stale'][0]
        self.assertIn('unverified',row['activity_note'])
    def test_hosted_links_reject_embedded_credentials(self):
        for url in ('https://user:secret@example.com','https://example.com?token=secret','https://example.com#secret','https://'):
            with self.assertRaises(FlowError):Config('local','one',web_url=url)
    def test_brief_is_read_only_uses_actual_column_and_defer_date(self):
        records={}
        for i,state in enumerate(('To do','Procrastinated','Doing','Waiting','Review','Done')):
            r=self.w.capture('p',state,state='Procrastinated' if state=='Procrastinated' else 'To do',reconsider_on='2026-11-09' if state=='Procrastinated' else None)
            records[state]=r
            if state not in ('To do','Procrastinated'):
                self.w.change(r['task_id'],state=state,explicit_done=state=='Done',next_action='Approve' if state=='Waiting' else None,actor='Alice' if state=='Waiting' else None,activity='running' if state=='Doing' else 'idle')
        r=records['To do'];self.backend.call('move_card',{'boardId':r['board_id'],'cardId':r['card_id'],'columnId':r['columns']['Review']})
        before=json.dumps(self.backend.boards,sort_keys=True)
        report=brief(self.w,today='2026-11-09',now=9999999999)
        self.assertEqual(report['tasks'],6);self.assertEqual(len(report['sections']['review']),2)
        self.assertEqual(len(report['sections']['reconsider']),1);self.assertEqual(len(report['sections']['stale']),1)
        self.assertEqual(len(report['suggestions']),3);self.assertIn('Ready for review',markdown(report))
        self.assertEqual(json.dumps(self.backend.boards,sort_keys=True),before)
if __name__=='__main__':unittest.main()
