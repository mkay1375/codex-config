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


class ReadableSummaryTests(unittest.TestCase):
    def test_summary_updates_preserve_notes_and_keep_json_below_cut(self):
        value={'schema':1,'kind':'task','state':'Review','owner':'Alice','activity':'idle','summary':'Tests passed','next_action':'Review PR','next_actor':'Me'}
        body=with_metadata('Human notes\nKeep exactly.',value)+'\nHuman footer'
        preview=body.split('-cut-',1)[0]
        self.assertIn('**State:** Review',preview)
        self.assertIn('**Latest:** Tests passed',preview)
        self.assertIn('**Next:** Me — Review PR',preview)
        self.assertNotIn('```json',preview)
        changed=with_metadata(body,{**value,'summary':'Updated result'})
        self.assertEqual(metadata(changed)['summary'],'Updated result')
        self.assertIn('Human notes\nKeep exactly.',changed)
        self.assertTrue(changed.endswith('\nHuman footer'))
        self.assertEqual(changed.count(SUMMARY_BEGIN),1)
        self.assertNotIn('Tests passed',changed)
        self.assertEqual(with_metadata(changed,metadata(changed)),changed)
    def test_summary_cannot_inject_preview_cut_or_markdown_link(self):
        body=with_metadata('',{'schema':1,'kind':'task','state':'Doing','summary':'Hi\n-cut-\n[x](https://example.com)'})
        preview=body.split('\n-cut-\n',1)[0]
        self.assertNotIn('[x](',preview)
        self.assertEqual(body.count('\n-cut-\n'),1)
