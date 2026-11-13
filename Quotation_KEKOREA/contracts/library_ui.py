"""Sample administration is separate from public contract drafting."""
import hashlib
import hmac
import json

import streamlit as st

from Quotation_KEKOREA.contracts.library import (
    publish_sample, read_manifest, register_sample, set_sample_active,
    backfill_library_embeddings, library_embedding_status,
)
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError
from Quotation_KEKOREA.contracts.promote_reference import promote_contract_reference
from Quotation_KEKOREA.contracts.contextual_rag import (
    approve_source_excerpts, index_private_original, private_index, _SENSITIVE,
    restore_private_extraction_bundle,
)


def show_library_sources(sources, source_comparison=None):
    if not sources:
        return
    with st.expander('이번 계약에 참고한 공통 샘플', expanded=False):
        st.caption('검토된 참고 메모입니다. 현재 거래 조건과 지급 정책이 우선하며, 원문 조건이나 법적 유효성을 자동 적용하지 않습니다.')
        for source in sources:
            st.write(f"{source['title']} · {source['locator']} · v{source['revision']}")
            st.caption(source['topic'])
            st.write(source['text'])
            if source.get('selected_reason'):
                st.caption('여러 계약서 비교 후 선택한 이유: ' + source['selected_reason'])
            if source.get('source_section_id'):
                st.caption('원본 조항과 SHA-256을 검증한 승인 참고 문구')
        decisions = (source_comparison or {}).get('decisions') or []
        if decisions:
            st.markdown('##### 여러 계약서 조항 비교 및 선택 근거')
            st.dataframe([
                {
                    '검토 주제': d['topic_key'],
                    '선택한 근거 ID': d['selected_id'],
                    '선택 이유': d['reason'],
                    '제외한 후보': len(d.get('alternatives') or []),
                    '재검토할 충돌': ' / '.join(d.get('conflicts') or []) or '없음',
                } for d in decisions
            ], hide_index=True)


