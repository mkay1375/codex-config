import copy
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from doska_flow.config import Config
from doska_flow.state import State
from doska_flow.workflow import Workflow, normalize_remote
from doska_flow.model import Conflict,FlowError,metadata,with_metadata

class FakeDoska:
    def __init__(self):self.boards={};self.n=0;self.fail_create=False
    def id(self,p):self.n+=1;return p+str(self.n)
    def connect(self):return {'reachable':True}
    def call(self,tool,a):
        if tool=='list_boards':return [{'id':b['boardId'],'title':b['title']} for b in self.boards.values()]
        if tool=='create_board':
            b={'boardId':self.id('board'),'title':a['title'],'columns':[{'id':self.id('col'),'title':s,'done':s=='Done','cards':[]} for s in ('To Do','In Progress','Done')]}
            self.boards[b['boardId']]=b;return {'board':{'id':b['boardId']},'columns':b['columns']}
        b=self.boards[a['boardId']]
        if tool=='get_board':return copy.deepcopy(b)
        if tool=='create_column':
            col={'id':self.id('col'),'title':a['title'],'done':a['done'],'cards':[]};b['columns'].append(col);return copy.deepcopy(col)
        if tool=='update_column':
            c=next(c for c in b['columns'] if c['id']==a['columnId']);c.update({k:v for k,v in a.items() if k not in ('boardId','columnId')});return copy.deepcopy(c)
        if tool=='create_card':
            c=next(c for c in b['columns'] if c['id']==a['columnId']);card={'id':self.id('card'),'title':a['title'],'body':a['body']};c['cards'].append(card)
            if self.fail_create and a['title']!='Project info':self.fail_create=False;raise FlowError('Ambiguous timeout')
            return copy.deepcopy(card)
        col,card=next((c,t) for c in b['columns'] for t in c['cards'] if t['id']==a['cardId'])
        if tool=='move_card':col['cards'].remove(card);next(c for c in b['columns'] if c['id']==a['columnId'])['cards'].append(card)
        if tool=='update_card':card.update({k:v for k,v in a.items() if k not in ('boardId','cardId')})
        return copy.deepcopy(card)

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=State(Path(self.tmp.name)/'state');self.backend=FakeDoska();self.w=Workflow(Config('local','local-test'),self.state,self.backend)
    def tearDown(self):self.state.close();self.tmp.cleanup()
    def test_six_columns_capture_start_review_done(self):
        r=self.w.capture('github.com/u/repo','Later',state='Procrastinated',session='thr_x',participants=['A'],reconsider_on='2027-01-01')
        self.assertEqual(len(self.backend.boards[r['board_id']]['columns']),6)
        self.assertEqual(r['metadata']['activity'],'idle');self.assertEqual(r['metadata']['state'],'Procrastinated')
        self.w.start(r['task_id'],'thr_x')
        result=self.w.finish(r['task_id'],'Review','Implemented','tests passed',session='thr_x')
        self.assertEqual(result['metadata']['state'],'Review')
        with self.assertRaises(FlowError):self.w.change(r['task_id'],state='Done')
        self.assertEqual(self.w.change(r['task_id'],state='Done',explicit_done=True)['metadata']['state'],'Done')
    def test_ambiguous_creation_retry_finds_uuid(self):
        self.backend.fail_create=True
        task='90236f32-9752-4b80-a64b-b9dde5436dca'
        with self.assertRaises(FlowError):self.w.capture('p','Task',task_id=task)
        r=self.w.capture('p','Task',task_id=task)
        self.assertEqual(sum(len(c['cards']) for c in self.backend.boards[r['board_id']]['columns']),2)
    def test_human_notes_preserved_and_metadata_conflict_rejected(self):
        r=self.w.capture('p','Task','Original human notes')
        board=self.backend.boards[r['board_id']];card=next(t for c in board['columns'] for t in c['cards'] if t['id']==r['card_id'])
        card['body']='Additional note\n'+card['body']+'\nFooter'
        self.w.change(r['task_id'],summary='progress')
        self.assertTrue(card['body'].startswith('Additional note\n'));self.assertTrue(card['body'].endswith('\nFooter'))
        m=metadata(card['body']);m['summary']='another machine';card['body']=with_metadata(card['body'],m)
        with self.assertRaises(Conflict):self.w.change(r['task_id'],summary='stale')
    def test_duplicate_boards_and_owner(self):
        r=self.w.capture('p','Task');self.w.start(r['task_id'],'one')
        with self.assertRaises(Conflict):self.w.start(r['task_id'],'two')
        self.w.start(r['task_id'],'two',takeover=True)
        b=copy.deepcopy(self.backend.boards[r['board_id']]);b['boardId']='duplicate';self.backend.boards['duplicate']=b
        with self.assertRaises(Conflict):self.w.board('p')
    def test_remote_normalization(self):
        self.assertEqual(normalize_remote('git@github.com:User/Repo.git'),normalize_remote('https://github.com/user/repo.git'))
        self.assertEqual(normalize_remote('https://secret@github.com/User/Repo.git'),'github.com/user/repo')
    def test_waiting_requires_action_and_actor(self):
        r=self.w.capture('p','Task')
        with self.assertRaises(FlowError):self.w.change(r['task_id'],state='Waiting')
