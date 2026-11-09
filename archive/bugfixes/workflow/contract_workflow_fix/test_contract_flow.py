"""Regression checks for deterministic contract workflow controls."""
import unittest
from Quotation_KEKOREA.contracts.flow import wants_contract_draft, should_generate_draft, select_new_questions


class DraftFirstWorkflowTests(unittest.TestCase):
    def test_explicit_korean_draft_request(self):
        for text in ('계약서 초안을 작성해줘', '이제 계약서 만들어 주세요',
                     '추가 질문 없이 초안을 생성해줘', '계약서를 작성해 주세요'):
            with self.subTest(text=text):
                self.assertTrue(wants_contract_draft(text))

    def test_english_draft_request(self):
        self.assertTrue(wants_contract_draft('Please draft the commission agreement.'))
        self.assertTrue(wants_contract_draft('Please create a contract.'))

    def test_draft_after_first_reply_without_keyword(self):
        messages = [{'role': 'user', 'content': '커미션 3%'},
                    {'role': 'assistant', 'content': '지급자 국가는?'},
                    {'role': 'user', 'content': '싱가포르입니다'}]
        self.assertTrue(should_generate_draft('싱가포르입니다', messages))
        self.assertFalse(should_generate_draft('싱가포르입니다', messages, has_clauses=True))
        self.assertFalse(should_generate_draft('커미션 3%', messages[:1]))

    def test_non_draft_prompt(self):
        self.assertFalse(wants_contract_draft('커미션이 3%입니다.'))
        self.assertFalse(wants_contract_draft('계약서 조항의 위험을 검토해줘'))

    def test_questions_only_once(self):
        questions = ['지급자 국가는 어디입니까?', '법인 주소는 무엇입니까?', '계좌는 확인됐습니까?']
        self.assertEqual(len(select_new_questions(questions, [{'role':'user','content':'커미션은 3%'}])), 2)
        self.assertEqual(select_new_questions(questions, [
            {'role':'user','content':'커미션은 3%'},
            {'role':'assistant','content':'확인할 사항: 지급자 국가는 어디입니까?'},
            {'role':'user','content':'싱가포르입니다'}]), [])

    def test_no_question_overflow(self):
        self.assertEqual(select_new_questions(['Q1', 'Q2', 'Q3'], [], limit=1), ['Q1'])
        self.assertEqual(select_new_questions(['Q1'], [], limit=0), [])


if __name__ == '__main__':
    unittest.main()
