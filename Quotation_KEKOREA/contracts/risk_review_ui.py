"""Streamlit extension for review pagination, three editable alternatives and live document preview.

Presentation-only: approval still delegates to the established proposal/revision UI.
"""
from copy import deepcopy
import math
import streamlit as st

from Quotation_KEKOREA.contracts.library import search_library
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError
from Quotation_KEKOREA.contracts.risk_review_workspace import (
    PROTECTED_SENTENCES, PAGE_SIZE, page_items, preview_proposal,
    replace_variables, review_full_contract, suggest_alternatives,
)


def _select(key, idx):
    st.session_state[key] = idx


def _variable_update(edited_key, template, variable_keys):
    values = {name: st.session_state.get(key, '') for name, key in variable_keys.items()}
    st.session_state[edited_key] = replace_variables(template, values)


def render_risk_review(repo, snapshot, state_key, env):
    contract_id = snapshot['contract_id']
    revision = snapshot['revision']
    review_key = f'contract_rag_risk_{contract_id}'
    preview_key = f'contract_risk_preview_{contract_id}'
    review_state = st.session_state.get(review_key)
    if review_state and review_state.get('revision') != revision:
        st.session_state.pop(review_key, None)
        review_state = None
    preview_state = st.session_state.get(preview_key)
    if preview_state and preview_state.get('revision') != revision:
        st.session_state.pop(preview_key, None)
        preview_state = None
    with st.expander('AI 핵심 위험 검토 · 필요할 때 실행', expanded=False):
        st.caption('전체 계약 조항 검토 · 페이지당 최대 5건 · 수정 문장 3개 · 사용자가 비교·승인한 뒤 revision 저장')
        st.caption('AI 제안은 국제계약의 통계적 평균이나 법률 자문이 아니며, 사실·법률상 적합성은 별도 확인해야 합니다.')
        if st.button('현재 초안의 전체 핵심 위험 검토', key=f'rag_review_run_{contract_id}_{revision}'):
            try:
                parts = [str(s.get('text') or '') for c in snapshot.get('clauses', []) for s in c.get('sentences', [])]
                result = search_library(repo, snapshot, ' '.join(parts)[:6000], env=env)
                with st.spinner('전체 조항을 나누어 검토하고 있습니다...'):
                    findings = review_full_contract(snapshot, result.get('sources', []), env=env)
                st.session_state[review_key] = {
                    'revision': revision, 'findings': findings,
                    'sources': result.get('sources', []), 'notices': result.get('notices', []),
                    'alternatives': {},
                }
                st.session_state[f'risk_page_{contract_id}_{revision}'] = 1
                st.session_state[f'risk_selected_{contract_id}_{revision}'] = 0
                st.rerun()
            except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                st.error(str(exc))
        if not review_state:
            return
        for notice in review_state.get('notices', []):
            st.caption(str(notice))
        findings = review_state.get('findings', [])
        if not findings:
            st.success('표시할 핵심 위험을 찾지 못했습니다. 법률 검토가 불필요하다는 뜻은 아닙니다.')
            return
        page_key = f'risk_page_{contract_id}_{revision}'
        selection_key = f'risk_selected_{contract_id}_{revision}'
        page = page_items(findings, st.session_state.get(page_key, 1))
        st.session_state[page_key] = page['page']
        st.markdown('#### AI 핵심 위험 검토')
        a, b = st.columns(2)
        with a:
            st.metric('전체 검토 항목', f"{page['total']}건")
        with b:
            st.metric('현재 페이지', f"{page['page']} / {page['pages']}")
        for index, finding in page['items']:
            active = (st.session_state.get(selection_key, 0) == index-1)
            severity = {'high':'높음', 'medium':'보통', 'low':'낮음'}.get(finding.get('severity'),'검토')
            with st.container(border=True):
                left, right = st.columns([8, 2], vertical_alignment='center')
                with left:
                    label = f"{'◉' if active else '○'}  {index}. {finding['title']}"
                    if st.button(label, key=f'risk_pick_{contract_id}_{revision}_{index}', use_container_width=True):
                        st.session_state[selection_key] = index-1
                        st.rerun()
                with right:
                    st.caption(severity)
                st.caption(_clause_title(snapshot, finding['sentence_id']))
        nav_cols = st.columns([1] + [1]*page['pages'] + [1]) if page['pages'] <= 9 else st.columns(3)
        if page['pages'] <= 9:
            with nav_cols[0]:
                if st.button('◀', key=f'risk_prev_{contract_id}', disabled=page['page'] == 1):
                    _switch_page(st.session_state, page_key, selection_key, page['page']-1)
                    st.rerun()
            for target in range(1, page['pages'] + 1):
                with nav_cols[target]:
                    if st.button(str(target), key=f'risk_nav_{contract_id}_{target}',
                                 type='primary' if target==page['page'] else 'secondary'):
                        _switch_page(st.session_state, page_key, selection_key, target)
                        st.rerun()
            with nav_cols[-1]:
                if st.button('▶', key=f'risk_next_{contract_id}', disabled=page['page']==page['pages']):
                    _switch_page(st.session_state, page_key, selection_key, page['page']+1)
                    st.rerun()
        else:
            with nav_cols[0]:
                if st.button('이전', key=f'risk_prev_{contract_id}', disabled=page['page']==1):
                    _switch_page(st.session_state, page_key, selection_key, page['page']-1)
                    st.rerun()
            with nav_cols[1]:
                target = st.selectbox('페이지', list(range(1,page['pages']+1)),
                                      index=page['page']-1, key=f'risk_jump_{contract_id}_{revision}')
                if target != page['page']:
                    _switch_page(st.session_state, page_key, selection_key, target)
                    st.rerun()
            with nav_cols[2]:
                if st.button('다음', key=f'risk_next_{contract_id}', disabled=page['page']==page['pages']):
                    _switch_page(st.session_state, page_key, selection_key, page['page']+1)
                    st.rerun()
        selected = st.session_state.get(selection_key, (page['page']-1)*PAGE_SIZE)
        if not (page['page']-1)*PAGE_SIZE <= selected < min(page['page']*PAGE_SIZE, len(findings)):
            selected = (page['page']-1)*PAGE_SIZE
        finding = findings[selected]
        sentence_id = finding['sentence_id']
        source = _sentence_text(snapshot, sentence_id)
        st.divider()
        st.markdown('#### 선택한 위험 항목')
        st.markdown(f"**{finding['title']}**")
        st.caption(f"{selected+1} / {len(findings)} · {finding.get('reason','')}")
        st.markdown('**현재 계약서 원문**')
        st.info(source)
        with st.expander('검토 대상 조항 및 근거', expanded=False):
            st.caption(f'문장 ID: {sentence_id}')
            st.write(source)
            for source_id in finding.get('source_ids', []):
                reference = next((x for x in review_state.get('sources', [])
                                  if x.get('id') == source_id), None)
                if reference:
                    st.caption(f"참고: {reference.get('title', '')} · {reference.get('locator', '')}")
        if st.button('이 조항을 선택하여 수정 메모 작성',
                     key=f'risk_select_note_{contract_id}_{revision}_{sentence_id}'):
            st.session_state[f'contract_selected_sentence_{contract_id}'] = sentence_id
            st.toast('BOX 3의 해당 문장에서 기존 메모 기능을 사용할 수 있습니다.')
            st.rerun()
        if sentence_id in PROTECTED_SENTENCES:
            st.warning('이 문장은 자동 생성되는 커미션 지급 조항입니다. BOX 2 수수료 지급조건에서 변경해 주세요.')
            return
        options_key = f'risk_alternatives_{contract_id}_{revision}_{sentence_id}'
        alternatives = st.session_state.get(options_key)
        if not alternatives:
            # Keep the exact selection -> three options flow from the approved mockup.
            # Lazily generate only the selected finding; cache through Streamlit reruns.
            try:
                with st.spinner('AI 추천 수정 문장 3개를 생성하고 있습니다...'):
                    alternatives = suggest_alternatives(snapshot, finding, env=env)
                st.session_state[options_key] = alternatives
            except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                st.error(f'이 항목의 추천 문장을 생성하지 못했습니다: {exc}')
                return
        choice_key = f'risk_variant_{contract_id}_{revision}_{sentence_id}'
        choice = st.session_state.get(choice_key, 0)
        if not isinstance(choice, int) or choice not in range(3):
            choice = 0
        st.markdown('**AI 추천 수정 문장 3개**')
        variable_keys = {var['key']:f'risk_var_{contract_id}_{revision}_{sentence_id}_{var["key"]}'
                         for var in alternatives['variables']}
        for var in alternatives['variables']:
            st.session_state.setdefault(variable_keys[var['key']], var['value'])
        values = {name: st.session_state[key] for name, key in variable_keys.items()}
        for index, option in enumerate(alternatives['options']):
            picked = (choice==index)
            with st.container(border=True):
                st.markdown(f"**{'◉' if picked else '○'} 추천안 {index+1} · {option['label']}**")
                st.write(replace_variables(option['template'], values))
                if st.button('이 추천안 선택', key=f'risk_choose_{contract_id}_{revision}_{sentence_id}_{index}',
                             disabled=picked):
                    st.session_state[choice_key] = index
                    st.session_state[f'risk_edited_{contract_id}_{revision}_{sentence_id}'] = replace_variables(option['template'], values)
                    st.rerun()
        st.markdown('**가변 정보 직접 수정**')
        st.caption('선택 문구에 등장하는 숫자·법인명 등을 수정할 수 있습니다.')
        if variable_keys:
            cols = st.columns(min(3, len(variable_keys)))
            for i, var in enumerate(alternatives['variables']):
                with cols[i%len(cols)]:
                    st.text_input(var['label'], key=variable_keys[var['key']],
                                  on_change=_variable_update,
                                  args=(f'risk_edited_{contract_id}_{revision}_{sentence_id}',
                                        alternatives['options'][choice]['template'], variable_keys))
        else:
            st.caption('이 추천안에는 별도로 추출된 가변 정보가 없습니다. 아래에서 전체 문장을 직접 수정할 수 있습니다.')
        edited_key = f'risk_edited_{contract_id}_{revision}_{sentence_id}'
        st.session_state.setdefault(edited_key, replace_variables(alternatives['options'][choice]['template'], values))
        st.text_area('최종 문장 직접 편집', key=edited_key, height=140)
        pending = st.session_state.get('contract_pending_proposal') or {}
        if pending.get('contract_id') == contract_id:
            st.caption('다른 수정안이 열려 있습니다. 비교·승인 또는 취소 후 새 적용을 진행해 주세요.')
        if st.button('추천 문장 적용', type='primary',
                     disabled=(not str(st.session_state.get(edited_key,'')).strip() or pending.get('contract_id')==contract_id),
                     key=f'risk_apply_preview_{contract_id}_{revision}_{sentence_id}'):
            preview_state = st.session_state.get(preview_key) or {'revision':revision, 'sentences':{}}
            preview_state['sentences'][sentence_id] = st.session_state[edited_key].strip()
            st.session_state[preview_key] = preview_state
            st.toast('선택한 문장을 BOX 3 미리보기에 반영했습니다. 계약서에 확정 저장되지는 않았습니다.')
            st.rerun()
        previews = (st.session_state.get(preview_key) or {}).get('sentences', {})
        if previews:
            st.divider()
            st.markdown('#### BOX 3 · 계약서 초안 미리보기')
            st.caption(f'수정 미리보기 {len(previews)}건 · 승인 전에는 기존 계약서가 유지됩니다.')
            with st.container(border=True):
                st.markdown(f"### {snapshot.get('title') or 'CONTRACT'}")
                st.markdown(f"**{_clause_title(snapshot, sentence_id)}**")
                st.write(previews.get(sentence_id, source))
                st.caption('선택한 수정 문장이 미리보기에 반영됐습니다.')
            st.caption('선택한 위험 수정안은 아래 최종 수정 요청 버튼에서 문장 메모와 함께 비교·승인합니다.')


def _switch_page(state, page_key, selected_key, page):
    state[page_key] = page
    state[selected_key] = (page-1)*PAGE_SIZE


def _sentence_text(snapshot, sentence_id):
    for clause in snapshot.get('clauses', []):
        for sentence in clause.get('sentences', []):
            if sentence.get('id') == sentence_id:
                return sentence.get('text', '')
    return ''


def _clause_title(snapshot, sentence_id):
    for clause in snapshot.get('clauses', []):
        if any(s.get('id') == sentence_id for s in clause.get('sentences', [])):
            return str(clause.get('title') or '계약 조항')
    return '계약 조항'
