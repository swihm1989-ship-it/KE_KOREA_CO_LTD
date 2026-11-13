import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from Quotation_KEKOREA.observability.storage import EventStore
from Quotation_KEKOREA.observability import core


SCRIPT = '''
import streamlit as st
from Quotation_KEKOREA.orchestration.ui.monitoring_page import render_monitoring
render_monitoring("owner@example.test", st.session_state["telemetry_test_store"])
'''


class MonitoringUiTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore({})

    def app(self, script=SCRIPT):
        app=AppTest.from_string(script)
        app.session_state['telemetry_test_store']=self.store
        return app.run()

    def test_empty_dashboard_is_rendered_without_provider_or_storage_calls(self):
        app = self.app()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('관리자 모니터링' in h.value for h in app.subheader))
        self.assertTrue(any('임시 메모리' in m.value for m in app.warning))
        self.assertEqual(app.metric[0].value,'0')

    def test_ai_usage_cost_errors_and_json_events_render(self):
        old = core.set_recorder(self.store.emit)
        try:
            with core.operation('ai.request',model='gpt-6-luna') as ai:
                ai.usage({'usage':{'input_tokens':1000,'output_tokens':200}})
            with core.operation('ai.request',model='gpt-6-luna') as ai:
                ai.failure(TimeoutError('PRIVATE CONTENT'))
        finally:
            core.set_recorder(old)
        app = self.app()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.metric[0].value,'2')
        self.assertTrue(any('50.0%' == m.value for m in app.metric))
        self.assertGreaterEqual(len(app.dataframe),2)
        app.selectbox(key='telemetry_days').set_value(1).run()
        app.button(key='telemetry_refresh').click().run()
        self.assertEqual(app.metric[0].value,'2') # Reruns do not create AI calls.
        self.assertNotIn('PRIVATE CONTENT',str(app))

    def test_unauthorized_principal_causes_no_store_read(self):
        script=SCRIPT.replace('"owner@example.test"','""')
        with patch.object(self.store,'summary') as summary,patch.object(self.store,'recent') as recent:
            app=self.app(script)
        self.assertEqual(len(app.exception),0)
        self.assertTrue(app.error)
        summary.assert_not_called()
        recent.assert_not_called()

    def test_remote_failure_displays_redacted_degraded_mode(self):
        self.store.configured=True
        with patch.object(self.store,'summary',side_effect=RuntimeError('SECRET-KEY')):
            app=self.app()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any('임시 메모리' in w.value for w in app.warning))
        self.assertNotIn('SECRET-KEY',str(app))
