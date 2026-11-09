"""Task operations over Doska's public MCP tools. No dependency on chat transcripts."""
import hashlib
import json
import re
import subprocess
import time
import uuid
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlsplit
from .model import (FlowError, Conflict, STATES, metadata, with_metadata,
                    validate_state, identifier, iso_date, chat_reference, BEGIN, END)
from .transport import Transport

ALIASES = {'To do': ('to do','to-do','todo'), 'Doing': ('doing','in progress'),
           'Procrastinated': ('procrastinated',), 'Waiting': ('waiting',),
           'Review': ('review','wait for review'), 'Done': ('done',)}

def normalize_remote(remote):
    remote = remote.strip()
    if '://' in remote:
        u = urlsplit(remote)
        host, path = u.hostname, u.path
    else:
        match = re.fullmatch(r'(?:[^/@:]+@)?([^/:]+):(.+)',remote)
        if not match: raise FlowError('Use an explicit project key for local-path Git remotes')
        host,path = match.groups()
    if not host: raise FlowError('Git remote has no hostname')
    path = path.strip('/').removesuffix('.git')
    if not path: raise FlowError('Git remote has no repository path')
    if host.lower()=='github.com': path=path.lower()
    return host.lower()+'/'+path

def project_key(cwd, explicit=''):
    if explicit: return explicit
    try:
        res=subprocess.run(['git','-C',str(cwd),'remote','get-url','origin'],capture_output=True,text=True,timeout=3)
        if res.returncode: raise FlowError('Set project_key or --project for a project without an origin remote')
        return normalize_remote(res.stdout)
    except (OSError,subprocess.TimeoutExpired): raise FlowError('Cannot identify project; supply --project') from None

