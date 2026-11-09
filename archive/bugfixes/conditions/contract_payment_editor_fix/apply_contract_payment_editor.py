"""Safely add a form-based commission editor without touching other modules.
Run once from the KE_KOREA_CO_LTD project root.
"""
from pathlib import Path
import re
import tempfile
import os

ROOT = Path('Quotation_KEKOREA/contracts')
POLICY = ROOT / 'commission_policy.py'
UI = ROOT / 'ui.py'


def unique_replace(text, before, after, name):
    n = text.count(before)
    if n != 1:
        raise RuntimeError(f'{name}: expected one original block, found {n}. No files were modified.')
    return text.replace(before, after, 1)


def build_policy(src):
    src = unique_replace(src,
        "DEADLINE = 'D+7 calendar days'",
        "DEADLINE = 'D+7 calendar days'\n\n\ndef _custom_deadline(snapshot):\n    \"\"\"Use a written custom deadline only when explicitly confirmed.\"\"\"\n    raw = _confirmed(snapshot, 'payment_deadline')\n    match = re.fullmatch(r'D\\+(\\d{1,2})(?: calendar days)?', raw, flags=re.IGNORECASE)\n    if not match:\n        return DEADLINE\n    days = int(match.group(1))\n    return f'D+{days} calendar days' if 1 <= days <= 90 else DEADLINE\n\n\ndef _negotiated_interest(snapshot):\n    \"\"\"A user-confirmed commercial rate, not a legal-validity conclusion.\"\"\"\n    value = _confirmed(snapshot, 'late_interest_rate')\n    if not value:\n        return None\n    match = re.fullmatch(r'(\\d{1,2}(?:\\.\\d{1,2})?)\\s*%', value)\n    if not match:\n        return None\n    rate = float(match.group(1))\n    return match.group(1) if 0 <= rate <= 30 else None",
        'payment helpers')
    src = unique_replace(src,
        "    deadline = _confirmed(snapshot, 'payment_deadline')\n    if deadline and deadline not in {DEADLINE, 'D+7', '7 calendar days', '7일 이내'}:\n        missing.append('지급기한이 기본 D+7 달력일 조건과 다릅니다. 충돌을 해결해 주세요.')",
        "    deadline = _confirmed(snapshot, 'payment_deadline')\n    custom_deadline = _custom_deadline(snapshot)\n    accepted_deadlines = {DEADLINE, 'D+7', '7 calendar days', '7일 이내', custom_deadline}\n    if deadline and deadline not in accepted_deadlines:\n        missing.append('지급기한 형식이 유효하지 않습니다. D+1~D+90의 달력일로 입력해 주세요.')\n    days = int(re.search(r'D\\+(\\d+)', custom_deadline).group(1))\n    rate = _negotiated_interest(snapshot)",
        'deadline handling')
    src = unique_replace(src,
        "'해당 트리거 발생일(D)로부터 7일 이내(D+7, 달력일 기준)에 Telegraphic Transfer(TT)로 지정된 회사 계좌에 입금해야 한다. '",
        "f'해당 트리거 발생일(D)로부터 {days}일 이내(D+{days}, 달력일 기준)에 Telegraphic Transfer(TT)로 지정된 회사 계좌에 입금해야 한다. '",
        'Korean deadline sentence')
    src = unique_replace(src,
        "'양 당사자가 별도로 서면 합의하지 않는 한, 지급기한 다음 날부터 실제 완제일까지 미지급 원금에 대하여 일할 단리로 연체이자를 부과한다. '\n            f'연체이율은 지급자 국가({country})에서 이 커미션 지급의무에 법적으로 적용할 수 있는 최고 허용 이율로 하되, '",
        "('양 당사자가 서면으로 합의한 경우 미지급 원금에 대해 지급기한 다음 날부터 실제 완제일까지 '\n             f'연 {rate}%의 단리 연체이자를 일할 계산하여 부과한다. ' if rate is not None else\n             '양 당사자가 별도로 서면 합의하지 않는 한, 지급기한 다음 날부터 실제 완제일까지 미지급 원금에 대하여 일할 단리로 연체이자를 부과한다. ')\n            + (f'합의 이율의 법적 적용 가능성은 지급자 국가({country}) 및 준거법에 따라 서명 전 검토한다. ' if rate is not None else\n               f'연체이율은 지급자 국가({country})에서 이 커미션 지급의무에 법적으로 적용할 수 있는 최고 허용 이율로 하되, ') +",
        'Korean interest rate')
    src = unique_replace(src,
        "'within seven (7) calendar days after that Trigger (D+7). Where actual receipt is the agreed Trigger, '",
        "f'within {days} calendar days after that Trigger (D+{days}). Where actual receipt is the agreed Trigger, '",
        'English deadline sentence')
    src = unique_replace(src,
        "'Unless varied by written agreement of both Parties, unpaid principal bears daily simple default interest '\n            'from the day following its due date until actual payment in full. The rate shall be the maximum rate '\n            f'lawfully applicable to this commission-payment obligation in the Payer country ({country}), '",
        "('Where the Parties agree in writing, unpaid principal shall bear daily simple default interest '\n             f'at {rate}% per annum from the day following the due date until actual payment in full. ' if rate is not None else\n             'Unless varied by written agreement of both Parties, unpaid principal bears daily simple default interest '\n             'from the day following its due date until actual payment in full. ')\n            + (f'The legal validity of this rate is subject to review under the Payer country ({country}) and governing law. ' if rate is not None else\n               f'The rate shall be the maximum rate lawfully applicable to this commission-payment obligation in the Payer country ({country}), ') +",
        'English interest rate')
    src = unique_replace(src,
        "    elif not str(deadline_term.get('value') or '').strip():\n        deadline_term.update(value=DEADLINE, status='confirmed', source_refs=[])",
        "    elif not str(deadline_term.get('value') or '').strip():\n        deadline_term.update(value=DEADLINE, status='confirmed', source_refs=[])\n    # Preserve a user's explicitly confirmed custom payment period.\n    # Unconfirmed proposals must not be silently treated as agreed.",
        'custom deadline preservation')
    return src


