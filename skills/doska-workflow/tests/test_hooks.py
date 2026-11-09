import copy
import os
import shutil
import shlex
import importlib.util
import json
import sys
import tempfile
import subprocess
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from doska_flow.hooks import submit,handle,begin,record_outcome,safe_bridge_command,offline_capture
from doska_flow.state import State
from doska_flow.model import FlowError
spec=importlib.util.spec_from_file_location('setup_flow',Path(__file__).parents[1]/'scripts/setup.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)

class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
        (self.home/'doska.local.toml').write_text('mode="remote"\nworkspace="fake"\nendpoint="https://example.invalid/mcp"\ntoken_env="FAKE_TOKEN"\n')
        self.state=State(self.home/'doska-state')
        self.event={'session_id':'session-1','turn_id':'turn-1','prompt':'Implement the export feature','hook_event_name':'UserPromptSubmit'}
    def tearDown(self):self.state.close();self.tmp.cleanup()
    def offline(self,c):raise FlowError('Doska HTTP 401')
    def online(self,c):return {'reachable':True}
    def consent(self,mode='offline'):
        result=submit(self.event,self.home,self.state,self.offline)
        self.assertEqual(result['decision'],'block')
        pending=self.state.get('pending-consent','session-1')
        e={**self.event,'turn_id':'turn-2','prompt':f'[doska:{mode}-once '+pending['challenge']+']\n'+self.event['prompt']}
        submit(e,self.home,self.state,self.offline)
        return pending['task_id'],e
    def test_bad_auth_blocks_and_no_implicit_timeout_consent(self):
        result=submit(self.event,self.home,self.state,self.offline)
        self.assertEqual(result['decision'],'block');self.assertIsNone(self.state.get('gate','session-1'))
        p=self.state.get('pending-consent','session-1')
        e={**self.event,'prompt':'[doska:offline-once '+p['challenge']+']\n'+self.event['prompt']}
        self.assertEqual(submit(e,self.home,self.state,self.offline,now=p['expires']+1)['decision'],'block')
    def test_nonce_cannot_approve_different_prompt_or_session(self):
        submit(self.event,self.home,self.state,self.offline)
        p=self.state.get('pending-consent','session-1')
        for changed in ({'prompt':'different work'},{'session_id':'other'}):
            e={**self.event,**changed};e['prompt']='[doska:offline-once '+p['challenge']+']\n'+e['prompt']
            self.assertEqual(submit(e,self.home,self.state,self.offline)['decision'],'block')
    def test_untracked_consent_bind_and_new_task_requires_new_choice(self):
        task,e=self.consent('untracked')
        begin(self.home,self.state,task,'session-1','turn-2')
        self.assertEqual(self.state.get('gate','session-1')['mode'],'untracked')
        self.assertEqual(self.state.events(),[])
        new={**self.event,'turn_id':'turn-3','prompt':'Implement another independent feature'}
        self.assertEqual(submit(new,self.home,self.state,self.offline)['decision'],'block')
        cont={**self.event,'turn_id':'turn-4','prompt':'[doska:task '+task+']\nExplain the test result'}
        self.assertNotIn('decision',submit(cont,self.home,self.state,self.offline))
        with self.assertRaises(FlowError):begin(self.home,self.state,'00000000-0000-4000-8000-000000000000','session-1','turn-4')
    def test_offline_capture_does_not_begin(self):
        task,e=self.consent()
        gate=self.state.get('gate','session-1')
        offline_capture(self.state,gate,{'task_id':task,'project':'fake','title':'Later','state':'Procrastinated'})
        self.assertFalse(self.state.get('gate','session-1')['bound'])
        self.assertEqual(len(self.state.events()),1)
        self.assertEqual(handle({'hook_event_name':'Stop','session_id':'session-1','turn_id':'turn-2'},self.home),{})
    def test_guard_refuses_compound_commands_and_unbound_tools(self):
        script=self.home/'skills/doska-workflow/scripts/doska_flow.py'
        good=f'python3 "{script}" doctor'
        self.assertTrue(safe_bridge_command(good,self.home))
        for raw in (good+'; touch /tmp/not-allowed',good+' && echo bad','echo '+good,'python3 -c "print(1)"',good+' $(echo bad)',good+'\nwhoami'):
            self.assertFalse(safe_bridge_command(raw,self.home))
        e={'hook_event_name':'PreToolUse','tool_name':'Bash','tool_input':{'command':'touch example'},'session_id':'session-1','turn_id':'turn-1'}
        self.assertEqual(handle(e,self.home)['hookSpecificOutput']['permissionDecision'],'deny')
        e['tool_input']['command']=good;self.assertEqual(handle(e,self.home),{})
    def test_stop_only_records_idle_and_bounded_outcome_reminder(self):
        task,e=self.consent('untracked');begin(self.home,self.state,task,'session-1','turn-2')
        stop={'hook_event_name':'Stop','session_id':'session-1','turn_id':'turn-2'}
        self.assertEqual(handle(stop,self.home)['decision'],'block')
        self.assertEqual(handle({**stop,'stop_hook_active':True},self.home),{})
        self.assertEqual(self.state.get('session','session-1')['activity'],'needs attention')
        record_outcome(self.state,'session-1','turn-2',task)
        self.assertEqual(handle(stop,self.home),{})
        self.assertEqual(handle({**stop,'hook_event_name':'Interrupt'},self.home),{})
        self.assertEqual(self.state.get('session','session-1')['activity'],'interrupted')
    def test_begin_online_requires_success_before_granting_work(self):
        submit(self.event,self.home,self.state,self.online)
        task='00000000-0000-4000-8000-000000000000'
        class Failed:
            def start(self,*args):raise FlowError('not writable')
        with self.assertRaises(FlowError):begin(self.home,self.state,task,'session-1','turn-1',Failed())
        self.assertFalse(self.state.get('gate','session-1')['bound'])
        class Working:
            def start(self,*args):return {}
        begin(self.home,self.state,task,'session-1','turn-1',Working())
        event={'hook_event_name':'PreToolUse','tool_name':'apply_patch','tool_input':{},'session_id':'session-1','turn_id':'turn-1'}
        self.assertEqual(handle(event,self.home,self.online),{})
        self.assertEqual(handle(event,self.home,self.offline)['hookSpecificOutput']['permissionDecision'],'deny')
    def test_hook_process_fails_closed_for_bad_input(self):
        script=Path(__file__).parents[1]/'scripts/doska_flow.py'
        result=subprocess.run([sys.executable,str(script),'--home',str(self.home),'hook'],input='not json',text=True,capture_output=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)['decision'],'block')
        self.assertNotIn('Traceback',result.stderr)
    def test_offline_cli_capture_finish_and_no_live_network(self):
        task,e=self.consent()
        script=Path(__file__).parents[1]/'scripts/doska_flow.py'
        def run(*args):
            r=subprocess.run([sys.executable,str(script),'--home',str(self.home),*args],text=True,capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr)
            return json.loads(r.stdout)
        captured=run('capture','Later','--session','session-1','--project','fake','--state','Procrastinated')
        self.assertEqual(captured['task_id'],task)
        self.assertFalse(self.state.get('gate','session-1')['bound'])
        run('begin',task,'--session','session-1','--turn','turn-2')
        run('finish',task,'--session','session-1','--state','Review','--summary','Ready')
        self.assertTrue(self.state.get('gate','session-1')['outcome'])
        self.assertEqual(len(self.state.events()),3)
    def test_generated_hook_runs_outside_skill_directory(self):
        source=Path(__file__).parents[1]/'scripts'
        target=self.home/'skills/doska-workflow/scripts'
        shutil.copytree(source,target)
        command=setup.template()['hooks']['SessionStart'][0]['hooks'][0]['command']
        env={**os.environ,'CODEX_HOME':str(self.home)}
        result=subprocess.run(shlex.split(command),input=json.dumps({'hook_event_name':'SessionStart','session_id':'fresh'}),text=True,capture_output=True,cwd=self.home,env=env)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['hookEventName'],'SessionStart')
    def test_setup_merge_idempotent_and_dry_helpers_no_activation(self):
        existing={'hooks':{'Stop':[{'hooks':[{'type':'command','command':'existing'}]}]},'other':'preserved'}
        original=copy.deepcopy(existing);proposed=setup.template()
        merged=setup.merge(existing,proposed)
        self.assertEqual(existing,original);self.assertEqual(setup.merge(merged,proposed),merged)
        self.assertEqual(merged['hooks']['Stop'][0]['hooks'][0]['command'],'existing')
        self.assertFalse((self.home/'hooks.json').exists())
        path=setup.apply(self.home,proposed)
        self.assertTrue(path.exists());self.assertEqual(json.loads(path.read_text())['hooks'],proposed['hooks'])
if __name__=='__main__':unittest.main()
