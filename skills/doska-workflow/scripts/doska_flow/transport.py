"""Small MCP Streamable HTTP client for Doska; no insecure remote fallbacks."""
import json
import os
from pathlib import Path
from urllib import request, error
from .config import local_settings_path
from .model import FlowError, REQUIRED_TOOLS

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Transport:
    def __init__(self, config):
        self.config = config
        self.endpoint = config.endpoint
        self.token = ''
        self.session = None
        self.counter = 0
        self.initialized = False
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())

    def credentials(self):
        c = self.config
        if c.mode == 'local':
            try:
                p = Path(c.settings_file).expanduser() if c.settings_file else local_settings_path()
                settings = json.loads(p.read_text())
                if not settings.get('enabled'): raise FlowError('Local Doska MCP is disabled')
                port = settings.get('port')
                if not isinstance(port, int) or not 1 <= port <= 65535: raise FlowError('Invalid local Doska port')
                self.endpoint = c.endpoint or f'http://127.0.0.1:{port}/mcp'
                self.token = settings['token']
            except (OSError, ValueError, KeyError, TypeError):
                raise FlowError('Local Doska MCP settings are unavailable or malformed') from None
        elif c.token_env:
            self.token = os.environ.get(c.token_env, '')
        elif c.token_file:
            try:
                p = Path(c.token_file).expanduser()
                if os.name != 'nt' and p.stat().st_mode & 0o077:
                    raise FlowError('Token file must be owner-only readable')
                self.token = p.read_text().strip()
            except OSError:
                raise FlowError('Remote token file is unavailable') from None
        if not isinstance(self.token, str) or not self.token or '\n' in self.token or '\r' in self.token:
            raise FlowError('Doska access token is missing or invalid')
        c.validate_url(self.endpoint)

    def rpc(self, method, params=None, notification=False):
        self.counter += 1
        data = {'jsonrpc':'2.0','method':method}
        if not notification: data['id'] = self.counter
        if params is not None: data['params'] = params
        headers = {'Content-Type':'application/json','Accept':'application/json, text/event-stream',
                   'Authorization':'Bearer '+self.token}
        if self.session: headers['Mcp-Session-Id'] = self.session
        if self.initialized: headers['MCP-Protocol-Version'] = '2025-03-26'
        req = request.Request(self.endpoint,data=json.dumps(data).encode(),headers=headers)
        try:
            with self.opener.open(req,timeout=self.config.timeout) as res:
                self.session = res.headers.get('Mcp-Session-Id', self.session)
                if notification:
                    return None
                if 'text/event-stream' in res.headers.get('Content-Type',''):
                    # A Streamable HTTP SSE response may remain open indefinitely.
                    # Finish as soon as the matching event arrives, not at EOF.
                    remaining = 2 * 1024 * 1024
                    parts = []
                    obj = None
                    while remaining > 0:
                        line = res.readline(remaining + 1)
                        remaining -= len(line)
                        if remaining < 0:
                            raise FlowError('Doska response exceeds the safety limit')
                        if not line:
                            break
                        line = line.decode().rstrip('\r\n')
                        if line.startswith('data:'):
                            parts.append(line[5:].lstrip())
                        elif not line and parts:
                            event = json.loads('\n'.join(parts))
                            parts = []
                            if isinstance(event, dict) and event.get('id') == data['id']:
                                obj = event
                                break
                    if obj is None:
                        raise FlowError('Doska did not return the requested response')
                else:
                    raw = res.read(2 * 1024 * 1024 + 1)
                    if len(raw) > 2 * 1024 * 1024:
                        raise FlowError('Doska response exceeds the safety limit')
                    obj = json.loads(raw)
                if (not isinstance(obj, dict) or obj.get('jsonrpc') != '2.0'
                        or isinstance(obj.get('id'), bool) or obj.get('id') != data['id']):
                    raise FlowError('Doska returned an invalid MCP response identifier')
                if obj.get('error'):
                    raise FlowError('Doska rejected MCP request ' + method)
                if not isinstance(obj.get('result'), dict):
                    raise FlowError('Doska returned an invalid MCP result')
                return obj['result']
        except error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise FlowError(f'Doska HTTP {code}; check authentication and endpoint') from None
        except (error.URLError, TimeoutError, OSError):
            raise FlowError('Doska is unreachable or timed out') from None
        except (ValueError, UnicodeError, TypeError):
            raise FlowError('Doska returned an invalid MCP response') from None

    def connect(self):
        self.credentials()
        result = self.rpc('initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'doska-workflow','version':'1.0'}})
        if result.get('protocolVersion') != '2025-03-26': raise FlowError('Unsupported MCP protocol version')
        self.initialized = True
        self.rpc('notifications/initialized',notification=True)
        names = {t['name'] for t in self.rpc('tools/list',{}).get('tools',[])}
        if REQUIRED_TOOLS - names: raise FlowError('Doska is missing required task tools: '+', '.join(sorted(REQUIRED_TOOLS-names)))
        self.call('list_boards', {})
        return {'reachable':True,'server':result.get('serverInfo',{}),'mode':self.config.mode,
                'workspace':self.config.workspace,'sync':'user-asserted' if self.config.sync_verified else 'unverified'}

    def call(self, tool, arguments):
        result = self.rpc('tools/call', {'name':tool,'arguments':arguments})
        if result.get('isError'): raise FlowError('Doska tool failed: '+tool)
        if 'structuredContent' in result: return result['structuredContent']
        text = '\n'.join(item.get('text','') for item in result.get('content',[]) if item.get('type')=='text')
        try: return json.loads(text)
        except ValueError: raise FlowError('Doska returned invalid tool content: '+tool) from None