def build_ui(src):
    open_marker = '            with st.expander("기본 수수료 지급 조항", expanded=True):'
    end_marker = '        _render_draft(repo, snapshot, state_key, env)'
    a = src.find(open_marker)
    if a == -1 or src.count(open_marker) != 1:
        raise RuntimeError('Could not locate unique existing payment panel; no files modified.')
    b = src.find(end_marker, a)
    if b == -1:
        raise RuntimeError('Could not locate end of payment panel; no files modified.')
    panel = '''            with st.expander("수수료 지급조건 수정", expanded=False):
                st.caption("상업조건을 수정하고 저장하면 계약서 지급 조항도 함께 갱신됩니다. 미검증 계좌·법률 정보는 임의로 확정하지 않습니다.")
                from Quotation_KEKOREA.contracts.commission_policy import _confirmed, _custom_deadline, _negotiated_interest
                import re as _payment_re
                current_deadline = _custom_deadline(snapshot)
                days = int(_payment_re.search(r'D\\+(\\d+)', current_deadline).group(1))
                current_rate = _negotiated_interest(snapshot)
                payer = next((p for p in snapshot.get('parties', [])
                              if 'commission_payer' in p.get('roles', [])), {})
                current_country = str(payer.get('country') or '')
                current_trigger = _confirmed(snapshot, 'payment_trigger') or _confirmed(snapshot, 'success_trigger')
                default_trigger = '실제 투자금 입금' if not current_trigger else current_trigger
                with st.form(f"contract_payment_edit_{active_id}_{snapshot['revision']}"):
                    trigger = st.text_input("커미션 지급 트리거", value=default_trigger,
                                            help="예: 투자금이 지급자 계좌에 실제 입금된 날")
                    payment_days = st.number_input("지급기한 (트리거 후 달력일)", min_value=1,
                                                    max_value=90, value=days, step=1)
                    chosen_rate = st.text_input("서면 합의 연체이율 (연 %, 선택)",
                                                value=str(current_rate or ''),
                                                help="예: 6 또는 6.5. 입력한 상업조건이며 법적 유효성은 별도 검토합니다.")
                    payer_country = st.text_input("지급자 설립국가 (확인 전에는 미확정)", value=current_country)
                    country_verified = st.checkbox("지급자 설립국가를 등록서류로 확인했습니다",
                        value=payer.get('status') == 'confirmed' and bool(current_country))
                    st.caption("계좌정보는 서버에 등록된 KE KOREA 명의 USD 계좌만 사용할 수 있습니다. "
                               "계좌정보가 미검증이면 [수취 계좌 확인 필요]로 남깁니다.")
                    save_payment = st.form_submit_button("지급조건 저장 및 조항 갱신", type="primary")
                if save_payment:
                    try:
                        if not str(trigger).strip():
                            raise ValueError("커미션 지급 트리거를 입력해 주세요.")
                        cleaned = str(chosen_rate).strip().removesuffix('%').strip()
                        if cleaned and not _payment_re.fullmatch(r'\\d{1,2}(?:\\.\\d{1,2})?', cleaned):
                            raise ValueError("연체이율은 0~30 범위의 숫자로 입력해 주세요.")
                        if cleaned and not (0 <= float(cleaned) <= 30):
                            raise ValueError("연체이율은 0~30% 범위로 입력해 주세요.")
                        updated = deepcopy(snapshot)
                        def set_term(key, value, status='confirmed'):
                            term = next((x for x in updated.get('terms', []) if x.get('key') == key), None)
                            if term is None:
                                term = {'id': f'term_{uuid4().hex}', 'key': key,
                                        'source_refs': [], 'status': status}
                                updated.setdefault('terms', []).append(term)
                            term.update(value=value, status=status, source_refs=[])
                        set_term('payment_trigger', str(trigger).strip())
                        set_term('payment_deadline', f'D+{int(payment_days)} calendar days')
                        if cleaned:
                            set_term('late_interest_rate', f'{cleaned}%')
                        else:
                            updated['terms'] = [t for t in updated.get('terms', [])
                                                if t.get('key') != 'late_interest_rate']
                        current_payer = next((p for p in updated.get('parties', [])
                                              if 'commission_payer' in p.get('roles', [])), None)
                        if current_payer is not None and str(payer_country).strip():
                            current_payer['country'] = str(payer_country).strip()
                            current_payer['status'] = 'confirmed' if country_verified else 'suggested'
                        elif str(payer_country).strip():
                            st.warning("지급자 역할이 지정되지 않아 국가를 저장하지 못했습니다. 상세 거래조건에서 지급자 역할을 등록해 주세요.")
                        updated = apply_payment_policy(updated, env=env)
                        saved = _save_snapshot(repo, updated, "Updated agreed payment conditions and regenerated clauses")
                        st.session_state[state_key] = saved
                        for cache_key in ('contract_revisions', 'contract_pending_proposal',
                                          'contract_pending_terms', f'contract_pending_analysis_{active_id}',
                                          f'contract_rag_risk_{active_id}'):
                            st.session_state.pop(cache_key, None)
                        st.rerun()
                    except (ValueError, ContractRepositoryError) as exc:
                        st.error(str(exc))
                with st.expander("서명 전 확인할 항목", expanded=False):
                    for issue in payment_policy_issues(snapshot, env=env):
                        st.warning(issue['message'])
'''
    return src[:a] + panel + src[b:]


def main():
    if not POLICY.is_file() or not UI.is_file():
        raise SystemExit('Run this script from the KE_KOREA_CO_LTD project root.')
    original_policy, original_ui = POLICY.read_text(encoding='utf-8'), UI.read_text(encoding='utf-8')
    if 'def _negotiated_interest(snapshot):' in original_policy:
        raise SystemExit('Payment editor patch is already applied. No changes made.')
    try:
        new_policy = build_policy(original_policy)
        new_ui = build_ui(original_ui)
        compile(new_policy, str(POLICY), 'exec')
        compile(new_ui, str(UI), 'exec')
    except (RuntimeError, SyntaxError) as exc:
        raise SystemExit(f'ERROR: {exc}') from None
    for target, contents in ((POLICY,new_policy),(UI,new_ui)):
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix='.payment_edit_', delete=False, newline='\n') as temp:
            temp.write(contents)
            newpath = temp.name
        os.replace(newpath, target)
    print('Updated only contracts/commission_policy.py and contracts/ui.py')
    print('Payment edits now save terms and regenerate the payment clauses in one action.')
    print('Run the contract test suite before committing.')

if __name__ == '__main__':
    main()