def cards(board):
    return [(col, card) for col in board['columns'] for card in col.get('cards',[])]

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def serialized(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        with self.state.operation_lock():
            return method(self, *args, **kwargs)
    return run

class Workflow:
    def __init__(self, config, state, transport=None):
        self.config,self.state=config,state
        self.transport=transport or Transport(config)
        self.ready=False

    def health(self):
        result=self.transport.connect();self.ready=True;return result

    def call(self, tool, args):
        if not self.ready: self.health()
        return self.transport.call(tool,args)

    @serialized
    def board(self, project):
        """Discover by stable marker, not by a machine-local path or a mutable title."""
        key=self.config.workspace+'\n'+project
        suffix='[flow:'+hashlib.sha256(key.encode()).hexdigest()[:16]+']'
        matches=[]
        for entry in self.call('list_boards',{}):
            board=self.call('get_board',{'boardId':entry['id']})
            markers=[(card,metadata(card.get('body',''))) for _,card in cards(board) if '<!-- doska-flow:v1 -->' in card.get('body','')]
            project_cards=[(card,m) for card,m in markers if m and m.get('kind')=='project' and m.get('project')==project and m.get('workspace')==self.config.workspace]
            if len(project_cards)>1: raise Conflict('Multiple Project info cards match this project')
            if project_cards or entry.get('title','').endswith(suffix):
                matches.append((board,project_cards[0] if project_cards else None))
        if len(matches)>1: raise Conflict('Duplicate project boards; choose a canonical board before continuing')
        if matches: board,project_info=matches[0]
        else:
            result=self.call('create_board',{'title':project.rsplit('/',1)[-1]+' '+suffix})
            board=self.call('get_board',{'boardId':result['board']['id']});project_info=None
        board_id=board['boardId']
        known=project_info[1].get('columns',{}) if project_info else {}
        mapping={}
        for state in STATES:
            found=[c for c in board['columns'] if c['id']==known.get(state)] if known.get(state) else [c for c in board['columns'] if c['title'].casefold() in ALIASES[state]]
            if len(found)>1: raise Conflict('Ambiguous columns for '+state)
            if found:
                col=found[0]
                patch={'boardId':board_id,'columnId':col['id']}
                if not known.get(state) and col['title']!=state: patch['title']=state
                if bool(col.get('done'))!=(state=='Done'):patch['done']=state=='Done'
                if len(patch)>2:self.call('update_column',patch)
            else:col=self.call('create_column',{'boardId':board_id,'title':state,'done':state=='Done'})
            mapping[state]=col['id']
        data={'schema':1,'kind':'project','project':project,'workspace':self.config.workspace,'columns':mapping}
        if project_info:
            card,old=project_info
            if old!=data:self.call('update_card',{'boardId':board_id,'cardId':card['id'],'body':with_metadata(card.get('body',''),data)})
        else:self.call('create_card',{'boardId':board_id,'columnId':mapping['To do'],'title':'Project info','body':with_metadata('Project identity and workflow columns. Keep this card when renaming the board.',data)})
        return {'id':board_id,'columns':mapping,'project':project,'workspace':self.config.workspace}

    def _find(self, board_id, task_id):
        matches=[]
        board=self.call('get_board',{'boardId':board_id})
        for col,card in cards(board):
            m=metadata(card.get('body',''))
            if m and m.get('kind')=='task' and m.get('task_id')==task_id:
                matches.append((card,col,m))
        if len(matches)>1:raise Conflict('Duplicate task UUID; select a canonical card')
        return matches[0] if matches else None

    def _save(self, task_id, board, card, meta, column):
        record={'task_id':task_id,'board_id':board['id'],'card_id':card['id'],'project':board['project'],
                'workspace':self.config.workspace,'columns':board['columns'],'metadata_hash':digest(meta),'column_id':column,
                'metadata':meta,'title':card.get('title',''),'updated_at':time.time()}
        self.state.set('task',task_id,record)
        return record

    @serialized
    def capture(self, project, title, body='', state='To do', session=None, machine=None,
                task_id=None, owner='', participants=None, acceptance='', reconsider_on=None):
        validate_state(state)
        if state not in ('To do','Procrastinated'):raise FlowError('Capture into To do or Procrastinated; use start to begin work')
        if not title.strip():raise FlowError('Task title must not be empty')
        task_id=identifier(task_id) if task_id else str(uuid.uuid4())
        # Persist intent before network writes so a timeout can be retried with the same UUID.
        intent=self.state.get('intent',task_id)
        request={'project':project,'title':title,'body':body,'state':state,'task_id':task_id,
                 'session':session,'machine':machine,'owner':owner,'participants':participants or [],
                 'acceptance':acceptance,'reconsider_on':iso_date(reconsider_on)}
        if intent and intent!=request:raise Conflict('Task UUID already belongs to a different capture request')
        self.state.set('intent',task_id,request)
        board=self.board(project)
        found=self._find(board['id'],task_id)
        if found:
            card,col,meta=found
            if meta.get('workspace')!=self.config.workspace or meta.get('project')!=project:raise Conflict('Task identity belongs to a different workspace')
            return self._save(task_id,board,card,meta,col['id'])
        meta={'schema':1,'kind':'task','task_id':task_id,'workspace':self.config.workspace,'project':project,
              'state':state,'activity':'idle','owner':owner,'participants':participants or [],'acceptance':acceptance,
              'reconsider_on':reconsider_on,'summary':'','next_action':'','next_actor':owner,
              'chats':[],'applied_events':[]}
        if session:meta['chats']=[chat_reference(session,machine or self.state.machine())]
        card=self.call('create_card',{'boardId':board['id'],'columnId':board['columns'][state],
                                     'title':title,'body':with_metadata(body,meta)})
        return self._save(task_id,board,card,meta,board['columns'][state])

    def info(self, task_id):
        task_id=identifier(task_id)
        record=self.state.get('task',task_id)
        if not record or record.get('workspace')!=self.config.workspace:raise FlowError('Task is not registered in this workspace; use attach with its board ID')
        found=self._find(record['board_id'],task_id)
        if not found:raise Conflict('Task card was deleted or is unavailable; not recreating it')
        card,col,meta=found
        return {'record':record,'card':card,'column':col,'metadata':meta}

    @serialized
    def attach(self, task_id, board_id, session=None):
        task_id=identifier(task_id)
        found=self._find(board_id,task_id)
        if not found:raise FlowError('Task UUID was not found on that board')
        card,col,meta=found
        if meta.get('workspace')!=self.config.workspace:raise Conflict('Task belongs to a different workspace')
        board=self.board(meta['project'])
        if board['id']!=board_id:raise Conflict('Board is not canonical for this project')
        record=self._save(task_id,board,card,meta,col['id'])
        if session:self.state.set('session',session,{'task_id':task_id,'activity':'idle'})
        return record

    @serialized
    def change(self, task_id, state=None, summary=None, next_action=None, actor=None, verification=None,
               session=None, explicit_done=False, activity=None, reconsider_on=None, event_id=None, takeover=False, title=None, body=None, owner=None,
               participants=None, acceptance=None, deadline=None, priority=None):
        if state is not None:validate_state(state)
        if title is not None and not title.strip():raise FlowError('Task title must not be empty')
        if body is not None and (BEGIN in body or END in body):raise FlowError('User notes cannot contain integration metadata markers')
        if deadline is not None:iso_date(deadline)
        if priority not in (None,'high','medium','low',''):raise FlowError('Unknown task priority')
        if state=='Done' and not explicit_done:raise FlowError('Done requires explicit acceptance')
        if state=='Waiting' and (not next_action or not actor):raise FlowError('Waiting requires next_action and actor')
        if activity not in (None,'running','idle','interrupted','needs attention'):raise FlowError('Invalid agent activity')
        item=self.info(task_id);record=item['record'];card=item['card'];meta=item['metadata'];col=item['column']
        if event_id and event_id in meta.get('applied_events',[]):return record
        if record['metadata_hash']!=digest(meta):raise Conflict('Task metadata changed since the last read; inspect and attach before updating')
        target=record['columns'][state] if state else col['id']
        if col['id']!=record['column_id'] and (state is None or col['id']!=target):raise Conflict('Task was manually moved; inspect and attach before updating')
        active=meta.get('active_chat')
        if meta.get('activity')=='running' and active and active!=session and not takeover:raise Conflict('Another chat is running this task; explicit takeover required')
        updates={'state':state,'summary':summary,'next_action':next_action,'next_actor':actor,
                 'verification':verification,'activity':activity,'reconsider_on':iso_date(reconsider_on) if reconsider_on else None,
                 'owner':owner,'participants':participants,'acceptance':acceptance}
        meta={**meta,**{k:v for k,v in updates.items() if v is not None},'last_update':time.time()}
        if session:
            ref=chat_reference(session,self.state.machine())
            meta['chats']=[c for c in meta.get('chats',[]) if c.get('session_id')!=session]+[ref]
            meta['active_chat']=session
        if event_id:meta['applied_events']=(meta.get('applied_events',[])+[event_id])[-100:]
        if target!=col['id']:self.call('move_card',{'boardId':record['board_id'],'cardId':card['id'],'columnId':target})
        next_body=with_metadata(card.get('body','') if body is None else body,meta)
        patch={'boardId':record['board_id'],'cardId':card['id'],'body':next_body}
        if title is not None:patch['title']=title
        if deadline is not None:patch['deadline']=deadline
        if priority is not None:patch['priority']=priority or None
        updated=self.call('update_card',patch)
        board={'id':record['board_id'],'project':record['project'],'columns':record['columns']}
        return self._save(task_id,board,updated,meta,target)

    @serialized
    def start(self, task_id, session, takeover=False):
        result=self.change(task_id,state='Doing',session=session,activity='running',takeover=takeover)
        self.state.set('session',session,{'task_id':task_id,'activity':'running'})
        return result

    def finish(self, task_id, state, summary, verification='', next_action='', actor='', session=None):
        if state not in ('Review','Waiting','Doing','Procrastinated'):raise FlowError('Finish records an outcome; mark Done separately with explicit acceptance')
        return self.change(task_id,state,summary,next_action,actor,verification,session,activity='idle')

    def links(self, task_id):
        record=self.state.get('task',identifier(task_id))
        if not record:raise FlowError('Unknown task UUID')
        return {'task_id':task_id,'web_url':self.config.web_url.rstrip('/')+'/d/'+quote(record['board_id'],safe='')+'/c/'+quote(record['card_id'],safe='') if self.config.web_url else None,
                'chats':record.get('metadata',{}).get('chats',[])}
