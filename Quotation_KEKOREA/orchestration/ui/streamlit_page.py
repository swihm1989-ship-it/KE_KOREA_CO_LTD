"""Run from the repository root:

    streamlit run Quotation_KEKOREA/orchestration/ui/streamlit_page.py

Mailbox supports explicit read-only Whois access. Sample workflows remain separate; no sends.
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

# Streamlit direct-file mode needs the project root on sys.path.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from Quotation_KEKOREA.orchestration.workflows.mock_workflow import (
    SAMPLE_MESSAGES, MockMessage, approve_mock_document, approve_mock_email,
    edit_mock_document, is_mock_approval_current, start_mock_run, update_mock_email,
)

st.set_page_config(page_title="KE KOREA | Orchestration Demo", page_icon="📑", layout="wide")

# FAIL-CLOSED: protects every menu before session state, sidebar, or database access.
from Quotation_KEKOREA.orchestration.security.auth_gate import require_authentication
_authenticated_principal = require_authentication(st)

# Explicitly enable metadata recording only after authorization, in Master.
from Quotation_KEKOREA.observability.runtime import configure as configure_observability
from Quotation_KEKOREA.orchestration.workflows.document_assets import document_export_env
import os
_telemetry_store = configure_observability(document_export_env(st.secrets, os.environ))


from Quotation_KEKOREA.orchestration.ui.ke_theme import STYLE, logo_path, header_html
st.markdown(STYLE, unsafe_allow_html=True)

if "mock_runs" not in st.session_state:
    st.session_state.mock_runs = {}
if "mock_selected" not in st.session_state:
    st.session_state.mock_selected = SAMPLE_MESSAGES[0].id
if "mock_notes" not in st.session_state:
    st.session_state.mock_notes = []

with st.sidebar:
    logo = logo_path()
    if logo.exists():
        st.image(str(logo), use_container_width=True)
    st.markdown("### MASTER GRAPH")
    st.caption("KE KOREA CO. LTD · AI WORKSPACE")
    st.markdown("---")
# A mailbox fragment requests a full rerun using a session-state flag.
# Consume this before the sidebar radio exists. Do NOT import a newly added
# workflow symbol here: Streamlit hot deployments may cache an older module and
# a top-level ImportError would otherwise prevent the entire Master from loading.
if st.session_state.pop("master_mail_navigation_pending", False):
    st.session_state["master_page"] = "AI 업무 요청"
page = st.sidebar.radio("업무 메뉴", ["시장 뉴스", "업무 대시보드", "메일함", "AI 업무 요청", "통합 업무 흐름", "문서 검토", "발송 대기", "엔진 사전검증", "문서 초안 미리보기", "저장된 계약서", "실행 기록", "관리자 모니터링"], label_visibility="collapsed", key="master_page")
st.sidebar.divider()
st.sidebar.caption("접속 계정: " + _authenticated_principal)
if st.sidebar.button("로그아웃", key="master_logout"):
    st.logout()
st.sidebar.caption("메일함은 별도 허용 계정만 읽을 수 있습니다. 실제 메일 발송은 비활성 상태입니다.")

def _message() -> MockMessage:
    return next((m for m in SAMPLE_MESSAGES if m.id == st.session_state.mock_selected), SAMPLE_MESSAGES[0])

def _selected_run():
    return st.session_state.mock_runs.get(st.session_state.mock_selected)

def _save(run):
    st.session_state.mock_runs[run.source_id] = run

def _start(message: MockMessage):
    run = start_mock_run(message)
    _save(run)
    st.session_state.mock_selected = message.id
    return run

st.markdown(
    header_html(
        "MASTER GRAPH",
        "KE KOREA 업무 자동화 · AI 업무 요청, 무역서류 및 계약서 검토",
        eyebrow="KE KOREA · AI WORKSPACE",
    ),
    unsafe_allow_html=True,
)
st.caption("독립 업무 화면 · 기존 KE KOREA 계약서 시스템은 변경하지 않습니다.")
col_a, col_b, col_c, col_d = st.columns(4)
runs = list(st.session_state.mock_runs.values())
col_a.metric("샘플 메일", len(SAMPLE_MESSAGES))
col_b.metric("진행 중 작업", sum(r.status != "ready_for_future_integration" for r in runs))
col_c.metric("문서 검토 대기", sum(r.status == "awaiting_document_approval" for r in runs))
col_d.metric("발송 대기(모의)", sum(r.status == "ready_for_future_integration" for r in runs))
st.divider()

if page == "관리자 모니터링":
    from Quotation_KEKOREA.orchestration.ui.monitoring_page import render_monitoring
    render_monitoring(_authenticated_principal, _telemetry_store)

elif page == "시장 뉴스":
    from Quotation_KEKOREA.orchestration.ui.market_news_page import render_market_news
    render_market_news()

elif page == "메일함":
    from Quotation_KEKOREA.orchestration.ui.mailbox_page import render_mailbox
    render_mailbox(_authenticated_principal)

elif page == "업무 대시보드":
    st.subheader("받은편지함 · Demo inbox")
    st.caption("실제 후이즈메일을 읽지 않습니다. 모든 주소는 example.test 테스트 주소입니다.")
    search = st.text_input("메일 검색", placeholder="제목 또는 발신자")
    matched = [m for m in SAMPLE_MESSAGES if search.lower() in (m.subject+" "+m.sender).lower()]
    if not matched:
        st.info("일치하는 샘플 메일이 없습니다.")
    for mail in matched:
        with st.container(border=True):
            a, b = st.columns([5, 1])
            a.markdown(f"**{mail.subject}**")
            a.caption(f"{mail.sender} · {mail.received_at}")
            a.write(mail.body)
            if b.button("업무 시작", key=f"start-{mail.id}", type="primary"):
                _start(mail)
                st.success("샘플 업무 생성 완료. 문서 검토 메뉴에서 확인하세요.")
    if page == "업무 대시보드":
        st.subheader("최근 샘플 작업")
        if not runs:
            st.info("아직 샘플 작업이 없습니다. 위 메일의 업무 시작 버튼을 눌러주세요.")
        for run in runs:
            st.write(f"**{run.subject}** · {run.status} · {', '.join(t.kind for t in run.tasks) or '분류 필요'}")

elif page == "AI 업무 요청":
    from Quotation_KEKOREA.orchestration.ui.ai_intake_page import render_ai_intake
    render_ai_intake(_authenticated_principal)

elif page == "통합 업무 흐름":
    st.subheader("요청부터 문서·이메일 초안 검토까지")
    st.caption("키워드 기반 문서 분류 → 기존 엔진 검증 및 DRAFT 파일 생성 → 문서별 검토 → 이메일 초안 검토")
    st.warning("실제 AI API, 메일 수신·발송, 서명 및 최종 문서 발행은 미연결입니다. 테스트 데이터만 사용하세요.")
    from Quotation_KEKOREA.orchestration.workflows.unified_review import (
        new_request, prepare_documents, approve_document, set_email_draft,
        approve_email_review, verify_handoff,
    )
    demo_source = {"PI": {
        "document_type": "PI", "product_family": "solar_cell", "currency": "USD",
        "document_number": "DRAFT",
        "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Street"},
        "buyer": {"legal_name": "Demo Buyer LLC", "address": "Example Street"},
        "incoterms": "EXW Seoul", "payment_terms": "T/T",
        "items": [{"product_name": "M10 test cell", "quantity": "100", "unit": "PCS",
                   "unit_price": "0.20", "price_basis": "PCS", "price_source": "demo"}],
    }}
    instruction = st.text_input("업무 요청", value="PI 작성해줘", key="unified_instruction")
    candidates_text = st.text_area(
        "문서별 구조화 입력 (JSON, PI/PO/CI/PL/CONTRACT 키)",
        value=json.dumps(demo_source, ensure_ascii=False, indent=2),
        key="unified_candidates", height=250,
    )
    input_key = hashlib.sha256((instruction + "\\0" + candidates_text).encode("utf-8")).hexdigest()
    if st.button("요청 분류 및 DRAFT 파일 생성", key="unified_prepare", type="primary"):
        st.session_state.pop("unified_run", None)
        st.session_state.pop("unified_input_key", None)
        try:
            candidate_map = json.loads(candidates_text)
            if not isinstance(candidate_map, dict):
                raise ValueError("JSON 최상위 값은 문서별 입력 객체여야 합니다.")
            run = prepare_documents(new_request(instruction, candidate_map))
            st.session_state["unified_run"] = run
            st.session_state["unified_input_key"] = input_key
        except (ValueError, TypeError, KeyError) as exc:
            st.error(f"요청 처리 실패: {exc}")
    run = st.session_state.get("unified_run")
    stale = st.session_state.get("unified_input_key") != input_key
    if run and stale:
        st.error("요청문 또는 문서 입력값이 수정됐습니다. 새 DRAFT를 생성해야 하며 이전 승인은 사용할 수 없습니다.")
    if run and not stale:
        st.caption("분류된 문서: " + (", ".join(run.kinds) or "분류 불가") + " · " + run.status)
        if not run.kinds:
            st.info("문서 종류를 파악할 수 없습니다. PI, PO, CI, PL, 계약서 등을 명시하세요.")
        for task in run.documents:
            with st.container(border=True):
                st.markdown(f"**{task.kind} · {'검토 확인' if task.approved else '검토 대기'}**")
                if task.blockers:
                    st.error(f"확인 필요: {len(task.blockers)}건")
                    with st.expander("누락·미확정 조건"):
                        for issue in task.blockers:
                            st.write(issue)
                if task.files:
                    for fmt, file in task.files.items():
                        st.caption(f"{file['filename']} · SHA-256 {file['sha256']}")
                        st.download_button(f"{task.kind} DRAFT {fmt.upper()} 다운로드",
                                           data=file["content"], file_name=file["filename"],
                                           mime=file["mime"], key=f"unified_download_{task.kind}_{fmt}")
                if st.button(f"{task.kind} DRAFT 검토 확인", key=f"unified_approve_{task.kind}",
                             disabled=task.approved or bool(task.blockers) or not task.files):
                    try:
                        st.session_state["unified_run"] = approve_document(run, task.kind)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
        st.divider()
        st.markdown("#### 이메일 초안 검토")
        st.caption("이메일은 화면 검토만 가능하며 SMTP 발송 버튼은 제공하지 않습니다.")
        with st.form("unified_email_form"):
            recipient = st.text_input("수신자", value=run.email_to or "buyer@example.test")
            subject = st.text_input("제목", value=run.email_subject or "[DRAFT] Documents for review")
            body = st.text_area("본문", value=run.email_body or "안녕하세요. 첨부 예정 문서 검토를 요청드립니다. [DEMO]", height=110)
            submitted = st.form_submit_button("이메일 초안 저장")
        if submitted:
            st.session_state["unified_run"] = set_email_draft(run, recipient, subject, body)
            st.rerun()
        all_approved = bool(run.documents) and all(t.approved and not t.blockers for t in run.documents)
        if st.button("이메일 초안 최종 검토 확인", key="unified_email_approve",
                     type="primary", disabled=not all_approved or not run.email_to or run.email_approved):
            try:
                st.session_state["unified_run"] = approve_email_review(run)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if verify_handoff(run):
            st.success("문서 및 이메일 초안 검토 완료. 실제 발송 권한은 부여되지 않았습니다.")
        st.button("실제 이메일 발송 · 미연결", disabled=True)
        with st.expander("업무 이력"):
            for item in run.history:
                st.write(item)

elif page == "저장된 계약서":
    from Quotation_KEKOREA.orchestration.ui.saved_contracts import render_saved_contracts
    render_saved_contracts(_authenticated_principal)

elif page == "엔진 사전검증":
    st.subheader("기존 엔진 사전검증 · 읽기 전용")
    st.caption("기존 무역서류·계약서의 검증 함수만 호출합니다. 저장·승인·PDF 발행·메일 발송은 하지 않습니다.")
    st.warning("현재 화면은 개발·검증용입니다. 실제 계약서·거래처 기밀은 입력하지 마세요.")
    doc_kind = st.selectbox("검증 유형", ["PI", "PO", "CI", "PL", "CONTRACT"], key="preflight_kind")
    example = ({"contract_id": "DEMO-001", "revision": 1,
                "contract_type": "sale", "language": "ko", "parties": [],
                "terms": [], "clauses": [], "issues": [], "omissions": {}}
               if doc_kind == "CONTRACT" else
               {"document_type": doc_kind, "product_family": "solar_cell", "items": []})
    raw_json = st.text_area("검토할 구조화 데이터 (JSON)",
                            value=json.dumps(example, ensure_ascii=False, indent=2),
                            height=225, key=f"preflight_json_{doc_kind}")
    if st.button("기존 엔진으로 사전검증", type="primary", key="validate_existing_engine"):
        try:
            candidate = json.loads(raw_json)
            if not isinstance(candidate, dict):
                raise ValueError("최상위 JSON은 객체여야 합니다.")
            from Quotation_KEKOREA.orchestration.adapters.engine_bridge import (
                evaluate_trade_candidate, evaluate_contract_candidate,
            )
            report = (evaluate_contract_candidate(candidate) if doc_kind == "CONTRACT"
                      else evaluate_trade_candidate({**candidate, "document_type": doc_kind}))
            st.markdown(f"**검증 결과: {report.status}**")
            if report.blockers:
                st.error(f"확인·수정할 항목 {len(report.blockers)}개")
                for issue in report.blockers:
                    st.write("- " + issue)
            else:
                st.success("검증상 필수조건 충족. 실제 문서 승인 및 발송은 별도로 필요합니다.")
            st.info("발송 권한: 없음 · 승인 및 저장: 수행하지 않음")
        except (ValueError, TypeError, KeyError) as exc:
            st.error(f"입력 또는 검증 오류: {exc}")

elif page == "문서 초안 미리보기":
    st.subheader("기존 엔진 기반 문서형 미리보기")
    st.caption("기존 코드로 계산·검증한 내용을 표시합니다. AI 계약 조항을 생성하거나 PDF/직인/최종 발행을 수행하지 않습니다.")
    kind = st.selectbox("문서 종류", ["PI", "PO", "CI", "PL", "CONTRACT"], key="preview_document_kind")
    example = (
        {"contract_id": "DRAFT-DEMO", "contract_type": "sale", "language": "ko",
         "revision": 1, "parties": [], "terms": [], "clauses": [], "issues": []}
        if kind == "CONTRACT" else
        {"document_type": kind, "product_family": "solar_cell", "currency": "USD",
         "document_number": "DRAFT", "seller": {"legal_name": "KE KOREA CO. LTD", "address": "Example Street"},
         "buyer": {"legal_name": "Demo Buyer LLC", "address": "Example Street"},
         "incoterms": "EXW Seoul", "payment_terms": "To confirm",
         "items": [{"product_name": "M10 test cell", "quantity": "100", "unit": "PCS",
                    "unit_price": "0.2", "price_basis": "PCS", "price_source": "demo"}]}
    )
    raw = st.text_area("거래 조건 또는 계약 스냅샷 (JSON)",
                       value=json.dumps(example, ensure_ascii=False, indent=2), height=235,
                       key=f"preview_json_{kind}")
    if st.button("초안 미리보기 생성", key="build_readonly_preview", type="primary"):
        try:
            from Quotation_KEKOREA.orchestration.workflows.document_preview import build_preview
            preview = build_preview(kind, json.loads(raw))
            st.session_state["preview_current"] = preview
        except (ValueError, KeyError, TypeError) as exc:
            st.session_state.pop("preview_current", None)
            st.error(f"초안 생성 불가: {exc}")
    preview = st.session_state.get("preview_current")
    if preview is not None and preview.kind == kind:
        st.divider()
        st.warning(preview.watermark)
        st.markdown(f"### {preview.title}")
        st.caption(f"검증 상태: {preview.status} · 승인/발송 권한 없음")
        if preview.parties:
            st.markdown("#### 거래 당사자")
            st.dataframe(list(preview.parties), width="stretch", hide_index=True)
        if preview.terms:
            st.markdown("#### 주요 조건")
            st.dataframe(list(preview.terms), width="stretch", hide_index=True)
        if preview.items:
            st.markdown("#### 품목 및 계산")
            st.dataframe(list(preview.items), width="stretch", hide_index=True)
        if preview.total:
            st.metric(f"계산된 합계 ({preview.currency})", preview.total)
        if preview.clauses:
            st.markdown("#### 기존 작성 조항")
            for clause in preview.clauses:
                with st.container(border=True):
                    st.markdown("**계약 조항**")
                    st.text(clause["title"])
                    for sentence in clause["sentences"]:
                        st.text(sentence)
        if preview.blockers:
            with st.expander(f"미확정 항목 {len(preview.blockers)}개", expanded=True):
                for issue in preview.blockers:
                    st.text(issue)
        st.info("화면 미리보기는 검토용입니다. 파일도 최종 발행·승인·메일 발송에 사용할 수 없습니다.")
        st.markdown("#### 검토용 파일 생성 및 다운로드")
        st.caption("계약: 기존 계약서 DRAFT 엔진으로 PDF·DOCX 생성. 무역서류: 기존 계산 검증 후 무직인·비발행 DOCX 검토본만 생성합니다.")
        source_key = hashlib.sha256((kind + "\\0" + raw).encode("utf-8")).hexdigest()
        if st.button("검토용 파일 생성", key="create_review_files", type="secondary"):
            st.session_state.pop("review_file_bundle", None)
            st.session_state.pop("review_file_source", None)
            try:
                from Quotation_KEKOREA.orchestration.workflows.draft_files import create_review_files
                source = json.loads(raw)
                files = create_review_files(kind, source)
                st.session_state["review_file_bundle"] = files
                st.session_state["review_file_source"] = source_key
            except (ValueError, TypeError, KeyError, ImportError) as exc:
                st.error(f"검토용 파일을 생성하지 못했습니다: {exc}")
        if st.session_state.get("review_file_source") == source_key:
            for extension, file in st.session_state.get("review_file_bundle", {}).items():
                st.download_button(
                    f"DRAFT {extension.upper()} 다운로드", data=file["content"],
                    file_name=file["filename"], mime=file["mime"],
                    key=f"download_draft_{extension}",
                )
                st.caption(f"SHA-256: {file['sha256']}")
        else:
            st.caption("입력 내용이 변경되었거나 생성된 파일이 없습니다. 현재 조건으로 검토본을 생성하세요.")
        if kind != "CONTRACT":
            st.warning("무역서류 PDF는 기존 생성 엔진의 회사 직인 필수 조건 때문에 이 화면에서 제공하지 않습니다.")


elif page in ("문서 검토", "발송 대기", "실행 기록"):
    if not runs:
        st.info("생성된 작업이 없습니다. 메일함에서 샘플 업무를 시작하세요.")
    else:
        selections = {f"{r.subject} [{r.source_id}]": r.source_id for r in runs}
        label = st.selectbox("작업 선택", list(selections), key="mock_run_selector")
        st.session_state.mock_selected = selections[label]
        run = _selected_run()
        st.caption(f"Run: {run.run_id} · Status: {run.status}")
        if page == "문서 검토":
            st.subheader("초안별 검토")
            if not run.tasks:
                st.warning("요청된 문서 종류를 구분할 수 없습니다. 필요한 문서 종류를 다시 입력하세요.")
            for task in run.tasks:
                with st.container(border=True):
                    st.markdown(f"**{task.kind}** · {'검토 완료 (모의)' if task.approved else '검토 대기'}")
                    revised = st.text_area("문서 편집 및 메모", task.text, key=f"edit-{run.run_id}-{task.kind}", height=115)
                    left, right = st.columns(2)
                    if left.button("수정 저장", key=f"save-{run.run_id}-{task.kind}"):
                        try:
                            _save(edit_mock_document(run, task.kind, revised))
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                    if right.button("문서 검토 확인", key=f"approve-{run.run_id}-{task.kind}", disabled=task.approved or revised != task.text, type="primary"):
                        _save(approve_mock_document(run, task.kind))
                        st.rerun()
            if run.tasks and all(t.approved for t in run.tasks):
                st.success("모든 샘플 문서 검토 완료. 발송 대기 메뉴에서 메일 초안을 확인할 수 있습니다.")
        elif page == "발송 대기":
            st.subheader("메일 최종 검토 · 발송은 불가능")
            st.caption("문서 검토 승인과 이메일 승인을 분리해 UI 흐름만 검증합니다.")
            with st.form(f"draft-{run.run_id}"):
                to = st.text_input("수신자", value=run.email_to)
                subject = st.text_input("메일 제목", value=run.email_subject)
                body = st.text_area("메일 본문", value=run.email_body, height=160)
                save = st.form_submit_button("메일 초안 저장")
            if save:
                _save(update_mock_email(run, to, subject, body))
                st.rerun()
            st.write("첨부 예정 문서: ", ", ".join(t.kind for t in run.tasks) or "없음")
            st.warning("현재는 실제 첨부 파일이 존재하지 않습니다. 검토 확인은 샘플 상태에만 적용됩니다.")
            if st.button("이메일 최종 검토 확인 (모의)", type="primary",
                         disabled=not run.tasks or not all(t.approved for t in run.tasks)):
                try:
                    _save(approve_mock_email(run))
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if is_mock_approval_current(run):
                st.success("모의 이메일 승인 완료. 실제 SMTP 발송 기능은 연결되지 않았습니다.")
            st.button("실제 메일 발송 · 미구현", disabled=True, help="후이즈 SMTP와 승인/멱등성 연동 후 별도 구현")
        else:
            st.subheader("실행 기록 · 세션 한정")
            st.caption("새로고침/서버 재시작 시 보존을 보장하지 않습니다.")
            for number, record in enumerate(run.history, 1):
                st.write(f"{number}. {record}")
