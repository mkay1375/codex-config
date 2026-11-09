"""Synchronous, fail-closed tracking gates. Never interpret assistant prose."""
import hashlib
import json
import re
import shlex
import sys
import time
import uuid
import subprocess
from pathlib import Path
from .config import load_config
from .model import FlowError, identifier
from .state import State
from .transport import Transport
from .recovery import origin_from_config, queue_operation

CONTROL = re.compile(r'^\[doska:(offline-once|untracked-once) ([a-f0-9]{24})\]\r?\n')
TASK = re.compile(r'^\[doska:task ([a-f0-9-]{36})\]\r?\n')
TTL = 600

def fingerprint(prompt):
    return hashlib.sha256(prompt.encode()).hexdigest()

def context(message):
    return {'hookSpecificOutput': {'hookEventName':'UserPromptSubmit','additionalContext':message}}

def block(message):
    return {'decision':'block','reason':message}

def task_prompt(prompt):
    match=TASK.match(prompt)
    return (identifier(match[1]),prompt[match.end():]) if match else (None,prompt)

def safe_bridge_command(raw, home):
    """Only a single direct CLI invocation, never wrappers/substitutions/chains."""
    if not isinstance(raw,str) or any(c in raw for c in ('\n','\r','`','$',';','|','&','>','<')):
        return False
    try: parts=shlex.split(raw, posix=True)
    except ValueError:return False
    if len(parts)<3 or Path(parts[0]).name.lower() not in ('python','python3','python.exe','python3.exe'):
        return False
    expected=(Path(home)/'skills/doska-workflow/scripts/doska_flow.py').resolve()
    if Path(parts[1]).expanduser().resolve()!=expected:return False
    args=parts[2:]
    if args[:1]==['--home']:
        if len(args)<3 or Path(args[1]).expanduser().resolve()!=Path(home).resolve():return False
        args=args[2:]
    return bool(args) and args[0] in ('doctor','capture','begin','start','update','finish','complete','info','links','attach','brief','replay','bind')

def bounded_probe(home, timeout=3):
    """Bound all doctor RPCs/DNS together below the synchronous hook timeout."""
    entry=Path(__file__).resolve().parents[1]/'doska_flow.py'
    try:
        result=subprocess.run([sys.executable,str(entry),'--home',str(home),'doctor'],
                              capture_output=True,text=True,timeout=timeout)
        if result.returncode:raise FlowError('Doska health check failed; run doctor for details')
        value=json.loads(result.stdout)
        if not isinstance(value,dict) or not value.get('reachable'):raise FlowError('Doska health check did not confirm availability')
        return value
    except (subprocess.TimeoutExpired,OSError,ValueError):
        raise FlowError('Doska health check timed out or could not run') from None

def submit(event,home,state,probe=None,now=None):
    now=time.time() if now is None else now
    session,turn=event.get('session_id'),event.get('turn_id')
    prompt=event.get('prompt')
    if not session or not turn or not isinstance(prompt,str):return block('Doska preflight requires session_id, turn_id and prompt; this client is unsupported.')
    previous=state.get('gate',session)
    if previous and previous.get('turn_id')==turn:return previous['reply']
    control=CONTROL.match(prompt)
    if control:
        prompt=prompt[control.end():]
    task_id,normalized=task_prompt(prompt)
    pending=state.get('pending-consent',session)
    mode='online'
    origin=None
    if control:
        if not pending or pending['challenge']!=control[2] or now>pending['expires'] or pending['fingerprint']!=fingerprint(prompt):
            return block('Doska continuation consent is invalid, expired or for a different task. Retry the original request to obtain a new decision.')
        mode='offline' if control[1]=='offline-once' else 'untracked'
        task_id=pending['task_id']
        origin=pending.get('origin')
        state.delete('pending-consent',session)
        state.set('task-consent',session+':'+task_id,{'mode':mode,'origin':origin})
    elif task_id:
        consent=state.get('task-consent',session+':'+task_id)
        if consent:
            mode=consent['mode'];origin=consent.get('origin')
    health=None
    if mode=='online':
        try:
            config=load_config(home)
            origin=origin_from_config(config)
            health=probe(config) if probe else bounded_probe(home)
        except (FlowError,OSError) as exc:
            pending={'challenge':uuid.uuid4().hex[:24],'fingerprint':fingerprint(prompt),'expires':now+TTL,'task_id':task_id or str(uuid.uuid4()),'origin':origin}
            state.set('pending-consent',session,pending)
            reply=block('Doska is unavailable: '+str(exc)+'. No task work has started. Fix it and resubmit, or resubmit the SAME request with one first line: [doska:offline-once '+pending['challenge']+'] to queue tracking locally, or [doska:untracked-once '+pending['challenge']+'] to do this task without tracking. This choice expires in ten minutes; silence never permits work.')
            # Do not cache rejected turns: a retry can legitimately re-run preflight.
            return reply
    gate={'turn_id':turn,'mode':mode,'task_id':task_id,'bound':False,'created':now,'health':health,'origin':origin}
    message=('Use $doska-workflow. Tracking mode: '+mode+'. Session '+session+', turn '+turn+'. '
             +'Before task work, call begin with the task UUID and these session/turn IDs. Capture-only requests do not start work. '
             +'Use an existing task only for an actual continuation; capture independent outcomes separately. '
             +'Record a structured finish outcome before the final response. Do not interpret turn completion as task completion.')
    if origin:message+=' Backend: '+origin['mode']+', workspace '+origin['workspace']+'. Sync verification: '+('configured as verified' if health and health.get('sync')=='user-asserted' else 'unverified; availability does not confirm device synchronization')+'.'
    if task_id:message+=' Required task UUID for this request: '+task_id+'.'
    reply=context(message);gate['reply']=reply;state.set('gate',session,gate)
    return reply

