"""Real worker coordination and menu state isolation, without external services."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest

from Quotation_KEKOREA.agent.workflow_state import DocumentWorkspaces


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.addCleanup(self.executor.shutdown, wait=True)
        self.work = DocumentWorkspaces(executor=self.executor)
        self.state = {}

    def test_menu_roundtrip_preserves_drafts_widgets_files_and_unfinished_json(self):
        for page in ('PI', 'PO', 'CI', 'PL', 'CIPL'):
            name = page + ' 만들기'
            self.work.activate(self.state, name)
            self.state.update(trade_draft={'document_type': page}, trade_draft_page=name,
                              rendered_paths={'pdf': page + '.pdf'}, download_format='pdf',
                              rendered_json=page)
            self.state[f'order_prompt_{name}'] = 'prompt ' + page
            self.state[f'advanced_json_{name}'] = 'unfinished edit ' + page
            self.state[f'packing_{name}_confirmed_abc'] = True
            self.state[f'product_double_check_{name}_0'] = 'corrected product ' + page
        self.work.activate(self.state, '계약서 만들기 · 준비 중')
        for key in list(self.state):
            if key.startswith(('order_prompt_', 'advanced_json_', 'packing_', 'product_double_check_')):
                del self.state[key]  # Streamlit removes widgets absent from a run.
        for page in ('PI', 'PO', 'CI', 'PL', 'CIPL'):
            name = page + ' 만들기'
            self.work.activate(self.state, name)
            self.assertEqual(self.state['trade_draft'], {'document_type': page})
            self.assertEqual(self.state['rendered_paths'], {'pdf': page + '.pdf'})
            self.assertEqual(self.state[f'order_prompt_{name}'], 'prompt ' + page)
            self.assertEqual(self.state[f'advanced_json_{name}'], 'unfinished edit ' + page)
            self.assertTrue(self.state[f'packing_{name}_confirmed_abc'])
            self.assertEqual(self.state[f'product_double_check_{name}_0'], 'corrected product ' + page)

    def test_new_extraction_resets_product_double_check_widget_values(self):
        self.work.activate(self.state, 'PO 만들기')
        self.state['product_double_check_PO 만들기_0'] = 'old corrected product'
        self.work.save(self.state)
        job = self.work.start('PO 만들기', 'extract', lambda: {'document_type': 'PO', 'items': []})
        job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertNotIn('product_double_check_PO 만들기_0', self.state)

    def test_background_extraction_survives_navigation_and_another_job(self):
        started, release = Event(), Event()
        self.addCleanup(release.set)
        def slow_extract():
            started.set()
            self.assertTrue(release.wait(5))
            return {'document_type': 'PI', 'items': []}
        self.work.activate(self.state, 'PI 만들기')
        pi_job = self.work.start('PI 만들기', 'extract', slow_extract)
        self.assertTrue(started.wait(2))
        self.work.activate(self.state, 'PO 만들기')
        po_job = self.work.start('PO 만들기', 'extract', lambda: {'document_type': 'PO'})
        po_job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertEqual(self.state['trade_draft']['document_type'], 'PO')
        self.assertFalse(pi_job.future.done())
        release.set()
        pi_job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertEqual(self.state['trade_draft']['document_type'], 'PO')
        self.work.activate(self.state, 'PI 만들기')
        self.assertEqual(self.state['trade_draft']['document_type'], 'PI')

    def test_render_completion_returns_to_origin_and_stale_output_is_discarded(self):
        self.work.activate(self.state, 'PI 만들기')
        self.state['rendered_json'] = 'original'
        self.work.save(self.state)
        job = self.work.start('PI 만들기', 'render', lambda: {'pdf': 'pi.pdf'},
                              context='original', file_format='pdf')
        self.work.activate(self.state, 'PO 만들기')
        job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertNotIn('download_format', self.state)
        self.work.activate(self.state, 'PI 만들기')
        self.assertEqual(self.state['rendered_paths'], {'pdf': 'pi.pdf'})
        job = self.work.start('PI 만들기', 'render', lambda: {'pdf': 'old.pdf'},
                              context='original', file_format='pdf')
        self.state['rendered_json'] = 'edited'
        self.state['rendered_paths'] = {}
        job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertEqual(self.state['rendered_paths'], {})

    def test_duplicate_inflight_job_is_rejected_and_failures_allow_retry(self):
        release = Event()
        self.addCleanup(release.set)
        def fail():
            release.wait(5)
            raise ValueError('test failure')
        self.work.activate(self.state, 'PO 만들기')
        job = self.work.start('PO 만들기', 'extract', fail)
        self.assertIsNone(self.work.start('PO 만들기', 'extract', lambda: {}))
        release.set()
        with self.assertRaisesRegex(ValueError, 'test failure'):
            job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertIn('test failure', self.work.errors['PO 만들기'])
        retry = self.work.start('PO 만들기', 'extract', lambda: {'document_type': 'PO'})
        retry.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertNotIn('PO 만들기', self.work.errors)
        self.assertEqual(self.state['trade_draft']['document_type'], 'PO')

    def test_worker_inputs_and_browser_sessions_are_independent(self):
        other = DocumentWorkspaces(executor=self.executor)
        release = Event()
        self.addCleanup(release.set)
        original = {'quantity': 10}
        def read_snapshot(value):
            release.wait(5)
            return value
        self.work.activate(self.state, 'PI 만들기')
        job = self.work.start('PI 만들기', 'extract', read_snapshot, original)
        original['quantity'] = 99
        release.set()
        job.future.result(timeout=2)
        self.work.collect(self.state)
        self.assertEqual(self.state['trade_draft']['quantity'], 10)
        other_state = {}
        other.activate(other_state, 'PI 만들기')
        self.assertNotIn('trade_draft', other_state)
