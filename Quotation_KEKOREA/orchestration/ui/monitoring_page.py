"""Private administrator metrics. Caller has passed Master's OIDC allowlist."""
import json
import streamlit as st

from Quotation_KEKOREA.observability.core import operation
from Quotation_KEKOREA.observability.pricing import PRICE_VERSION
from Quotation_KEKOREA.observability.reporting import local_summary

REVISION = 'master-observability-20261113-v1'


def _number(value):
    return f'{value:,}' if value is not None else '미확인'


def render_monitoring(principal, store):
    if not principal:
        st.error('관리자 인증이 필요합니다.')
        return
    st.subheader('관리자 모니터링 · 실행 로그 & AI')
    st.caption('메일 수집 · AI 요청 · 계약 분석 · PI/PO/CI/PL 생성 | 업무 내용과 개인정보는 수집하지 않습니다.')
    days = st.selectbox('조회 기간', [1,7,30], index=1,
                        format_func=lambda n:f'최근 {n}일',key='telemetry_days')
    a,b=st.columns(2)
    refresh=a.button('새로고침',key='telemetry_refresh',width='stretch')
    check=b.button('모니터링 연결 점검',key='telemetry_health',width='stretch')
    if check:
        with operation('monitor.health'):
            pass
    if refresh or check:
        store.flush(timeout=1)
    durable=False
    try:
        summary=store.summary(days)
        events=store.remote_recent(days)
        if not isinstance(summary,dict) or not isinstance(summary.get('totals'),dict):
            raise ValueError('Invalid telemetry summary')
        durable=True
    except Exception:
        events=store.recent(days)
        summary=local_summary(events)
    if durable:
        st.success('Supabase 영구 저장소 연결 정상 · 30일 보관 · 만료 데이터는 매시간 자동 삭제')
    else:
        st.warning('영구 저장소를 읽을 수 없어 이 서버의 임시 메모리 기록만 표시합니다. 최대 2,000건이며 재시작 시 사라집니다.')
    health=store.health()
    st.caption(f"저장 대기 {health['pending']}건 · 이 서버 저장 완료 {health['persisted']}건 · 영구 저장 누락 {health['dropped']}건")
    if health['last_error'] or health['dropped']:
        st.warning('모니터링 데이터 일부가 저장되지 않았을 수 있습니다. 기존 업무는 계속 실행됩니다.')
    totals=summary['totals']
    count=totals.get('calls',0)
    failures=totals.get('failures',0)
    cols=st.columns(4)
    cols[0].metric('AI 호출',str(count))
    cols[1].metric('성공률',f'{100*(count-failures)/count:.1f}%' if count else '—')
    cols[2].metric('실패율',f'{100*failures/count:.1f}%' if count else '—')
    duration=totals.get('avg_duration_ms')
    cols[3].metric('평균 응답시간',f'{duration/1000:.2f}초' if duration is not None else '—')
    cols=st.columns(4)
    cols[0].metric('입력 토큰',_number(totals.get('input_tokens')))
    cols[1].metric('출력 토큰',_number(totals.get('output_tokens')))
    cost=totals.get('estimated_cost_usd')
    cols[2].metric('예상 API 비용 · USD',f'${float(cost):.6f}' if cost is not None else '미확인')
    cols[3].metric('재시도 호출',str(totals.get('retry_calls',0)))
    if totals.get('unpriced_calls') or totals.get('missing_usage_calls'):
        st.info(f"비용 미확인 {totals.get('unpriced_calls',0)}건 · 토큰 미확인 {totals.get('missing_usage_calls',0)}건. 표시 합계는 확인된 값의 소계입니다.")
    st.caption('비용은 표준 텍스트 토큰 단가에 따른 추정치입니다. 청구서와 다를 수 있습니다. 미등록 모델·요금제·캐시 쓰기는 비용 미확인으로 표시합니다. '+PRICE_VERSION)
    st.markdown('#### 모델별 AI 사용량')
    if summary.get('models'):
        st.dataframe(summary['models'],hide_index=True,width='stretch')
    else:
        st.info('조회 기간에 완료된 AI 호출이 없습니다. 기능 적용 이후의 실행부터 집계됩니다.')
    st.markdown('#### 작업별 실행시간')
    if summary.get('tasks'):
        st.dataframe(summary['tasks'],hide_index=True,width='stretch')
    else:
        st.caption('수집된 실행 기록이 없습니다.')
    st.markdown('#### 오류 원인과 재시도')
    if summary.get('errors'):
        st.dataframe(summary['errors'],hide_index=True,width='stretch')
    else:
        st.caption('기록된 오류가 없습니다.')
    st.caption('오류는 고정 분류 코드와 HTTP 상태만 보관합니다. 재시도 횟수는 기존 처리에서 발생한 재시도이며, 모니터링이 새 AI 요청을 만들지 않습니다.')
    st.markdown('#### 최근 JSON 실행 로그')
    st.caption('최근 200건 · 집계는 조회 기간 전체의 완료 이벤트 기준입니다. 실행 ID로 시작·종료 및 하위 작업을 연결할 수 있습니다.')
    recent=list(reversed(events[-200:])) if not durable else events[:200]
    if recent:
        st.dataframe([{k:e.get(k) for k in ('run_id','task','document_kind','event_type','status','started_at','ended_at','duration_ms','model','error_type','retry_count')}
                      for e in recent],hide_index=True,width='stretch')
        with st.expander('JSON 원본 보기'):
            st.code('\n'.join(json.dumps(e,ensure_ascii=False,allow_nan=False) for e in recent),language='json')
    st.caption('보존기간 30일 · 저장 항목: 실행 메타데이터만 · 버전 '+REVISION)
