"""Stable identifiers and the deliberately small task metadata format."""
import json
import re
import uuid
from datetime import date

STATES = ('To do', 'Procrastinated', 'Doing', 'Waiting', 'Review', 'Done')
BEGIN = '<!-- doska-flow:v1 -->'
END = '<!-- /doska-flow -->'
SUMMARY_BEGIN = '[doska-flow-summary-start]: #'
SUMMARY_END = '[doska-flow-summary-end]: #'
REQUIRED_TOOLS = frozenset(('list_boards', 'get_board', 'get_card', 'create_board',
    'create_column', 'update_column', 'create_card', 'update_card', 'move_card'))

class FlowError(Exception):
    """An actionable tracking failure; never contains credentials."""

class Conflict(FlowError):
    """A human must resolve an ambiguous identity or concurrent change."""

def identifier(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise FlowError('Expected a task UUID') from None

def validate_state(value):
    if value not in STATES:
        raise FlowError('Unknown task state: ' + str(value))
    return value

def iso_date(value):
    if value is not None:
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except (ValueError, TypeError):
            raise FlowError('Use a date in YYYY-MM-DD form') from None
    return value

def metadata(body):
    if BEGIN not in body and END not in body:
        return None
    if body.count(BEGIN) != 1 or body.count(END) != 1:
        raise Conflict('Ambiguous integration metadata; refusing to rewrite the card')
    start = body.index(BEGIN) + len(BEGIN)
    finish = body.index(END)
    raw = body[start:finish].strip()
    if finish < start or not raw.startswith('```json\n') or not raw.endswith('\n```'):
        raise Conflict('Malformed integration metadata')
    try:
        result = json.loads(raw[8:-4])
    except (ValueError, TypeError):
        raise Conflict('Malformed integration metadata') from None
    if not isinstance(result, dict) or result.get('schema') != 1:
        raise Conflict('Unsupported integration metadata schema')
    return result

def _summary(value):
    # Reference definitions are invisible in rendered Markdown. Keeping the
    # preview cut inside this managed region prevents JSON from filling cards.
    def text(item):
        line=' '.join(str(item or '').split())
        return re.sub(r'([\\`*_{}\[\]<>#+.!|()~-])', r'\\\1', line)
    lines=[SUMMARY_BEGIN, '', '**State:** '+text(value.get('state'))+
           ' · **Owner:** '+text(value.get('owner') or 'Unassigned')+
           ' · **Agent:** '+text(value.get('activity') or 'idle')]
    if value.get('summary'):lines+=['', '**Latest:** '+text(value['summary'])]
    elif value.get('acceptance'):lines+=['', '**Outcome:** '+text(value['acceptance'])]
    if value.get('next_action'):
        actor=text(value.get('next_actor'))
        lines+=['', '**Next:** '+(actor+' — ' if actor else '')+text(value['next_action'])]
    lines+=['', '-cut-', '', SUMMARY_END]
    return '\n'.join(lines)

def with_metadata(body, value):
    metadata(body)  # Validate before replacing any existing block.
    if SUMMARY_BEGIN in body or SUMMARY_END in body:
        if body.count(SUMMARY_BEGIN)!=1 or body.count(SUMMARY_END)!=1 or body.index(SUMMARY_END)<body.index(SUMMARY_BEGIN):
            raise Conflict('Ambiguous generated summary; refusing to rewrite the card')
    block = BEGIN + '\n```json\n' + json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n```\n' + END
    if BEGIN in body:
        start, finish = body.index(BEGIN), body.index(END) + len(END)
        result=body[:start] + block + body[finish:]
    else:
        result=body + ('\n\n' if body else '') + block
    if value.get('kind')=='task':
        summary=_summary(value)
        if SUMMARY_BEGIN in result:
            start,finish=result.index(SUMMARY_BEGIN),result.index(SUMMARY_END)+len(SUMMARY_END)
            result=result[:start]+summary+result[finish:]
        else:result=summary+'\n\n'+result
    return result

def chat_reference(session, machine, title=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', session or ''):
        raise FlowError('Invalid chat session identifier')
    return {'client': 'codex', 'session_id': session, 'machine': machine,
            'title': title or session, 'uri': 'codex://threads/' + session}
