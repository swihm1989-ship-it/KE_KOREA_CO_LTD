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


def show_library_sources(sources):
    if not sources:
        return
    with st.expander('이번 계약에 참고한 공통 샘플', expanded=False):
        st.caption('검토된 참고 메모입니다. 현재 거래 조건과 지급 정책이 우선하며, 원문 조건이나 법적 유효성을 자동 적용하지 않습니다.')
        for source in sources:
            st.write(f"{source['title']} · {source['locator']} · v{source['revision']}")
            st.caption(source['topic'])
            st.write(source['text'])


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