if __name__=='__main__':unittest.main()

class CorrectnessTests(WorkflowTests):
    def test_manual_move_rejected_for_summary_only_update(self):
        r=self.w.capture('p','Task')
        self.backend.call('move_card',{'boardId':r['board_id'],'cardId':r['card_id'],'columnId':r['columns']['Procrastinated']})
        with self.assertRaises(Conflict):self.w.change(r['task_id'],summary='stale state')
    def test_edit_fields_preserves_integration(self):
        r=self.w.capture('p','Old','Old notes')
        result=self.w.change(r['task_id'],title='New',body='New human notes',owner='A',participants=['B'],acceptance='Pass tests',deadline='2027-01-01',priority='high')
        item=self.w.info(r['task_id'])
        self.assertEqual(item['card']['title'],'New');self.assertTrue(item['card']['body'].startswith('New human notes'))
        self.assertEqual(item['metadata']['owner'],'A');self.assertEqual(item['metadata']['participants'],['B'])
        with self.assertRaises(FlowError):self.w.change(r['task_id'],body=with_metadata('',{'schema':1}))
    def test_local_links_include_navigation_ids(self):
        r=self.w.capture('p','Task')
        links=self.w.links(r['task_id'])
        self.assertEqual(links['board_id'],r['board_id'])
        self.assertEqual(links['card_id'],r['card_id'])
        self.assertIsNone(links['web_url'])

    def test_operation_lock_is_reentrant_and_bounds_other_instances(self):
        other=State(self.state.root)
        try:
            with self.state.operation_lock():
                with self.state.operation_lock():
                    with self.assertRaises(FlowError):
                        with other.operation_lock(timeout=0.05):pass
            with other.operation_lock(timeout=0.05):pass
        finally:other.close()


class AttachStateTests(WorkflowTests):
    def test_attach_adopts_manual_defer_and_completion(self):
        for target in ('Procrastinated', 'Done'):
            with self.subTest(target=target):
                r=self.w.capture('p','Manual move '+target,'Human notes')
                self.backend.call('move_card',{'boardId':r['board_id'],'cardId':r['card_id'],'columnId':r['columns'][target]})
                self.assertEqual(self.w.info(r['task_id'])['state'],target)
                self.w.attach(r['task_id'],r['board_id'])
                result=self.w.change(r['task_id'],summary='Keep manual decision')
                self.assertEqual(result['metadata']['state'],target)
                self.assertEqual(result['metadata']['activity'],'idle')
                self.assertTrue(self.w.info(r['task_id'])['card']['body'].startswith('Human notes'))
