"""기존 가상환경으로 Run하는 도서관 조회 터미널 대화 앱."""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from batch import format_summary
from contracts import CompareArgs
from prompts import DIALOGUE_PROMPT
from tools import MAX_CONCURRENCY, compare_library_stock

MAX_ROUNDS = 3


async def answer(model, messages, request, emit=print):
    messages.append(HumanMessage(content=request))
    attempted, merged = False, None  # 새 사용자 턴이면 앞선 제목의 결과를 재사용하지 않는다.
    emit('요청: ' + request)
    for _ in range(MAX_ROUNDS):
        selected = model if attempted else model.bind_tools(
            [compare_library_stock], tool_choice='auto', parallel_tool_calls=False)
        response = await (DIALOGUE_PROMPT | selected).ainvoke({'history': messages})
        messages.append(response)  # 원래 AIMessage와 실제 호출 ID를 보존한다.
        calls = response.tool_calls
        emit('모델의 도구 요청: ' + json.dumps(calls, ensure_ascii=False))
        if not calls:
            return StrOutputParser().invoke(response)
        valid = not attempted and len(calls) == 1 and calls[0]['name'] == compare_library_stock.name
        attempted = True
        if not valid:
            for call in calls:
                messages.append(ToolMessage(content='이 턴에는 compare_library_stock 한 번만 허용합니다.',
                                            tool_call_id=call['id'], name=call['name'], status='error'))
            continue
        call = calls[0]
        try:
            args = CompareArgs.model_validate(call['args'])
            if args.title not in request:
                raise ValueError('이번 사용자 입력에 실제 있는 책 제목만 조회할 수 있습니다.')
            emit(f'예상 실행: 비교 도구 1회 → 지점별 독립 작업 3개, 최대 동시 실행 {MAX_CONCURRENCY}개')
            # 업무 도구 1회 → 내부 gather 작업 3개 → 합류 결과 1개.
            merged = await compare_library_stock.ainvoke(args.model_dump())
            emit('실제 작업·병합 결과: ' + json.dumps(merged, ensure_ascii=False))
            # 내부 작업용 호출 ID를 만들지 않고 원래 모델 호출 ID에 한 결과를 연결한다.
            messages.append(ToolMessage(content=json.dumps(merged, ensure_ascii=False),
                                        tool_call_id=call['id'], name=call['name'], status='success'))
        except Exception as exc:
            detail = f'{type(exc).__name__}: {exc}'
            emit('도구 실행 오류: ' + detail)
            messages.append(ToolMessage(content=detail, tool_call_id=call['id'],
                                        name=call['name'], status='error'))
    fallback = format_summary(merged) if merged else '조회 결과를 확인하지 못했습니다.'
    notice = '모델 호출 한도에 도달했습니다.\n' + fallback
    messages.append(AIMessage(content=notice))
    return notice


async def main():
    # .env는 기존 이름 폴더의 파일을 사용하며 복사·출력하지 않는다.
    load_dotenv(Path(__file__).resolve().parents[3] / '.env')
    model = ChatOpenAI(model=os.environ['OPENAI_MODEL'], timeout=45, max_retries=1)
    messages = []
    print('세 도서관의 고정 가상 자료를 조회합니다. 예약·대출은 지원하지 않습니다. 빈 입력으로 종료합니다.')
    while request := (await asyncio.to_thread(input, '\n도서 문의: ')).strip():
        try:
            # 제목 보충 답변도 이 messages에 추가되므로 원래 요청·질문과 같은 대화다.
            print('최종 안내:', await answer(model, messages, request))
        except Exception as exc:
            print('처리 실패:', str(exc))
            messages.clear()  # 미완료 호출 메시지를 다음 대화로 넘기지 않는다.


if __name__ == '__main__':
    asyncio.run(main())
