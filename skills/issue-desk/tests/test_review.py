import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('review', Path(__file__).resolve().parents[1] / 'scripts/server.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
SAMPLE = """**A sample finding** about a credential boundary.

Rotate or revoke the demo credential and remove its literal:

```bash
printf 'example only'
```

Confirm the remediation with the owner."""


def fixture_issues():
    issues = {}
    for ident, severity in [('APP-01','Critical'),('APP-02','High'),('APP-03','High'),('APP-17','Medium'),('API-02','High')]:
        project = 'app' if ident.startswith('APP') else 'api'
        issues[ident] = dict(id=ident, project=project, severity=severity, area='Testing',
                             title='Synthetic finding', body='Synthetic evidence and remediation.',
                             fingerprint='fixture-' + ident, report=project+'-audit-report-2026-01-01.md')
    return issues, [dict(id=p, count=sum(i['project']==p for i in issues.values())) for p in ['app','api']]



class Reports(unittest.TestCase):
    def test_relative_evidence_and_current_report_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'demo.py').write_text('pass\n')
            (root/'demo-audit-report-2026-01-01.md').write_text(
                '| ID | Severity | Area | Finding | Evidence anchor |\n'
                '|---|---|---|---|---|\n'
                '| [DEMO-01](#demo-01) | High | Testing | Demo issue | [demo.py:1](demo.py:1) |\n\n'
                '<a id="demo-01"></a>\n\n### DEMO-01 — Demo issue\n\nEvidence and remediation.\n')
            issues, projects=app.load_reports(root)
            self.assertEqual(len(projects),1)
            self.assertEqual(issues['DEMO-01']['evidence_path'],'demo.py')
            self.assertEqual(issues['DEMO-01']['body'],'Evidence and remediation.')


