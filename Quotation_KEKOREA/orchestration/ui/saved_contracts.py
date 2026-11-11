"""Protected read-only UI for contracts saved by the existing KE KOREA agent."""
from __future__ import annotations

import os
import streamlit as st

from Quotation_KEKOREA.orchestration.adapters.contract_library import (
    make_reader, read_contract_list, read_contract_versions, inspect_contract_version,
)
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError


def _server_value(key: str) -> str:
    """Streamlit Cloud secrets are sometimes injected as environment variables."""
    value = os.environ.get(key, "")
    if value:
        return value
    try:
        return str(st.secrets.get(key, ""))
    except (FileNotFoundError, KeyError):
        return ""


def _details(snapshot):
    st.markdown("#### 계약 당사자")
    parties = snapshot.get("parties", [])
    if parties:
        for party in parties:
            with st.container(border=True):
                st.markdown("**" + str(party.get("legal_name") or "(회사명 미확정)") + "**")
                st.caption("역할: " + ", ".join(map(str, party.get("roles", []))))
                st.write("설립국:", party.get("country") or "미입력")
                st.write("주소:", party.get("address") or "미입력")
    else:
        st.info("저장된 당사자 정보가 없습니다.")

    st.markdown("#### 거래 조건")
    terms = snapshot.get("terms", [])
    if terms:
        st.dataframe([{"항목": str(t.get("key") or ""),
                       "값": str(t.get("value") or ""),
                       "확정 상태": str(t.get("status") or "")}
                      for t in terms if isinstance(t, dict)],
                     width="stretch", hide_index=True)
    else:
        st.caption("등록된 거래 조건이 없습니다.")

    st.markdown("#### 저장된 계약서 조항")
    clauses = sorted(snapshot.get("clauses", []), key=lambda c: c.get("order", 0))
    if not clauses:
        st.warning("해당 리비전에 저장된 계약서 조항이 없습니다.")
    for clause in clauses:
        with st.container(border=True):
            st.markdown("**" + str(clause.get("title") or "무제 조항") + "**")
            for sentence in clause.get("sentences", []):
                st.write(str(sentence.get("text") or ""))


def render_saved_contracts(principal: str):
    """The caller must have passed the OIDC/allowlist gate on this rerun."""
    if not principal:
        raise PermissionError("Authenticated principal required")

    st.subheader("저장된 계약서 · 기존 업무 에이전트")
    st.caption("기존 Supabase 계약서 원본과 리비전 조회 · 읽기 전용 · 신규 계약 작성/수정/삭제/발송 불가")
    env = {k: _server_value(k) for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}
    if not all(env.values()):
        st.error("계약서 조회용 서버 설정(SUPABASE_URL, SUPABASE_SECRET_KEY)이 없습니다. 관리자 설정이 필요합니다.")
        return

    try:
        repo = make_reader(env)
        keyword = st.text_input("계약서 검색", placeholder="계약명, 유형, 상태, 계약 ID", key="saved_contract_search")
        language = st.selectbox("언어", [("전체", ""), ("한국어", "ko"), ("English", "en")],
                                format_func=lambda x: x[0], key="saved_contract_lang")[1]
        records = read_contract_list(repo, keyword=keyword, language=language)
        if not records:
            st.info("검색 결과가 없습니다. 이 화면은 기존 저장소의 최신 100건을 대상으로 합니다.")
            return

        st.caption(f"조회된 계약서 {len(records)}건 · 기존 저장소에서 최근 업데이트 순으로 최대 100건")
        st.dataframe([{
            "계약명": r.get("title"), "유형": r.get("contract_type"),
            "언어": r.get("language"), "상태": r.get("status"),
            "최신 Revision": r.get("current_revision"),
            "수정일": r.get("updated_at"),
        } for r in records], width="stretch", hide_index=True)

        choices = {f"{r.get('title') or 'Untitled'} [{r.get('language')}] · {r['id']}": str(r["id"])
                   for r in records if r.get("id")}
        if not choices:
            st.warning("계약서 ID가 누락되어 상세 조회가 불가능합니다.")
            return
        selected = st.selectbox("조회할 계약서", list(choices), key="saved_contract_selected")
        identifier = choices[selected]
        versions = read_contract_versions(repo, identifier)
        if not versions:
            st.info("선택한 계약서의 리비전 내역이 없습니다.")
            return
        version_choices = {f"Revision {v['revision']} · {v.get('created_at') or 'date unknown'}": v
                           for v in versions}
        version_label = st.selectbox("리비전 선택", list(version_choices), key="saved_contract_version")
        entry = version_choices[version_label]
        snapshot = entry["snapshot"]
        st.caption("변경 요약: " + str(entry.get("change_summary") or "기록 없음"))
        st.markdown("### " + str(snapshot.get("title") or selected.split(" [")[0]))
        st.caption("원본 데이터 조회 · 리비전 " + str(entry["revision"]))
        _details(snapshot)

        st.divider()
        st.markdown("#### 저장된 분석 결과")
        existing = snapshot.get("issues") or []
        if existing:
            for issue in existing:
                st.write(str(issue.get("message") or issue) if isinstance(issue, dict) else str(issue))
        else:
            st.caption("해당 리비전에 저장된 분석 이슈가 없습니다.")

        if st.checkbox("기존 계약서 검증 규칙으로 분석 보기", key="saved_contract_rule_review"):
            report = inspect_contract_version(snapshot)
            st.caption("AI 새 호출이 아닌 기존 결정적 검증 규칙 기반 분석입니다. 법률 의견이나 최종 승인 판정이 아닙니다.")
            if report["cards"]:
                st.dataframe([{"분류": c["kind"], "확인 항목": c["summary"], "발견 수": c["count"]}
                              for c in report["cards"]], width="stretch", hide_index=True)
            if report["issues"]:
                with st.expander("상세 검증 결과", expanded=False):
                    for issue in report["issues"]:
                        st.write(str(issue.get("message") or issue) if isinstance(issue, dict) else str(issue))
            else:
                st.success("기존 기본 검증에서 추가 확인 항목이 발견되지 않았습니다. 법적 적합성을 보증하지 않습니다.")
    except (ContractRepositoryError, ValueError, TypeError) as exc:
        st.error("계약서 조회 또는 검증에 실패했습니다. 연결 설정 및 원본 데이터를 확인하세요.")
