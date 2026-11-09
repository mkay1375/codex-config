import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from doska_flow.model import *
from doska_flow.config import Config

class Contracts(unittest.TestCase):
    def test_human_notes_survive_metadata_update(self):
        body = 'Human notes\n\n' + with_metadata('', {'schema': 1, 'task': 'x'}) + '\nHuman footer'
        changed = with_metadata(body, {'schema': 1, 'task': 'y'})
        self.assertTrue(changed.startswith('Human notes\n\n'))
        self.assertTrue(changed.endswith('\nHuman footer'))
        self.assertEqual(metadata(changed)['task'], 'y')
    def test_duplicate_block_rejected(self):
        block = with_metadata('', {'schema': 1})
        with self.assertRaises(Conflict): with_metadata(block + block, {'schema': 1})
    def test_endpoint_boundaries(self):
        for mode, endpoint in [('local','http://0.0.0.0:3846/mcp'),('local','http://localhost:3846/mcp'),('remote','http://example.com/mcp'),('remote','https://a:b@example.com/mcp')]:
            with self.assertRaises(FlowError): Config(mode, 'a', endpoint=endpoint)
    def test_states_and_chat_identity(self):
        self.assertIn('Procrastinated', STATES)
        self.assertEqual(chat_reference('thr_123','pc')['uri'], 'codex://threads/thr_123')
        with self.assertRaises(FlowError): chat_reference('x?bad', 'pc')
if __name__ == '__main__': unittest.main()
