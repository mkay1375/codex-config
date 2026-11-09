import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from doska_flow.config import Config
from doska_flow.transport import Transport
from doska_flow.state import State
from doska_flow.model import FlowError, REQUIRED_TOOLS

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        if self.headers.get('Authorization') != 'Bearer test-secret':
            self.send_response(401);self.end_headers();return
        p=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if p['method'].startswith('notifications/'):
            self.send_response(202);self.end_headers();return
        if p['method']=='initialize': result={'protocolVersion':'2025-03-26','serverInfo':{'name':'doska','version':'fake'}}
        elif p['method']=='tools/list':result={'tools':[{'name':n} for n in REQUIRED_TOOLS]}
        else:result={'content':[{'type':'text','text':'[]'}]}
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Mcp-Session-Id','test-session');self.end_headers()
        self.wfile.write(('event: message\ndata: '+json.dumps({'jsonrpc':'2.0','id':p['id'],'result':result})+'\n\n').encode())

class TransportTests(unittest.TestCase):
    def test_local_handshake_and_state_permissions(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                settings=Path(d)/'settings.json'; settings.write_text(json.dumps({'enabled':True,'port':server.server_port,'token':'test-secret'}))
                t=Transport(Config('local','test',settings_file=str(settings)))
                self.assertTrue(t.connect()['reachable']);self.assertEqual(t.session,'test-session')
                settings.write_text(json.dumps({'enabled':True,'port':server.server_port,'token':'bad'}))
                with self.assertRaises(FlowError):t.connect()
                state=State(Path(d)/'state');state.set('session','s',{'task':'x'})
                self.assertEqual(state.get('session','s')['task'],'x')
                first=state.machine();self.assertEqual(first,state.machine())
                state.enqueue('x',{'operation':'capture'},'event');state.enqueue('x',{},'event')
                self.assertEqual(len(state.events()),1)
                if os.name!='nt':self.assertEqual(state.path.stat().st_mode&0o777,0o600)
                state.close()
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
