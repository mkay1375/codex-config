"""Small MCP Streamable HTTP client for Doska; no insecure remote fallbacks."""
import json
import os
import time
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
        deadline = time.monotonic() + self.config.timeout
        try:
            with self.opener.open(req,timeout=self.config.timeout) as res:
                self.session = res.headers.get('Mcp-Session-Id', self.session)
                if notification:
                    return None
                streaming = 'text/event-stream' in res.headers.get('Content-Type','')
                remaining = 2 * 1024 * 1024
                buffer = b''
                obj = None
                while remaining > 0:
                    budget = deadline - time.monotonic()
                    if budget <= 0:
                        raise FlowError('Doska response timed out')
                    socket = getattr(getattr(getattr(res, 'fp', None), 'raw', None), '_sock', None)
                    if socket is not None:
                        socket.settimeout(budget)
                    # read1 returns after at most one underlying read. readline/read
                    # can otherwise wait forever while a peer trickles a long line.
                    chunk = res.read1(min(65536, remaining + 1))
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise FlowError('Doska response exceeds the safety limit')
                    if not chunk:
                        break
                    buffer += chunk
                    if streaming:
                        buffer = buffer.replace(b'\r\n', b'\n')
                        while b'\n\n' in buffer:
                            event_bytes, buffer = buffer.split(b'\n\n', 1)
                            parts = [line[5:].lstrip() for line in event_bytes.split(b'\n') if line.startswith(b'data:')]
                            if not parts:
                                continue
                            event = json.loads(b'\n'.join(parts))
                            if isinstance(event, dict) and event.get('id') == data['id']:
                                obj = event
                                break
                        if obj is not None:
                            break
                if obj is None and streaming:
                    raise FlowError('Doska did not return the requested response')
                if not streaming:
                    if remaining <= 0:
                        raise FlowError('Doska response exceeds the safety limit')
                    obj = json.loads(buffer)
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
        self.session = None
        self.initialized = False
        self.credentials()
        result = self.rpc('initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'doska-workflow','version':'1.0'}})
        if result.get('protocolVersion') != '2025-03-26': raise FlowError('Unsupported MCP protocol version')
        self.initialized = True
        self.rpc('notifications/initialized',notification=True)
        tools = self.rpc('tools/list',{}).get('tools')
        if not isinstance(tools, list) or any(not isinstance(t, dict) or not isinstance(t.get('name'), str) for t in tools):
            raise FlowError('Doska returned an invalid tool list')
        names = {t['name'] for t in tools}
        if REQUIRED_TOOLS - names: raise FlowError('Doska is missing required task tools: '+', '.join(sorted(REQUIRED_TOOLS-names)))
        self.call('list_boards', {})
        return {'reachable':True,'server':result.get('serverInfo',{}),'mode':self.config.mode,
                'workspace':self.config.workspace,'sync':'user-asserted' if self.config.sync_verified else 'unverified'}

    def call(self, tool, arguments):
        result = self.rpc('tools/call', {'name':tool,'arguments':arguments})
        if result.get('isError'): raise FlowError('Doska tool failed: '+tool)
        if 'structuredContent' in result: return result['structuredContent']
        content = result.get('content')
        if not isinstance(content, list) or any(not isinstance(item, dict) or (item.get('type') == 'text' and not isinstance(item.get('text'), str)) for item in content):
            raise FlowError('Doska returned invalid tool content: ' + tool)
        text = '\n'.join(item['text'] for item in content if item.get('type')=='text')
        try: return json.loads(text)
        except ValueError: raise FlowError('Doska returned invalid tool content: '+tool) from None
