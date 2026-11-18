"""Synthetic regression for MASTER contract stage callbacks.

No AI API, SMTP, Supabase writes, signing or contract publication.
"""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from Quotation_KEKOREA.contracts.models import new_snapshot
from Quotation_KEKOREA.orchestration.workflows.ai_intake import generate_contract_draft


class ContractStageProgressTests(TestCase):
    def setUp(self):
        self.original = new_snapshot("orchestration-synthetic-stage", "sale", "ko")
        self.env = {"OPENAI_API_KEY": "synthetic", "OPENAI_MODEL": "mock-model"}

    def test_master_forwards_real_graph_progress_and_keeps_existing_draft_guards(self):
        seen = []
        def fake_graph(candidate, preferred_clauses, **kwargs):
            callback = kwargs.get("progress_callback")
            self.assertIs(callback, seen.append)
            self.assertFalse(kwargs["use_library"])
            self.assertFalse(kwargs["transaction_messages"])
            self.assertEqual(preferred_clauses, [])
            callback("입력 조건 검증")
            callback("AI 계약서 초안 작성")
            candidate = deepcopy(candidate)
            candidate["clauses"] = [{
                "id": "contract-stage-clause-1", "title": "거래 범위",
                "order": 1, "topic_key": "scope",
                "sentences": [{
                    "id": "contract-stage-sentence-1",
                    "text": "당사자는 계약 대상 물품의 확정된 규격을 별도 문서로 합의한다.",
                    "term_ids": [], "source_refs": [],
                }],
            }]
            return candidate

        with patch("Quotation_KEKOREA.contracts.ai_graph.generate_contract_draft_graph",
                   side_effect=fake_graph) as graph:
            draft = generate_contract_draft(
                self.original, self.env, consent=True,
                use_library=False, progress_callback=seen.append)
        self.assertEqual(seen, ["입력 조건 검증", "AI 계약서 초안 작성"])
        self.assertEqual(len(draft["clauses"]), 1)
        self.assertEqual(self.original["clauses"], [])
        self.assertEqual(graph.call_count, 1)

    def test_consent_is_still_required_before_progress_or_generation(self):
        seen = []
        with self.assertRaises(PermissionError):
            generate_contract_draft(self.original, self.env,
                                    consent=False, progress_callback=seen.append)
        self.assertEqual(seen, [])