def begin(home,state,task_id,session,turn,workflow=None):
    task_id=identifier(task_id)
    gate=state.get('gate',session)
    if not gate or gate['turn_id']!=turn:raise FlowError('No preflight for this session and turn; resubmit the task')
    if gate.get('task_id') and gate['task_id']!=task_id:raise FlowError('This request is authorized for a different task; start a new task request')
    if gate['mode']=='online':
        if workflow is None:
            from .workflow import Workflow
            workflow=Workflow(load_config(home),state)
        workflow.start(task_id,session)
    elif gate['mode']=='offline':
        if not state.get('task',task_id) and not state.get('intent',task_id):raise FlowError('Capture the offline task before beginning')
        queue_operation(state,gate,task_id,{'operation':'change','request':{'task_id':task_id,'state':'Doing','session':session,'activity':'running'}})
    gate.update(task_id=task_id,bound=True)
    state.set('gate',session,gate)
    state.set('session',session,{'task_id':task_id,'activity':'running','turn_id':turn,'mode':gate['mode']})
    return {'task_id':task_id,'mode':gate['mode'],'activity':'running'}

def record_outcome(state,session,turn,task_id):
    gate=state.get('gate',session)
    if gate and gate['turn_id']==turn and gate.get('task_id')==task_id:
        gate['outcome']=True;state.set('gate',session,gate)

def offline_capture(state,gate,request):
    task_id=gate.get('task_id') or request['task_id']
    if request.get('task_id') not in (None,task_id):raise FlowError('Offline consent belongs to a different task UUID')
    request={'body':'','state':'To do','session':None,'owner':'','participants':[],'acceptance':'','reconsider_on':None,**request,
             'task_id':task_id,'machine':request.get('machine') or state.machine()}
    request['participants']=request.get('participants') or []
    if gate['mode']=='offline':
        existing=state.get('intent',task_id)
        if existing and existing!=request:raise FlowError('Offline task UUID belongs to another capture request')
        state.set('intent',task_id,request)
        queue_operation(state,gate,task_id,{'operation':'capture','request':request},'capture:'+task_id)
    return {'task_id':task_id,'mode':gate['mode'],'state':request['state'],'queued':gate['mode']=='offline'}

def handle(event,home,probe=None):
    state=State(Path(home)/'doska-state')
    try:
        name=event.get('hook_event_name')
        session,turn=event.get('session_id'),event.get('turn_id')
        if name=='UserPromptSubmit':return submit(event,home,state,probe)
        if name=='SessionStart':
            return {'hookSpecificOutput':{'hookEventName':name,'additionalContext':'Doska tracking is installed. Use $doska-workflow after successful preflight. Existing task: '+json.dumps(state.get('session',session,{}))}}
        gate=state.get('gate',session)
        if name=='PreToolUse':
            tool=event.get('tool_name','')
            args=event.get('tool_input',{})
            if tool in ('Bash','exec_command') and isinstance(args,dict) and safe_bridge_command(args.get('command',args.get('cmd')),home):return {}
            if not gate or gate.get('turn_id')!=turn or not gate.get('bound'):
                return {'hookSpecificOutput':{'hookEventName':name,'permissionDecision':'deny','permissionDecisionReason':'Doska: register/begin this task after preflight before using work tools. Tracking commands must be a single direct bridge invocation.'}}
            if gate['mode']=='online':
                try:
                    config=load_config(home)
                    if origin_from_config(config)!=gate.get('origin'):raise FlowError('Tracking backend changed')
                    if probe:probe(config)
                    else:bounded_probe(home)
                except (FlowError,OSError):
                    gate['bound']=False;state.set('gate',session,gate)
                    return {'hookSpecificOutput':{'hookEventName':name,'permissionDecision':'deny','permissionDecisionReason':'Doska became unavailable. Pause work and ask the user to resubmit with a new preflight/continuation choice.'}}
            return {}
        if name in ('PostToolUse','Stop','Interrupt','SessionEnd'):
            record=state.get('session',session)
            if record:
                record['last_activity']=time.time()
                if name in ('Stop','Interrupt','SessionEnd'):record['activity']='interrupted' if name=='Interrupt' else 'idle'
                state.set('session',session,record)
            if name=='Stop' and gate and gate.get('turn_id')==turn and gate.get('bound') and not gate.get('outcome'):
                if not event.get('stop_hook_active'):return block('Record a structured Doska finish outcome for this task before ending. If tracking failed, report that and preserve the task state.')
                if record:record['activity']='needs attention';state.set('session',session,record)
            return {}
        return {}
    finally:state.close()

def main(home):
    try:
        event=json.load(sys.stdin)
        if not isinstance(event,dict):raise FlowError('Hook input must be an object')
        output=handle(event,Path(home))
        print(json.dumps(output));return 0
    except Exception:
        # No tracebacks, prompt text, server responses, or credentials in hook output.
        print(json.dumps(block('Doska tracking hook failed. No work is authorized; repair tracking and resubmit.')))
        return 2
