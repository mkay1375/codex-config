"""A real child doctor must finish within the hook's total availability budget."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from test_transport import Handler
from doska_flow.hooks import bounded_probe
from doska_flow.model import FlowError

class SlowHandler(Handler):
    def do_POST(self):
        time.sleep(0.9)
        try:super().do_POST()
        except (BrokenPipeError,ConnectionResetError):pass

class BudgetTests(unittest.TestCase):
    def test_multiple_slow_rpcs_cannot_overrun_hook_budget(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),SlowHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                home=Path(d)
                settings=home/'fake-settings.json'
                settings.write_text(json.dumps({'enabled':True,'port':server.server_port,'token':'test-secret'}))
                (home/'doska.local.toml').write_text('mode = "local"\nworkspace = "test"\nsettings_file = '+json.dumps(str(settings))+'\ntimeout = 10\n')
                start=time.monotonic()
                with self.assertRaises(FlowError):bounded_probe(home)
                self.assertLess(time.monotonic()-start,4,'Doctor exceeded total hook budget')
                self.assertFalse((home/'doska-state').exists(),'Read-only doctor created workflow state')
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
