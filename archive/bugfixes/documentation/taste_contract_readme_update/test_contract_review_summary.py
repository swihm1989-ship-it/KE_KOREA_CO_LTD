import unittest
from Quotation_KEKOREA.contracts.review_summary import summarize_issues, unresolved_issues


class ContractReviewSummaryTests(unittest.TestCase):
    def test_sixteen_detailed_findings_become_five_or_fewer_korean_groups(self):
        issues = ([{'severity':'block', 'code':'party_details',
                    'message':'Confirm VIBE INVESTMENT PTE LTD and signing authority'}] * 5
                  + [{'severity':'block', 'code':'payment_trigger',
                      'message':'Confirm the actual receipt and commission basis'}] * 4
                  + [{'severity':'block', 'code':'property_address',
                      'message':'Confirm the property identity'}] * 3
                  + [{'severity':'block', 'code':'governing_law',
                      'message':'Verify governing law and tax'}] * 3
                  + [{'severity':'block', 'code':'unconfirmed_terms',
                      'message':'All snapshot business terms are suggested or missing.'}])
        groups = summarize_issues(issues)
        self.assertLessEqual(len(groups), 5)
        self.assertEqual(sum(item['count'] for item in groups), 16)
        self.assertTrue(all(any('\uac00' <= ch <= '\ud7a3' for ch in item['label']) for item in groups))

    def test_confirmed_resolved_and_info_do_not_appear(self):
        issues = [
            {'severity':'info','message':'notice'},
            {'severity':'confirm','confirmed':True,'message':'done'},
            {'severity':'block','resolved_by_user':True,'resolution':'verified document','message':'done'},
            {'severity':'block','message':'Verify signing authority'},
        ]
        self.assertEqual(len(unresolved_issues(issues)), 1)
        self.assertEqual(sum(row['count'] for row in summarize_issues(issues)), 1)

    def test_original_issue_objects_are_not_modified(self):
        src = [{'severity':'block','code':'party','message':'Review'}]
        original = [x.copy() for x in src]
        summarize_issues(src)
        self.assertEqual(src, original)

    def test_empty_and_other_issue(self):
        self.assertEqual(summarize_issues([]), [])
        self.assertEqual(summarize_issues([{'severity':'confirm','message':'unknown'}])[0]['count'], 1)

    def test_invalid_group_limit(self):
        with self.assertRaises(ValueError):
            summarize_issues([], max_groups=0)
