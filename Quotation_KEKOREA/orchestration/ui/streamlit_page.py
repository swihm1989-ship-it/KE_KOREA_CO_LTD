"""Run from the repository root:

    streamlit run Quotation_KEKOREA/orchestration/ui/streamlit_page.py

All data is fake and all approvals are UI-only. NO external mailbox or sends.
"""
from __future__ import annotations
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

st.markdown("""
<style>
:root { --ink:#172b37; --accent:#087f72; --line:#dfe9e9; }
.block-container { max-width:1460px; padding-top:1.6rem; }
[data-testid="stSidebar"] { background:#f4f7f7; border-right:1px solid var(--line); }
h1,h2,h3 { color:var(--ink); letter-spacing:-.03em; }
[data-testid="stMetric"] { border:1px solid var(--line); padding:1rem; border-radius:10px; background:#fff; }
.stButton button[kind="primary"] { background:var(--accent); border-color:var(--accent); }
</style>
""", unsafe_allow_html=True)

if "mock_runs" not in st.session_state:
    st.session_state.mock_runs = {}
if "mock_selected" not in st.session_state:
    st.session_state.mock_selected = SAMPLE_MESSAGES[0].id
if "mock_notes" not in st.session_state:
    st.session_state.mock_notes = []

st.sidebar.markdown("### KE KOREA")
st.sidebar.caption("AI WORKSPACE · ISOLATED DEMO")
page = st.sidebar.radio("업무 메뉴", ["업무 대시보드", "메일함", "AI 업무 요청", "문서 검토", "발송 대기", "엔진 사전검증", "문서 초안 미리보기", "실행 기록"], label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.warning("샘플 데이터 전용\n\n후이즈메일/계약/PI·PO·CI·PL 실연동 없음. 외부 발송 불가.", icon="⚠️")

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

st.title("Trade operations, in one workspace")
st.caption("후이즈메일 오케스트레이션 설계 검증용 독립 화면 · 기존 업무 에이전트에 영향 없음")
col_a, col_b, col_c, col_d = st.columns(4)
runs = list(st.session_state.mock_runs.values())
col_a.metric("샘플 메일", len(SAMPLE_MESSAGES))
col_b.metric("진행 중 작업", sum(r.status != "ready_for_future_integration" for r in runs))
col_c.metric("문서 검토 대기", sum(r.status == "awaiting_document_approval" for r in runs))
col_d.metric("발송 대기(모의)", sum(r.status == "ready_for_future_integration" for r in runs))
st.divider()

if page in ("업무 대시보드", "메일함"):
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
    st.subheader("자연어 업무 요청 · Mock router")
    st.caption("AI API를 호출하지 않습니다. 문서 키워드를 찾아 가상 워크플로만 만듭니다.")
    with st.form("mock_task_form"):
        subject = st.text_input("업무 제목", placeholder="PI and Contract draft")
        instruction = st.text_area("업무 지시", placeholder="거래조건과 필요한 문서를 설명하세요. 실거래 기밀은 입력하지 마세요.", height=130)
        submitted = st.form_submit_button("샘플 업무 생성", type="primary")
    if submitted:
        if not (subject.strip() or instruction.strip()):
            st.error("업무 제목 또는 지시문을 입력하세요.")
        else:
            number = len(st.session_state.mock_runs) + 1
            item = MockMessage(f"manual-{number}", "reviewer@example.test", subject, instruction, "manual")
            _save(start_mock_run(item))
            st.session_state.mock_selected = item.id
            st.success("Mock 라우팅 완료. 문서 검토 메뉴로 이동하세요.")

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
            st.dataframe(list(preview.parties), use_container_width=True, hide_index=True)
        if preview.terms:
            st.markdown("#### 주요 조건")
            st.dataframe(list(preview.terms), use_container_width=True, hide_index=True)
        if preview.items:
            st.markdown("#### 품목 및 계산")
            st.dataframe(list(preview.items), use_container_width=True, hide_index=True)
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
        st.info("이 화면은 검토용 미리보기입니다. 저장, 서명, 직인, 최종 PDF, 이메일 발송 기능이 없습니다.")

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