def render_library_admin(repo, env):
    with st.expander('공통 샘플 라이브러리 관리', expanded=False):
        token = str(env.get('CONTRACT_LIBRARY_ADMIN_TOKEN') or '')
        if not token:
            st.caption('샘플 등록·원문 열람·승인은 서버의 별도 관리 키 설정 후 사용할 수 있습니다. 계약 작성에는 관리 키가 필요하지 않습니다.')
            return
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        if st.session_state.get('_sample_admin_session') != fingerprint:
            with st.form('library_admin_login'):
                candidate = st.text_input('샘플 관리 키', type='password', key='_sample_admin_password')
                login = st.form_submit_button('관리 시작')
            if login:
                if hmac.compare_digest(candidate, token):
                    st.session_state['_sample_admin_session'] = fingerprint
                    st.rerun()
                st.error('샘플 관리 키를 확인해 주세요.')
            return
        st.session_state.pop('_sample_admin_password', None)
        if st.button('샘플 관리 종료', key='library_admin_logout'):
            st.session_state.pop('_sample_admin_session', None)
            st.rerun()
        st.caption('원본과 추출 내용은 관리자 전용입니다. 검색에는 승인한 익명화 참고 메모만 사용됩니다.')
        try:
            all_samples = repo.list_library_records()
            approved_samples = [
                r for r in all_samples
                if r.get('extraction_status') == 'library_approved'
            ]
            ready_text = sum(bool(str(r.get('extracted_text') or '').strip())
                             for r in approved_samples)
            indexed_samples = [
                private_index(r) for r in approved_samples if private_index(r)
            ]
            indexed_clauses = sum(len(idx.get('sections') or [])
                                  for idx in indexed_samples)
            st.caption(
                f"승인 문서 원문 저장 {ready_text}/{len(approved_samples)}개 · "
                f"비공개 조항 인덱스 {len(indexed_samples)}/{len(approved_samples)}개 · "
                f"조항 {indexed_clauses}개"
            )
        except ContractRepositoryError as exc:
            st.warning('원문 복구 상태 확인 실패: ' + str(exc)[:160])
        try:
            stats = library_embedding_status(
                repo.list_library_records(approved_only=True),
                model=env.get('CONTRACT_LIBRARY_EMBEDDING_MODEL') or 'text-embedding-3-small',
            )
            st.caption(
                f"공통 RAG 벡터 · 승인 문서 {stats['documents']}개 · "
                f"임베딩 {stats['embedded']}/{stats['chunks']}개 · 미적용 {stats['missing']}개"
            )
            if stats['missing'] and st.button(
                '승인 참고 조항의 누락 임베딩 생성',
                key='library_embedding_backfill',
                help='현재 승인된 익명화 참고 메모만 OpenAI API로 전송합니다. '
                     '원본 계약서·계좌·직인·미승인 문서는 전송하지 않습니다.',
            ):
                with st.spinner('누락 벡터를 생성하고 유효성을 검사합니다...'):
                    result = backfill_library_embeddings(repo, env=env)
                st.success(
                    f"임베딩 저장: {result['chunks_updated']}개 / "
                    f"문서 {result['documents_updated']}개 · "
                    f"남은 미적용 {result['remaining']}개"
                )
                if result['failed_documents']:
                    st.warning(
                        f"동시 변경 등으로 {result['failed_documents']}개 문서는 저장하지 못했습니다. "
                        "기존 원문·승인은 유지됩니다."
                    )
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.warning('RAG 임베딩 상태 확인 또는 생성 실패: ' + str(exc)[:220])
        with st.expander('기존 ZIP에서 추출했던 원문 텍스트 복구', expanded=False):
            st.caption(
                '대화에서 전달된 계약서 ZIP의 이전 텍스트 추출 결과(JSON)를 업로드해 '
                '원본 SHA-256을 확인한 후 비공개 extracted_text에 저장합니다. '
                '기존 본문을 덮어쓰지 않으며 이 작업은 RAG 재사용 승인과 별개입니다.'
            )
            previous_extraction = st.file_uploader(
                '개인정보가 포함될 수 있는 원문 복구 JSON · 관리자 전용',
                type=['json'], key='private_extraction_restore_json',
            )
            restore_confirm = st.checkbox(
                '모든 자료가 본인 소유이며 기존 저장 원본과 대조해 비공개 복원하는 데 동의합니다.',
                key='private_extraction_restore_confirm',
            )
            if st.button('원문 텍스트 SHA 검증 후 DB 복구',
                         disabled=not (previous_extraction and restore_confirm),
                         key='private_extraction_restore_execute'):
                if previous_extraction.size > 512 * 1024:
                    raise ValueError('복구 JSON은 512KB를 초과할 수 없습니다.')
                bundle = json.loads(previous_extraction.getvalue().decode('utf-8'))
                with st.spinner('원본 파일과 추출 결과를 비교하고 있습니다...'):
                    restored = restore_private_extraction_bundle(repo, bundle)
                st.success(
                    f"본문 복구 {restored['restored']}개 · "
                    f"이미 저장됨 {restored['unchanged']}개 · "
                    f"확인 필요 {restored['skipped']}개"
                )
                for reason in restored['reasons'][:8]:
                    st.warning(reason)
        # Hierarchical source indexing is private until individual excerpts
        # are explicitly reviewed and approved; no raw originals reach the AI.
        with st.expander('원본 계약서 조항 인덱스 · 관리자 검증', expanded=False):
            records_for_index = repo.list_library_records()
            failed_ids = st.session_state.setdefault('_private_index_skipped', [])
            candidates = [
                r for r in records_for_index
                if not private_index(r)
                and str(r.get('filename') or '').lower().endswith(('.pdf', '.docx', '.hwp', '.xlsx'))
                and str(r['id']) not in failed_ids
            ]
            completed = sum(bool(private_index(r)) for r in records_for_index)
            st.caption(
                f"검증된 원문 조항 색인 {completed}개 / 공통 원본 {len(records_for_index)}개 · "
                f"이번 실행 대상 {len(candidates)}개"
            )
            if st.button('기존 원본 조항 추출 및 위치 기록 (최대 5개)',
                         disabled=not candidates, key='private_context_index_batch'):
                ok, failures = [], []
                for candidate in candidates[:5]:
                    try:
                        result = index_private_original(repo, str(candidate['id']))
                        ok.append((candidate['filename'], result['sections']))
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        failures.append((candidate['filename'], str(exc)[:160]))
                        failed_ids.append(str(candidate['id']))
                if ok:
                    st.success(f"원본 검증·비공개 조항 인덱싱: {len(ok)}개 완료")
                for name, reason in failures:
                    st.warning(f"{name}: {reason}")
                st.rerun()
            if failed_ids and st.button('미완료 문서 다시 확인', key='private_index_retry'):
                st.session_state['_private_index_skipped'] = []
                st.rerun()
            st.caption(
                '서명·거래금액이 포함된 원문은 서버의 비공개 인덱스에만 저장됩니다. '
                '다른 계약서의 AI 검색에 넣기 전에 아래에서 익명화 문구를 직접 검토·승인해야 합니다.'
            )
        # Explicitly promote a previously saved per-contract reference. Admin-only.
        # No source deletion and no AI retrieval before reviewed guidance approval.
        current_contract_id = st.session_state.get('contract_active_id')
        if current_contract_id:
            with st.expander('현재 계약의 참고자료를 공통 라이브러리에 등록', expanded=False):
                references = [r for r in repo.contract_references(current_contract_id)
                              if str(r.get('filename') or '').lower().endswith(('.pdf', '.docx'))]
                if not references:
                    st.caption('현재 계약에 등록된 PDF/DOCX 참고자료가 없습니다.')
                else:
                    options = {str(r['id']): r for r in references}
                    with st.form(f'promote_contract_reference_{current_contract_id}'):
                        selected = st.selectbox('공통 등록할 기존 참고자료', list(options),
                                                format_func=lambda v: options[v].get('filename', v))
                        common_title = st.text_input('공통 라이브러리 표시 제목 (거래처·개인정보 제외)')
                        common_types = st.multiselect('재사용할 계약 유형',
                                                      ['sale', 'trade_commission', 'investment_commission'])
                        common_language = st.selectbox('참고자료 언어', ['ko', 'en'])
                        confirmed = st.checkbox('회사 공통 재사용에 적합한 자료이며, 원본은 관리자만 열람하고 승인 전 AI 검색에 사용하지 않는 데 동의합니다.')
                        do_promote = st.form_submit_button('공통 라이브러리에 승인 대기로 등록')
                    if do_promote:
                        try:
                            if not confirmed or not common_title.strip() or not common_types:
                                raise ValueError('명시적 동의, 공통 제목, 계약 유형을 모두 입력해 주세요.')
                            record = promote_contract_reference(
                                repo, current_contract_id, selected, title=common_title,
                                contract_types=common_types, language=common_language)
                            st.success('공통 라이브러리에 승인 대기로 등록했습니다. 아래에서 익명화 메모를 검토·승인해야 다른 계약의 AI 검색에 활용됩니다.')
                            st.rerun()
                        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                            st.error(str(exc))
        with st.form('library_upload'):
            uploaded = st.file_uploader('새 공통 샘플 여러 개 (PDF/DOCX/HWP5)', type=['pdf', 'docx', 'hwp'], accept_multiple_files=True)
            title = st.text_input('공개 참고 제목', help='기존 거래처나 개인 이름을 넣지 마세요.')
            kinds = st.multiselect('참고할 계약 유형', ['sale', 'trade_commission', 'investment_commission'])
            language = st.selectbox('샘플 언어', ['ko', 'en'])
            register = st.form_submit_button('비공개 원본 등록 (승인 대기)')
        try:
            if register:
                if not uploaded or not title.strip() or not kinds:
                    raise ValueError('파일·공개 제목·계약 유형을 입력해 주세요.')
                successes, failures = [], []
                for file in uploaded:
                    try:
                        sample_title = title.strip() if len(uploaded) == 1 else file.name.rsplit('.', 1)[0][:160]
                        record = register_sample(repo, file.getvalue(), file.name, title=sample_title,
                                                 contract_types=kinds, language=language)
                        successes.append(file.name)
                    except (ValueError, RuntimeError, ContractRepositoryError) as exc:
                        failures.append((file.name, str(exc)))
                if successes:
                    st.success(f'{len(successes)}개 원본 저장 및 해시 검증 완료. AI 검색에는 승인 후 반영됩니다.')
                for name, reason in failures:
                    st.error(f'{name}: {reason}')
                if successes and not failures:
                    st.rerun()
            records = repo.list_library_records()
            managed = []
            for record in records:
                try:
                    managed.append((record, read_manifest(record)))
                except ValueError:
                    continue
            if not managed:
                st.info('등록된 공통 샘플이 없습니다.')
                return
            by_id = {record['id']: (record, manifest) for record, manifest in managed}
            selected = st.selectbox('관리할 샘플', list(by_id),
                                    format_func=lambda value: by_id[value][1].title)
            record = repo.get_library_record(selected)
            manifest = read_manifest(record)
            st.write(f"승인: {manifest.approved} · 활성: {manifest.active} · 버전: {manifest.revision}")
            index = private_index(record)
            with st.expander('원본 조항 문맥 확인 및 개별 승인', expanded=False):
                if not index:
                    st.info('위의 원본 조항 인덱스를 먼저 생성해 주세요.')
                    if st.button('선택한 문서의 원본 조항 인덱스 만들기',
                                 key=f'index_selected_{selected}'):
                        result = index_private_original(repo, selected)
                        st.success(f"조항 {result['sections']}개 추출: {result['extraction_status']}")
                        st.rerun()
                else:
                    sections = index.get('sections') or []
                    st.caption(
                        f"원문 검증: SHA-256 일치 · 추출 상태: "
                        f"{index.get('extraction_status')} · "
                        f"조항 수: {len(sections)} · "
                        f"미추출 페이지: {len(index.get('unread_pages') or [])}"
                    )
                    by_section = {sec['id']: sec for sec in sections}
                    selected_ids = st.multiselect(
                        '승인할 원문 조항 (최대 4개씩)',
                        list(by_section),
                        format_func=lambda sid: (
                            by_section[sid]['locator'] + ' · '
                            + (by_section[sid]['heading'] or by_section[sid]['text'][:35])
                        ),
                        max_selections=4,
                        key=f'source_section_choose_{selected}',
                    )
                    if selected_ids:
                        first = next(i for i, sec in enumerate(sections)
                                     if sec['id'] == selected_ids[0])
                        st.caption('선택한 첫 조항의 원문 앞뒤 문맥 · 관리자만 열람')
                        for pos in range(max(0, first-1), min(len(sections), first+2)):
                            sec = sections[pos]
                            st.text_area(
                                f"{'선택 조항' if pos == first else '인접 조항'} · {sec['locator']}",
                                value=sec['text'], height=145, disabled=True,
                                key=f'raw_hierarchy_{selected}_{manifest.revision}_{pos}',
                            )
                        review_rows = [{
                            'section_id': sid,
                            'topic': (by_section[sid]['heading'] or
                                      '계약서 원문 조항 구조 검토')[:150],
                            'text': _SENSITIVE.sub('[비공개 정보 제거]', by_section[sid]['text'])[:2500],
                        } for sid in selected_ids]
                        fingerprint = hashlib.sha256(
                            (selected + ':'.join(selected_ids)).encode()
                        ).hexdigest()[:14]
                        with st.form(f'contextual_approve_{selected}_{fingerprint}'):
                            edited = st.text_area(
                                '원문에 근거한 익명화 조항 JSON · 각 text에서 당사자명·직책·주소·'
                                '계좌·서명·개별 금액과 비율을 제거하세요.',
                                value=json.dumps(review_rows, ensure_ascii=False, indent=2),
                                height=300,
                            )
                            confirmed = st.checkbox(
                                '원문 전체 문맥 및 다른 조항과의 관계를 확인했고, '
                                '거래처·개인정보·금액·비율이 제거된 문구만 공통 AI 참고로 승인합니다.'
                            )
                            publish_context = st.form_submit_button(
                                '원문 근거 조항을 RAG에 승인 등록'
                            )
                        if publish_context:
                            if not confirmed:
                                raise ValueError('원문·익명화 검토 확인을 먼저 체크해 주세요.')
                            rows = json.loads(edited)
                            if (not isinstance(rows, list) or
                                    {row.get('section_id') for row in rows} != set(selected_ids)):
                                raise ValueError('선택한 원문 조항만 승인할 수 있습니다.')
                            result = approve_source_excerpts(
                                repo, selected, rows, explicit_approval=True, env=env,
                            )
                            st.success(
                                f"원본 근거 조항 {result['chunks_added']}개 RAG 승인 · "
                                f"즉시 임베딩 {result['embedded']}개"
                            )
                            st.rerun()
            with st.expander('관리자용 원문 텍스트와 출처'):
                st.text(record.get('extracted_text') or '텍스트 추출 결과가 없습니다.')
                st.dataframe([{'location': loc.get('locator'), 'text': loc.get('text')}
                              for loc in record['source_locations'] if loc.get('locator')], hide_index=True)
            initial = [{'locator': c.locator, 'topic': c.topic, 'text': c.text} for c in manifest.chunks]
            if not initial:
                first = next((loc for loc in record['source_locations'] if loc.get('locator')), {})
                initial = [{'locator': first.get('locator', ''), 'topic': '', 'text': ''}]
            with st.form(f'library_review_{selected}_{manifest.revision}'):
                reviewed = st.text_area('검토된 참고 메모 JSON', value=json.dumps(initial, ensure_ascii=False, indent=2),
                                        height=260, help='locator=위 원문 위치, topic=주제, text=새로 작성한 익명화 참고 메모')
                confirmation = st.checkbox('거래처·개인정보·계좌·기존 금액과 비율을 제거하고 참고용으로 새로 작성한 메모임을 확인합니다.')
                approve = st.form_submit_button('메모 승인 및 검색 인덱스 갱신')
            if approve:
                if not confirmation:
                    raise ValueError('참고 메모의 익명화와 검토 여부를 확인해 주세요.')
                chunks = json.loads(reviewed)
                if not isinstance(chunks, list):
                    raise ValueError('참고 메모는 JSON 배열이어야 합니다.')
                result = publish_sample(repo, selected, chunks, env=env)
                for message in result['notices']:
                    st.warning(message)
                st.success('메모가 승인되었습니다. 다음 계약 분석부터 참고 검색에 포함됩니다.')
            if st.button('검색에서 제외' if manifest.active else '검색에 다시 포함', key=f'library_toggle_{selected}'):
                set_sample_active(repo, selected, not manifest.active)
                st.rerun()
        except (ValueError, RuntimeError, ContractRepositoryError) as exc:
            st.error(str(exc))
