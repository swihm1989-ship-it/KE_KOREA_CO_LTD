"""Targeted fix for month names in KE KOREA contract translation numeric checks.
Run from project root: python path/to/apply_month_translation_fix.py
Only modifies the numeric validator, adds tests, and syncs five READMEs.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
TARGET = ROOT / 'Quotation_KEKOREA/contracts/contract_versions.py'
TEST = ROOT / 'Quotation_KEKOREA/tests/test_contract_translation_month_names.py'
READMES = [
    ROOT / 'README.md',
    ROOT / 'Quotation_KEKOREA/README.md',
    ROOT / 'Quotation_KEKOREA/README_CONTRACTS.md',
    ROOT / 'Quotation_KEKOREA/Team/README.md',
    ROOT / 'Quotation_KEKOREA/Presentation/README.md',
]
START = 'def _numbers(text):'
OLD = "for match in _NUMBER.finditer(str(text or '')):"
NEW = "for match in _NUMBER.finditer(_normalize_month_words(str(text or ''))):"
SENTINEL = 'def _normalize_month_words(text):'

INSERT = '''_MONTH_NAME_VALUES = {
    'january': 1, 'jan': 1, 'february': 2, 'feb': 2,
    'march': 3, 'mar': 3, 'april': 4, 'apr': 4,
    'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
    'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10, 'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}
_MONTH_WORD_RE = re.compile(
    r'\\b(?:January|February|March|April|May|June|July|August|September|'
    r'October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\\b\\.?',
    re.I,
)


def _normalize_month_words(text):
    """Map English date-month names to numeric month tokens for comparison.

    Only convert month names in a recognizable date context, to avoid
    mistaking the legal modal verb 'may' for the month May.
    """
    def convert(match):
        before, after = text[:match.start()], text[match.end():]
        has_following_day = re.match(r'\\s+\\d{1,2}(?:st|nd|rd|th)?\\b', after, re.I)
        has_preceding_day = re.search(r'\\b\\d{1,2}(?:st|nd|rd|th)?\\s+(?:of\\s+)?$', before, re.I)
        has_following_year = re.match(r'\\s+(?:of\\s+)?\\d{4}\\b', after, re.I)
        if has_following_day or has_preceding_day or has_following_year:
            return str(_MONTH_NAME_VALUES[match.group(0).rstrip('.').lower()])
        return match.group(0)
    return _MONTH_WORD_RE.sub(convert, text)


'''

TEST_CONTENT = '''import unittest
from Quotation_KEKOREA.contracts.contract_versions import _numbers, _normalize_month_words


class ContractTranslationMonthTests(unittest.TestCase):
    def test_korean_dates_equal_english_month_names(self):
        korean = '계약기간은 2026년 11월 10일부터 3년으로 하며, 종료일은 2029년 11월 10일로 한다. 30일.'
        english = 'The term shall be 3 years from November 10, 2026, ending November 10, 2029. 30 days.'
        self.assertEqual(_numbers(korean), _numbers(english))

    def test_actual_month_change_is_detected(self):
        self.assertNotEqual(_numbers('2026년 11월 10일'), _numbers('December 10, 2026'))
        self.assertNotEqual(_numbers('2026년 11월 10일'), _numbers('November 11, 2026'))

    def test_actual_amount_or_percent_change_is_detected(self):
        self.assertNotEqual(_numbers('30%'), _numbers('40%'))
        self.assertNotEqual(_numbers('USD 1,000'), _numbers('USD 1100'))

    def test_month_abbreviations_and_british_dates(self):
        self.assertEqual(_numbers('2026년 11월 10일'), _numbers('10 Nov. 2026'))
        self.assertEqual(_numbers('2026년 5월 10일'), _numbers('May 10, 2026'))

    def test_modal_may_is_not_misread_as_month(self):
        self.assertEqual(_normalize_month_words('The party may terminate within 30 days.'),
                         'The party may terminate within 30 days.')


if __name__ == '__main__':
    unittest.main()
'''

NOTE = '''\n### 2026-11-09 영어 계약서 날짜 번역 숫자 검증 보완\n\n- 한국어 `2026년 11월 10일`과 영어 `November 10, 2026`의 달 표기를 같은 값으로 비교합니다. 날짜 맥락의 영어 월 이름/약어만 숫자로 정규화합니다.\n- 원래 금액·수량·비율·날짜의 실제 값 변경은 계속 차단하고, 불일치 시 원문/번역문과 차이를 보여줍니다. 원본 계약은 보존됩니다.\n- 회귀 테스트: `Quotation_KEKOREA/tests/test_contract_translation_month_names.py`. 실모델 응답·운영 Streamlit은 별도 검증이 필요합니다.\n'''


def main():
    if not TARGET.exists() or any(not p.exists() for p in READMES):
        raise SystemExit('프로젝트 최상위 폴더에서 실행하세요. 계약서 파일 또는 README가 없습니다.')
    source = TARGET.read_text(encoding='utf-8')
    if SENTINEL in source:
        print('이미 날짜 월 이름 수정이 반영되어 있습니다. 중복 설치하지 않습니다.')
        return
    if source.count(START) != 1 or source.count(OLD) != 1:
        raise SystemExit('기존 검증 함수가 예상과 달라 변경하지 않았습니다. 최신 파일을 확인하세요.')
    if TEST.exists():
        raise SystemExit('같은 이름의 테스트 파일이 있어 안전하게 중단했습니다.')
    out = source.replace(START, INSERT + START, 1).replace(OLD, NEW, 1)
    compile(out, str(TARGET), 'exec')
    compile(TEST_CONTENT, str(TEST), 'exec')
    originals = {TARGET: source, **{p:p.read_text(encoding='utf-8') for p in READMES}}
    backup = ROOT.parent / ('KEKOREA_month_fix_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    for file in originals:
        dest = backup / file.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,dest)
    try:
        TARGET.write_text(out,encoding='utf-8')
        TEST.write_text(TEST_CONTENT,encoding='utf-8')
        for file in READMES:
            file.write_text(originals[file].rstrip()+ '\n'+ NOTE,encoding='utf-8')
    except BaseException:
        for file, body in originals.items():
            file.write_text(body,encoding='utf-8')
        TEST.unlink(missing_ok=True)
        raise
    print('OK: 영어 월 이름 날짜 변환 버그 패치 적용 완료')
    print('백업 위치: '+str(backup))
    print('다음: 전체 unittest 실행, README sync guard, 커밋/푸시')


if __name__ == '__main__':
    main()
