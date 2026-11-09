"""Explicit command interface. Help/import never creates files or contacts Doska."""
import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from .config import load_config, codex_home
from .model import FlowError, STATES, identifier
from .state import State
from .workflow import Workflow, project_key

def parser():
    p=argparse.ArgumentParser(description='Portable Doska task workflow')
    p.add_argument('--home',type=Path,help='Isolated Codex home; defaults to CODEX_HOME')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor',help='Read-only backend health; never creates boards or cards')
    capture=sub.add_parser('capture')
    capture.add_argument('title');capture.add_argument('--project');capture.add_argument('--body',default='')
    capture.add_argument('--state',choices=('To do','Procrastinated'),default='To do')
    capture.add_argument('--task-id');capture.add_argument('--session');capture.add_argument('--owner',default='')
    capture.add_argument('--participant',action='append',default=[]);capture.add_argument('--acceptance',default='');capture.add_argument('--reconsider-on')
    for op in ('start','update','finish','complete','info','links','open-task','delete','attach'):
        c=sub.add_parser(op);c.add_argument('task_id')
        if op in ('start','update','finish','complete','attach'):c.add_argument('--session',required=op=='start')
        if op in ('start','update'):c.add_argument('--takeover',action='store_true')
        if op in ('update','finish'):
            c.add_argument('--state',choices=STATES,required=op=='finish');c.add_argument('--summary',default=None if op=='update' else '')
            c.add_argument('--next-action');c.add_argument('--actor');c.add_argument('--verification');c.add_argument('--reconsider-on')
        if op=='update':c.add_argument('--activity',choices=('running','idle','interrupted','needs attention'))
        if op=='complete':c.add_argument('--accepted',action='store_true',help='Explicitly confirm task acceptance')
        if op=='delete':c.add_argument('--confirm',required=True,help='Repeat the task UUID to authorize deletion')
        if op=='attach':c.add_argument('--board',required=True)
        if op=='open-task':c.add_argument('--launch',action='store_true')
    c=sub.add_parser('open-chat');c.add_argument('session');c.add_argument('--launch',action='store_true')
    return p

def launch(uri):
    if sys.platform=='darwin':subprocess.run(['open',uri],check=True)
    elif sys.platform=='win32':os.startfile(uri)
    else:subprocess.run(['xdg-open',uri],check=True)

def dispatch(args, home):
    if args.command=='open-chat':
        from .model import chat_reference
        uri=chat_reference(args.session,'local')['uri']
        if args.launch:launch(uri)
        return {'uri':uri,'note':'Opens a local chat on its owning computer; does not sync chat history'}
    config=load_config(home)
    if args.command=='doctor':
        from .transport import Transport
        return Transport(config).connect()
    state=State(home/'doska-state')
    try:
        w=Workflow(config,state)
        op=args.command
        if op=='capture':return w.capture(project_key(Path.cwd(),args.project or config.project_key),args.title,args.body,args.state,args.session,task_id=args.task_id,owner=args.owner,participants=args.participant,acceptance=args.acceptance,reconsider_on=args.reconsider_on)
        if op=='start':return w.start(args.task_id,args.session,args.takeover)
        if op=='attach':return w.attach(args.task_id,args.board,args.session)
        if op=='update':return w.change(args.task_id,state=args.state,summary=args.summary,next_action=args.next_action,actor=args.actor,verification=args.verification,session=args.session,activity=args.activity,reconsider_on=args.reconsider_on,takeover=args.takeover)
        if op=='finish':return w.finish(args.task_id,args.state,args.summary,args.verification or '',args.next_action or '',args.actor or '',args.session)
        if op=='complete':return w.change(args.task_id,state='Done',explicit_done=args.accepted,session=args.session,activity='idle')
        if op=='info':return w.info(args.task_id)
        if op in ('links','open-task'):
            links=w.links(args.task_id)
            if op=='open-task' and args.launch:
                if not links['web_url']:raise FlowError('This local-only store has no web URL; use board/card IDs in Doska')
                launch(links['web_url'])
            return links
        if op=='delete':
            if identifier(args.confirm)!=identifier(args.task_id):raise FlowError('Deletion confirmation must match the exact task UUID')
            item=w.info(args.task_id);r=item['record']
            result=w.call('delete_card',{'boardId':r['board_id'],'cardId':r['card_id']})
            state.delete('task',args.task_id);return result
    finally:state.close()

def main(argv=None):
    args=parser().parse_args(argv)
    if args.command=='capture' and not args.task_id:args.task_id=str(uuid.uuid4())
    try:
        result=dispatch(args,args.home or codex_home())
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (FlowError,OSError,subprocess.SubprocessError) as exc:
        error={'error':str(exc)}
        if args.command=='capture':error['task_id']=args.task_id
        print(json.dumps(error),file=sys.stderr);return 2
