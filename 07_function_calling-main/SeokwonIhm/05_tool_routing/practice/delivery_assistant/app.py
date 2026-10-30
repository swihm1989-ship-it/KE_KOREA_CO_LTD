"""Run으로 실행하는 배송 안내 CLI. 기존 SeokwonIhm/.env와 가상환경 사용."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from contracts import DeliveryArgs, DeliveryResult, Intent, PickupArgs, PickupResult
from prompts import DIALOGUE_PROMPT, INTENT_PROMPT

MAX_CALLS = 4
HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def connect_delivery():
    # 사용 도구: MCP stdio 클라이언트. 같은 Python으로 로컬 server.py를 실행한다.
    parameters = StdioServerParameters(command=sys.executable, args=[str(HERE / 'server.py')])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            discovered = await session.list_tools()
            definitions = {tool.name: {'type': 'function', 'function': {
                'name': tool.name, 'description': tool.description or '',
                'parameters': tool.input_schema,
            }} for tool in discovered.tools}
            if set(definitions) != {'lookup_delivery', 'lookup_pickup_point'}:
                raise ValueError('서버의 조회 도구 목록이 과제 명세와 다릅니다.')
            yield session, definitions


def new_state(tracking_number):
    # 새 문의마다 이전 배송·보관소 조회 결과를 버린다. 대화 이력은 유지한다.
    return {'tracking_number': tracking_number, 'delivery': None, 'pickup': None,
            'calls': 0, 'attempts': 0, 'error': None, 'limit_reached': False}


def available_tools(state):
    if state['error'] or state['calls'] >= MAX_CALLS:
        return []
    if state['delivery'] is None:
        return ['lookup_delivery']
    delivery = state['delivery']
    if delivery['found'] and delivery['status'] == 'ready_for_pickup' and state['pickup'] is None:
        return ['lookup_pickup_point']
    return []


def response_data(result):
    if result.is_error:
        detail = '; '.join(item.text for item in result.content if item.type == 'text')
        raise RuntimeError(detail or 'MCP 도구 실행 오류')
    if result.structured_content is not None:
        return result.structured_content
    for item in result.content:
        if item.type == 'text':
            try:
                return json.loads(item.text)
            except json.JSONDecodeError:
                continue
    raise ValueError('MCP 응답에 JSON 조회 결과가 없습니다.')


async def execute_call(session, state, call):
    """Python 보장: 노출 도구·입력 출처·현재 보관소 ID·실행 횟수·반환 검사."""
    try:
        name = call['name']
        if name not in available_tools(state):
            raise ValueError('현재 단계에서 허용되지 않은 도구입니다.')
        if name == 'lookup_delivery':
            args = DeliveryArgs.model_validate(call['args'])
            if args.tracking_number != state['tracking_number']:
                raise ValueError('현재 문의에서 사용자가 제공한 운송장번호만 조회할 수 있습니다.')
            schema, slot = DeliveryResult, 'delivery'
            expected_id = args.tracking_number
            id_field = 'tracking_number'
        else:
            args = PickupArgs.model_validate(call['args'])
            if args.pickup_point_id != state['delivery']['pickup_point_id']:
                raise ValueError('현재 배송 조회 결과에서 반환한 보관소 ID만 조회할 수 있습니다.')
            schema, slot = PickupResult, 'pickup'
            expected_id = args.pickup_point_id
            id_field = 'pickup_point_id'
        state['calls'] += 1
        # 실제 도구 실행은 반드시 MCP 세션을 통한다. 로컬 함수를 직접 호출하지 않는다.
        result = await session.call_tool(name, args.model_dump())
        payload = schema.model_validate(response_data(result)).model_dump()
        if payload[id_field] != expected_id:
            raise ValueError('조회 결과 ID가 요청한 ID와 다릅니다.')
        state[slot] = payload
        return ToolMessage(content=json.dumps(payload, ensure_ascii=False), tool_call_id=call['id'])
    except Exception as error:
        # 검증 거부는 도구 실행이 아니며, 실행 오류와 미등록 결과를 구별한다.
        return ToolMessage(content=json.dumps({'error': str(error)}, ensure_ascii=False),
                           tool_call_id=call['id'], status='error')


def number_in_request(number, text):
    return bool(number and re.search(r'(?<![A-Za-z0-9])' + re.escape(number) + r'(?![A-Za-z0-9])', text))


async def process_request(model, session, definitions, history, request, ask=input, emit=print):
    active_request = request
    emit('요청: ' + request)
    history.append(HumanMessage(content=request))
    while True:
        # 모델 판단: 문의 의미와 사용자가 말한 번호 추출. 아직 배송 도구는 사용하지 않는다.
        intent = await (INTENT_PROMPT | model.with_structured_output(
            Intent, method='json_schema')).ainvoke({'history': history, 'active_request': active_request})
        if intent.kind == 'general':
            answer = intent.reply or '배송 상태·수령 장소 조회와 관련된 내용을 안내할 수 있습니다.'
            history.append(AIMessage(content=answer))
            emit('예상 경로: 일반 설명 → 배송 도구 0회')
            emit('최종 안내: ' + answer)
            return {'answer': answer, 'trace': [], 'state': new_state(None)}
        number = intent.tracking_number.strip() if intent.tracking_number else None
        # Python 보장: 이력에만 있는 번호나 모델이 만든 번호로 조회하지 않는다.
        if number_in_request(number, active_request):
            break
        question = intent.reply or '조회할 운송장번호를 알려 주세요.'
        history.append(AIMessage(content=question))
        emit('예상 경로: 번호 질문 → 배송 도구 0회')
        emit('안내: ' + question)
        follow_up = (await asyncio.to_thread(ask, '운송장번호/보충 답변(빈 입력은 취소): ')).strip()
        if not follow_up:
            emit('최종 안내: 조회를 취소했습니다.')
            return {'answer': '조회를 취소했습니다.', 'trace': [], 'state': new_state(None)}
        history.append(HumanMessage(content=follow_up))
        active_request += '\n보충 답변: ' + follow_up

    state, trace = new_state(number), []
    emit('예상 경로: lookup_delivery → 보관소 도착이면 lookup_pickup_point'
         + (' → 배송지 변경 미지원 안내' if intent.kind == 'change' else ''))
    while available_tools(state) and state['attempts'] < MAX_CALLS:
        names = available_tools(state)
        variables = {'kind': intent.kind, 'tracking_number': number,
                     'available_tools': ', '.join(names), 'evidence': json.dumps(state, ensure_ascii=False),
                     'history': history}
        # 모델 판단: 현재 단계에 공개한 도구의 인자를 선택한다. 한 번에 한 호출만 요청한다.
        response = await (DIALOGUE_PROMPT | model.bind_tools(
            [definitions[name] for name in names], tool_choice='required', parallel_tool_calls=False
        )).ainvoke(variables)
        emit('모델의 도구 요청: ' + json.dumps(response.tool_calls, ensure_ascii=False))
        history.append(response)  # 원래 AIMessage 및 호출 ID를 보존한다.
        if not response.tool_calls:
            state['error'] = '모델이 필수 조회 도구를 요청하지 않아 배송을 확인하지 못했습니다.'
            break
        for index, call in enumerate(response.tool_calls):
            if index > 0 or state['attempts'] >= MAX_CALLS:
                message = ToolMessage(content='한 번에 한 도구만, 요청당 최대 4회까지 허용합니다.',
                                      tool_call_id=call['id'], status='error')
            else:
                state['attempts'] += 1
                before = state['calls']
                message = await execute_call(session, state, call)
                record = {'name': call['name'], 'args': call['args'],
                          'executed': state['calls'] > before, 'status': message.status,
                          'payload': json.loads(message.content)}
                trace.append(record)
                emit('Python 실행 결과: ' + json.dumps(record, ensure_ascii=False))
                if message.status == 'error' and state['calls'] > before:
                    state['error'] = record['payload']['error']
            # 원래 요청의 ID와 같은 ToolMessage를 모든 호출에 연결한다.
            history.append(message)

    unfinished = state['delivery'] is None or (
        state['delivery']['found'] and state['delivery']['status'] == 'ready_for_pickup'
        and state['pickup'] is None)
    state['limit_reached'] = unfinished and state['attempts'] >= MAX_CALLS
    variables = {'kind': intent.kind, 'tracking_number': number, 'available_tools': '없음',
                 'evidence': json.dumps(state, ensure_ascii=False), 'history': history}
    # 도구 없는 최종 안내에서만 문자열 파서를 사용한다.
    answer = await (DIALOGUE_PROMPT | model | StrOutputParser()).ainvoke(variables)
    history.append(AIMessage(content=answer))
    emit('최종 안내: ' + answer)
    return {'answer': answer, 'trace': trace, 'state': state}


def create_model():
    # 기존 환경 파일 위치를 명시한다. 키나 .env를 과제 폴더에 복사하지 않는다.
    load_dotenv(HERE.parents[2] / '.env')
    return ChatOpenAI(model=os.environ['OPENAI_MODEL'], timeout=45, max_retries=1)


async def main():
    model = create_model()
    print('실습용 고정 JSON 배송 조회입니다. 배송지 변경은 지원하지 않습니다. 빈 입력으로 종료합니다.')
    history = []
    async with connect_delivery() as (session, definitions):
        while request := (await asyncio.to_thread(input, '\n문의: ')).strip():
            try:
                await process_request(model, session, definitions, history, request)
            except Exception as error:
                print('처리 실패:', str(error))
                # 미완료 도구 호출 메시지는 다음 대화에 넘기지 않는다.
                history.clear()


if __name__ == '__main__':
    asyncio.run(main())