class Review(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        real_issues, real_projects = fixture_issues()
        self.patches = [patch.object(app, 'DATA', root / 'data'), patch.object(app, 'ROOT', root),
                        patch.object(app, 'EXPORT', root / 'selected-issues.md'),
                        patch.object(app, 'load_reports', return_value=(real_issues, real_projects))]
        for p in self.patches:
            p.start()
        app.initialize()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def review(self, ident='APP-01'):
        with app.connect() as conn:
            return app.state(conn, ident)

    def test_exact_user_markdown_can_be_approved_and_removed(self):
        saved = app.update_review('APP-01', SAMPLE, False, 0)
        self.assertNotIn(SAMPLE, app.EXPORT.read_text())
        approved = app.update_review('APP-01', SAMPLE, True, saved['version'])
        self.assertIn(SAMPLE, app.EXPORT.read_text())
        with app.connect() as conn:
            app.sync_selection(conn)
        self.assertEqual(self.review()['draft'], SAMPLE)
        self.assertEqual(self.review()['version'], approved['version'])
        app.update_review('APP-01', SAMPLE, False, approved['version'])
        self.assertNotIn(SAMPLE, app.EXPORT.read_text())

    def test_empty_rejected_and_stale_version_preserves_edits(self):
        with self.assertRaises(ValueError):
            app.update_review('APP-01', '  ', True, 0)
        app.update_review('APP-01', 'My free-form draft', False, 0)
        with self.assertRaises(ValueError):
            app.update_review('APP-01', SAMPLE, True, 0)
        self.assertEqual(self.review()['draft'], 'My free-form draft')

    def test_manual_file_edit_syncs_and_survives_other_approvals_and_restart(self):
        app.update_review('APP-01', SAMPLE, True, 0)
        doc=app.selection_document()
        changed=doc['content'].replace('Rotate or revoke', 'Immediately rotate or revoke') + '\n## Personal notes\n\nKeep this note.\n'
        app.save_selection(changed, doc['revision'])
        self.assertIn('Immediately rotate', self.review()['draft'])
        app.update_review('API-02', 'A different issue and fix.', True, 0)
        app.initialize()
        output=app.EXPORT.read_text()
        self.assertIn('Immediately rotate', output)
        self.assertIn('Keep this note.', output)
        self.assertIn('A different issue and fix.', output)

    def test_delete_section_unselects_and_keeps_draft(self):
        app.update_review('APP-01', SAMPLE, True, 0)
        doc=app.selection_document()
        content=app.edit_selection(doc['content'], 'APP-01', None)
        app.save_selection(content, doc['revision'])
        self.assertFalse(self.review()['approved'])
        self.assertEqual(self.review()['draft'], SAMPLE)

    def test_clear_file_and_revision_conflict(self):
        app.update_review('APP-01', SAMPLE, True, 0)
        doc=app.selection_document()
        app.save_selection('', doc['revision'])
        self.assertEqual(app.EXPORT.read_text(), '')
        self.assertFalse(self.review()['approved'])
        with self.assertRaises(ValueError):
            app.save_selection('Must not overwrite', doc['revision'])
        self.assertEqual(app.EXPORT.read_text(), '')

    def test_external_edits_detected_before_approval(self):
        app.update_review('APP-01', SAMPLE, True, 0)
        app.EXPORT.write_text(app.EXPORT.read_text().replace('Rotate or revoke','Immediately revoke'))
        with self.assertRaises(ValueError):
            app.update_review('APP-01', SAMPLE, True, 1)
        self.assertIn('Immediately revoke', app.EXPORT.read_text())

    def test_code_fences_and_internal_headings_do_not_split_issue(self):
        draft='## Remediation\n\n### Details\n\n````md\n### APP-02\n```bash\necho test\n```\n````\n\nKeep this paragraph.'
        app.update_review('APP-01', draft, True, 0)
        sections,_=app.selection_sections(app.EXPORT.read_text())
        self.assertEqual(set(sections),{'APP-01'})
        self.assertEqual(sections['APP-01']['body'],draft)

    def test_duplicate_sections_rejected_without_writing(self):
        doc=app.selection_document()
        with self.assertRaises(ValueError):
            app.save_selection('## app\n### APP-01\nFirst\n### APP-01\nSecond',doc['revision'])
        self.assertEqual(app.selection_document(),doc)

    def test_project_grouping_and_severity_order(self):
        for ident in ['APP-17','APP-01','API-02']:
            app.update_review(ident, f'Fix {ident}.', True, 0)
        content=app.EXPORT.read_text()
        self.assertEqual(content.count('## app\n'),1)
        self.assertEqual(content.count('## api\n'),1)
        self.assertLess(content.index('#### APP-01'),content.index('#### APP-17'))
        self.assertIn('#### API-02',content)
        self.assertIn('## app\n\n### Critical\n\n#### APP-01',content)
        self.assertIn('### Medium\n\n#### APP-17',content)
        self.assertIn('## api\n\n### High\n\n#### API-02',content)

    def test_legacy_file_migration_preserves_text_and_is_idempotent(self):
        legacy = '# Selected issues\n\n## app\n\n### APP-17\n\nManual CI text.\n\n### APP-01\n\n' + SAMPLE + '\n'
        app.EXPORT.write_text(legacy)
        app.initialize()
        output=app.EXPORT.read_text()
        self.assertIn('## app\n\n### Critical\n\n#### APP-01',output)
        self.assertIn('### Medium\n\n#### APP-17',output)
        self.assertIn(SAMPLE,output)
        self.assertIn('Manual CI text.',output)
        self.assertEqual(app.migrate_selection(output),output)
        sections,_=app.selection_sections(output)
        self.assertEqual(sections['APP-01']['body'],SAMPLE)
        self.assertEqual(sections['APP-17']['body'],'Manual CI text.')

    def test_severity_sections_are_reused_and_removal_keeps_neighbors(self):
        for ident in ['APP-02','APP-17','APP-03','APP-01']:
            app.update_review(ident,f'Problem: {ident} problem.\nSolution: Fix it.',True,0)
        output=app.EXPORT.read_text()
        self.assertEqual(output.count('### High\n'),1)
        self.assertLess(output.index('### Critical'),output.index('### High'))
        self.assertLess(output.index('### High'),output.index('### Medium'))
        app.update_review('APP-02','Keep draft.',False,1)
        sections,_=app.selection_sections(app.EXPORT.read_text())
        self.assertEqual(set(sections),{'APP-01','APP-03','APP-17'})
        self.assertRegex(app.EXPORT.read_text(),r'### High\s+#### APP-03')

    def test_generated_draft_has_only_problem_and_solution(self):
        class Result:
            returncode=0
        answer='Problem: Credentials are exposed.\nSolution: Rotate them and remove them from source.'
        def fake_run(command, **kwargs):
            self.assertIn('exactly two lines',kwargs['input'])
            self.assertIn('Do not include the issue ID, severity',kwargs['input'])
            Path(command[command.index('--output-last-message')+1]).write_text(answer)
            return Result()
        app.JOBS['two-lines']={'status':'queued'}
        with patch.object(app.subprocess,'run',side_effect=fake_run):
            app.run_job('two-lines','APP-01','draft','',0)
        self.assertEqual(app.JOBS['two-lines']['status'],'done')
        self.assertEqual(self.review()['draft'],answer)
        self.assertFalse(self.review()['approved'])

    def test_selected_severity_override_moves_issue_and_preserves_original(self):
        app.update_review('APP-01', 'Problem: Exposed credentials.\nSolution: Rotate them.', True, 0, 'Low')
        self.assertIn('### Low\n\n#### APP-01', app.EXPORT.read_text())
        self.assertEqual(app.ISSUES['APP-01']['severity'], 'Critical')
        self.assertEqual(self.review()['selected_severity'], 'Low')
        app.update_review('APP-01', 'Problem: Exposed credentials.\nSolution: Rotate them.', True, 1, 'High')
        self.assertIn('### High\n\n#### APP-01', app.EXPORT.read_text())
        self.assertEqual(app.EXPORT.read_text().count('#### APP-01'), 1)
        app.initialize()
        self.assertEqual(self.review()['selected_severity'], 'High')

    def test_invalid_override_rejected_and_manual_heading_change_synced(self):
        with self.assertRaises(ValueError):
            app.update_review('APP-01', 'My draft', True, 0, 'Urgent')
        app.update_review('APP-01', 'My draft', True, 0, 'Low')
        doc=app.selection_document()
        app.save_selection(doc['content'].replace('### Low','### Medium'), doc['revision'])
        self.assertEqual(self.review()['selected_severity'], 'Medium')

    def test_reapproval_preserves_independent_notes_and_removed_report_issue(self):
        app.update_review('APP-02','Current draft.',True,0)
        app.update_review('APP-03','Old source finding.',True,0)
        doc=app.selection_document()
        app.save_selection(doc['content']+'\n## Personal notes\n\nKeep my notes.\n',doc['revision'])
        del app.ISSUES['APP-03']
        with app.connect() as conn:
            app.sync_selection(conn)
        self.assertEqual(self.review('APP-02')['draft'],'Current draft.')
        app.update_review('APP-02','Revised draft.',True,self.review('APP-02')['version'])
        self.assertIn('Old source finding.',app.EXPORT.read_text())
        self.assertIn('Keep my notes.',app.EXPORT.read_text())

    def test_processed_persists_independently_of_selection(self):
        app.set_processed('APP-01', True)
        self.assertTrue(self.review()['processed'])
        self.assertFalse(self.review()['approved'])
        app.update_review('APP-01', SAMPLE, True, 0)
        app.update_review('APP-01', SAMPLE, False, 1)
        app.initialize()
        self.assertTrue(self.review()['processed'])
        app.set_processed('APP-01', False)
        self.assertFalse(self.review()['processed'])

    def test_generation_does_not_overwrite_concurrent_draft_edits(self):
        class Result:
            returncode=0
        def fake_run(command, **kwargs):
            app.update_review('APP-01', 'Keep my edit.', False, 0)
            Path(command[command.index('--output-last-message')+1]).write_text('Problem: Exposed credentials.\nSolution: Rotate them.')
            return Result()
        app.JOBS['conflict']={'status':'queued'}
        with patch.object(app.subprocess,'run',side_effect=fake_run):
            app.run_job('conflict','APP-01','draft','',0)
        self.assertEqual(app.JOBS['conflict']['status'],'error')
        self.assertEqual(self.review()['draft'],'Keep my edit.')


if __name__=='__main__':
    unittest.main()
