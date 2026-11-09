"""Read-only briefs from shared cards, with actual column state taking precedence."""
import time
from datetime import date
from .model import FlowError, metadata, iso_date
from .workflow import cards

def brief(workflow,today=None,now=None,stale_seconds=1800):
    today=iso_date(today) if today else date.today().isoformat()
    now=time.time() if now is None else now
    sections={k:[] for k in ('review','waiting','deadlines','reconsider','stale','to_do','unknown')}
    count=0
    for entry in workflow.call('list_boards',{}):
        board=workflow.call('get_board',{'boardId':entry['id']})
        registry=[m for _,c in cards(board) if (m:=metadata(c.get('body',''))) and m.get('kind')=='project' and m.get('workspace')==workflow.config.workspace]
        if not registry:continue
        if len(registry)!=1:raise FlowError('Ambiguous Project info cards; brief cannot establish the project')
        project=registry[0];column_states={v:k for k,v in project.get('columns',{}).items()}
        for column,card in cards(board):
            m=metadata(card.get('body',''))
            if not m or m.get('kind')!='task' or m.get('workspace')!=workflow.config.workspace or m.get('project')!=project.get('project'):continue
            count+=1
            state=column_states.get(column['id'],'Unknown')
            row={'task_id':m['task_id'],'title':card['title'],'project':m['project'],'board_id':entry['id'],'card_id':card['id'],
                 'state':state,'summary':m.get('summary',''),'next_action':m.get('next_action',''),'next_actor':m.get('next_actor',''),
                 'deadline':card.get('deadline'),'reconsider_on':m.get('reconsider_on'),'chats':m.get('chats',[])}
            row['web_url']=workflow.config.web_url.rstrip('/')+'/d/'+entry['id']+'/c/'+card['id'] if workflow.config.web_url else None
            if state=='Done':continue
            if state=='Review':sections['review'].append(row)
            if state=='Waiting':sections['waiting'].append(row)
            if state=='To do':sections['to_do'].append(row)
            if state=='Unknown':sections['unknown'].append(row)
            if row['deadline'] and iso_date(row['deadline'])<=today:sections['deadlines'].append(row)
            if state=='Procrastinated' and row['reconsider_on'] and iso_date(row['reconsider_on'])<=today:sections['reconsider'].append(row)
            fresh_local=False
            for chat in m.get('chats',[]):
                if chat.get('machine')!=workflow.state.get('machine','id'):continue
                local=workflow.state.get('session',chat.get('session_id'),{})
                if local.get('task_id')==m['task_id'] and local.get('activity')=='running' and now-local.get('last_activity',0)<=stale_seconds:
                    fresh_local=True
            if m.get('activity') in ('running','interrupted','needs attention') and not fresh_local and (not m.get('last_update') or now-m['last_update']>stale_seconds):
                row['activity_note']='Last shared activity update is old or unavailable; agent activity is unverified'
                sections['stale'].append(row)
    for rows in sections.values():rows.sort(key=lambda r:(r.get('deadline') or '9999',r['project'],r['title'],r['task_id']))
    suggestions=[];seen=set()
    for section in ('review','waiting','deadlines','to_do','reconsider'):
        for row in sections[section]:
            if row['task_id'] not in seen:
                seen.add(row['task_id']);suggestions.append({**row,'reason':section})
    return {'date':today,'workspace':workflow.config.workspace,'mode':workflow.config.mode,'sync_verified':workflow.config.sync_verified,'tasks':count,'sections':sections,
            'pending_updates':len(workflow.state.events()),'suggestions':suggestions[:3]}

def markdown(report):
    lines=[f"Morning brief — {report['date']}",f"Workspace: {report['workspace']} ({report['mode']}; sync {'configured as verified' if report['sync_verified'] else 'unverified'}). Pending tracking updates: {report['pending_updates']}."]
    names={'review':'Ready for review','waiting':'Waiting for action','deadlines':'Due or overdue','reconsider':'Procrastinated: reconsider','stale':'Activity needs checking','to_do':'Ready to start','unknown':'Unrecognized state'}
    for key,title in names.items():
        rows=report['sections'][key]
        if not rows:continue
        lines.extend(('',title))
        for row in rows:
            text=row['title'].replace('\n',' ')
            if row.get('web_url'):text=f"[{text}]({row['web_url']})"
            if key=='stale':text+=' — '+row['activity_note']
            lines.append(f"- {text} [{row['project']}] — {row['next_action'] or row['summary'] or row['state']} (task {row['task_id']}; board {row['board_id']}; card {row['card_id']})")
    lines.extend(('', 'Suggested priorities'))
    for row in report['suggestions']:lines.append(f"- {row['title']} — {row['reason']} (task {row['task_id']})")
    return '\n'.join(lines)+'\n'
