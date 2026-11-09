"""Explicit outbox recovery. Queued work is bound to a backend, never silently retargeted."""
import json
from pathlib import Path
from .config import load_config, local_settings_path
from .model import FlowError, Conflict, metadata, identifier
from .workflow import Workflow, digest

def origin_from_config(config):
    endpoint=config.endpoint
    if config.mode=='local' and not endpoint:
        try:
            settings=json.loads((Path(config.settings_file).expanduser() if config.settings_file else local_settings_path()).read_text())
            port=settings.get('port')
            if not isinstance(port,int) or not 1<=port<=65535:return None
            endpoint=f'http://127.0.0.1:{port}/mcp'
        except (OSError,ValueError,TypeError):return None
    config.validate_url(endpoint)
    return {'workspace':config.workspace,'mode':config.mode,'endpoint':endpoint}

def queue_operation(state,gate,task_id,payload,event_id=None):
    """Keep the original endpoint and baseline even while the profile is broken."""
    identifier(task_id)
    record=state.get('task',task_id)
    pending=[e for e in state.events() if e['task']==task_id]
    baseline=None
    if record:
        baseline={key:record[key] for key in ('metadata_hash','column_id','board_id','card_id')}
    envelope={**payload,'origin':gate.get('origin'),'baseline':baseline,
              'parent_event':pending[-1]['id'] if pending else None}
    return state.enqueue(task_id,envelope,event_id)

def bind_unassigned(state,config,task_id,confirm,project=None):
    if identifier(confirm)!=identifier(task_id):raise FlowError('Binding confirmation must match the task UUID')
    origin=origin_from_config(config)
    if origin is None:raise FlowError('Cannot identify the configured backend')
    events=[e for e in state.events() if e['task']==task_id]
    if not events:raise FlowError('No pending events for this task')
    if any(e['payload'].get('origin') is not None for e in events):raise FlowError('Assigned events cannot be retargeted; restore their original backend')
    if not any(e['payload'].get('operation')=='capture' for e in events):raise FlowError('Only a new, unassigned capture can be bound to another backend')
    updates=[]
    for e in events:
        p=e['payload'];p['origin']=origin
        if p.get('operation')=='capture':
            if project:p['request']['project']=project
            if p['request'].get('project') in (None,'','unresolved-project'):raise FlowError('Supply --project to resolve the original project identity')
        updates.append((e['id'],p))
    with state.operation_lock(),state.db:
        for event_id,p in updates:
            if p.get('operation')=='capture':
                state.db.execute('INSERT INTO kv VALUES (?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value',('intent',task_id,json.dumps(p['request'])))
            state.db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(p),event_id))
    return {'task_id':task_id,'bound_to':origin,'events':len(events)}

def replay(state,config=None,apply=False,workflow=None):
    current=origin_from_config(config) if config else None
    events=state.events()
    result={'apply':apply,'pending':len(events),'events':[]}
    if not apply:
        for e in events:
            p=e['payload'];origin=p.get('origin')
            status='unassigned' if origin is None else 'ready' if origin==current else 'different backend'
            result['events'].append({'id':e['id'],'task_id':e['task'],'operation':p.get('operation'),'status':status,'origin':origin})
        return result
    if config is None or current is None:raise FlowError('Configure an identifiable backend before replay')
    w=workflow or Workflow(config,state)
    with state.operation_lock():
        for e in events:
            p=e['payload'];task=e['task'];op=p.get('operation');request=dict(p.get('request',{}))
            try:
                if p.get('origin') is None:raise Conflict('Unassigned event; explicitly bind this task before replay')
                if p['origin']!=current:raise Conflict('Queued event belongs to another backend; restore its original profile')
                if op not in ('capture','change'):raise Conflict('Unsupported or destructive operation is never replayed')
                if request.get('task_id')!=task:raise Conflict('Queued task identity does not match its event')
                if request.get('state')=='Done' or request.get('explicit_done'):raise Conflict('Done is never replayed automatically')
                if op=='capture':
                    r=w.capture(**request)
                    if r['metadata']['state']!=request.get('state','To do'):raise Conflict('Captured task has since moved; inspect before replaying dependent changes')
                else:
                    item=w.info(task);record=item['record'];actual=item['metadata'];column=item['column']['id']
                    if e['id'] in actual.get('applied_events',[]):
                        # The remote write succeeded before local acknowledgement. Do
                        # not repeat it or invent an expected baseline for its children.
                        state.event_status(e['id'],'applied')
                        result['events'].append({'id':e['id'],'status':'already applied; inspect before dependent replay'})
                        continue
                    parent=p.get('parent_event')
                    if parent:
                        expected=state.get('event-ack',parent)
                        if not expected:raise Conflict('Previous event lacks a confirmed baseline; inspect pending work')
                    else:expected=p.get('baseline')
                    if not expected:raise Conflict('Existing task has no offline baseline; inspect and register it first')
                    if expected['metadata_hash']!=digest(actual) or expected['column_id']!=column:
                        raise Conflict('Task changed after the queued baseline; no update was replayed')
                    # Re-adopt this verified baseline, not an arbitrary remote edit.
                    board={'id':record['board_id'],'project':record['project'],'columns':record['columns']}
                    w._save(task,board,item['card'],actual,column)
                    r=w.change(**request,event_id=e['id'])
                state.set('event-ack',e['id'],{key:r[key] for key in ('metadata_hash','column_id','board_id','card_id')})
                state.event_status(e['id'],'applied')
                result['events'].append({'id':e['id'],'status':'applied'})
            except (FlowError,OSError) as exc:
                result['events'].append({'id':e['id'],'status':'blocked','reason':str(exc)})
                result['blocked']=True
                break
    result['remaining']=len(state.events())
    return result
