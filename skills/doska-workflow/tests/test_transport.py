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

class PersistentSSE(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    released=threading.Event()
    sent=threading.Event()
    def log_message(self,*a):pass
    def do_POST(self):
        p=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        self.wfile.write(('data: '+json.dumps({'jsonrpc':'2.0','id':p['id'],'result':{'ok':True}})+'\n\n').encode());self.wfile.flush()
        self.sent.set();self.released.wait(3)
        self.close_connection=True

class MoreTransportTests(unittest.TestCase):
    def test_persistent_sse_returns_before_server_closes(self):
        PersistentSSE.released.clear();PersistentSSE.sent.clear()
        server=ThreadingHTTPServer(('127.0.0.1',0),PersistentSSE)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        result=[]
        t=Transport(Config('local','test',endpoint=f'http://127.0.0.1:{server.server_port}/mcp',timeout=2))
        t.token='test'
        worker=threading.Thread(target=lambda:result.append(t.rpc('test')),daemon=True)
        try:
            worker.start();self.assertTrue(PersistentSSE.sent.wait(1));worker.join(0.5)
            self.assertFalse(worker.is_alive(),'Client waited for the persistent SSE connection to close')
            self.assertEqual(result,[{'ok':True}])
        finally:
            PersistentSSE.released.set();worker.join(3);server.shutdown();server.server_close();thread.join()

    def test_json_response_identifier_and_shape(self):
        import io
        class Response(io.BytesIO):
            headers={'Content-Type':'application/json'}
        class Opener:
            def __init__(self,payload):self.payload=payload
            def open(self,*a,**kw):return Response(json.dumps(self.payload).encode())
        for value in [{'jsonrpc':'2.0','id':99,'result':{}},{'jsonrpc':'2.0','id':1,'result':[]},[],{'jsonrpc':'2.0','id':True,'result':{}}]:
            t=Transport(Config('local','test',endpoint='http://127.0.0.1:3846/mcp'));t.opener=Opener(value)
            with self.assertRaises(FlowError):t.rpc('test')

class HeartbeatSSE(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        import time
        try:
            for _ in range(40):self.wfile.write(b': heartbeat\n\n');self.wfile.flush();time.sleep(0.02)
        except (BrokenPipeError,ConnectionResetError):pass

class DeadlineTests(unittest.TestCase):
    def test_heartbeat_stream_has_total_deadline(self):
        import time
        server=ThreadingHTTPServer(('127.0.0.1',0),HeartbeatSSE);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        t=Transport(Config('local','test',endpoint=f'http://127.0.0.1:{server.server_port}/mcp',timeout=0.12));t.token='test'
        try:
            start=time.monotonic()
            with self.assertRaises(FlowError):t.rpc('test')
            self.assertLess(time.monotonic()-start,0.5)
        finally:server.shutdown();server.server_close();thread.join()
    def test_reconnect_starts_new_session_and_malformed_tools_rejected(self):
        class TestTransport(Transport):
            def credentials(self):pass
            def rpc(self,method,params=None,notification=False):
                if method=='initialize':
                    self.initial_state=(self.session,self.initialized)
                    return {'protocolVersion':'2025-03-26'}
                if method=='tools/list':return {'tools':[None]}
        t=TestTransport(Config('local','test'));t.session='old';t.initialized=True
        with self.assertRaises(FlowError):t.connect()
        self.assertEqual(t.initial_state,(None,False))
