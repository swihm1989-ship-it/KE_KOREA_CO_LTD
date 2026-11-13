"""Selected-mail → existing AI extractors → private, unapproved candidates.

No polling, sends, database writes, automatic approvals or payload logging.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import re
from uuid import uuid4

from Quotation_KEKOREA.orchestration.router import classify, DOC_TYPES
from Quotation_KEKOREA.observability.core import traced

MAX_MAIL_CHARS=12000


@dataclass(frozen=True)
class MailRequest:
    instruction: str
    kinds: tuple[str,...]
    fingerprint: str


def fingerprint(instruction):
    return sha256(instruction.encode('utf-8')).hexdigest()


def prepare_mail_request(subject, body):
    if not isinstance(body,str) or not body.strip():
        raise ValueError('추출할 메일 본문이 없습니다.')
    instruction='메일 제목: '+str(subject or '')+'\n\n'+body.strip()
    if len(instruction)>MAX_MAIL_CHARS:
        raise ValueError('메일이 12,000자를 초과합니다. AI 업무 요청에서 필요한 거래조건만 편집해 주세요. 원문을 자동으로 잘라 보내지 않습니다.')
    # Old mail may contain facts but must not choose a new document request.
    latest=re.split(r'(?im)^\s*(?:On .+wrote:|[- ]*Original Message[- ]*|[- ]*Forwarded message[- ]*|보낸 사람:)',body,maxsplit=1)[0]
    latest='\n'.join(line for line in latest.splitlines() if not line.lstrip().startswith('>'))
    # Join line-wrapped MoU titles for routing only. The AI instruction retains
    # the unmodified original source text (including every newline).
    routing = re.sub(r'(?i)\bmemorandum\s*\n\s*of\s*\n\s*understanding\b',
                     'Memorandum of Understanding', latest)
    routing = re.sub(r'(?i)\bmemorandum\s+of\s*\n\s*understanding\b',
                     'Memorandum of Understanding', routing)
    routing = re.sub(r'(?i)\b양해\s*\n\s*각서', '양해각서', routing)
    # Protect interior abbreviation dots, but preserve the FINAL full stop as
    # a sentence boundary. Otherwise "M.O.U. No need for PI" gets conflated.
    routing = re.sub(r'(?i)\bM\s*\.?\s*O\s*\.?\s*U\.(?=[가-힣])', 'MOU', routing)
    routing = re.sub(r'(?i)\bM\s*\.?\s*O\s*\.?\s*U(?![A-Za-z0-9_])', 'MOU', routing)
    positive=[];denied=set()
    for sentence in re.split(r'[.!?;\n]',routing):
        if re.search(r"\b(?:no need for|do not (?:prepare|send|create|provide)|don.t (?:prepare|send|create|provide)|without)\b|(?:작성|발행|생성)하지\s*마|필요\s*없",sentence,re.I):
            denied.update(classify('',sentence))
        else:
            positive.extend(classify('',sentence))
    kinds=set(positive or classify(str(subject or ''),''))-denied
    from Quotation_KEKOREA.agent.ci_import import is_ci_conversion_request
    if is_ci_conversion_request(latest):
        kinds.discard('PI');kinds.add('CI')
    return MailRequest(instruction,tuple(k for k in DOC_TYPES if k in kinds),fingerprint(instruction))


def queue_handoff(state, message, *, extract=False, attachments=(), requested=None):
    # Old in-memory render and consent state must not cross transactions.
    for key in list(state):
        if ((key.startswith('ai_intake_') and key not in {'ai_intake_language','ai_intake_family'})
                or key.startswith('master_pdf_') or key=='master_legacy_files'):
            state.pop(key,None)
    try:
        request=prepare_mail_request(message.subject,message.body)
        if requested is not None:
            selected=tuple(classify('', '', list(requested)))
            request=MailRequest(request.instruction, selected, request.fingerprint)
    except ValueError as error:
        state['ai_intake_instruction']='메일 제목: '+message.subject+'\n\n'+message.body
        state['ai_intake_mail_notice']=str(error)
        extract=False
        request=None
    state['ai_intake_consent']=bool(extract)
    state['master_page']='AI 업무 요청'
    if request:
        state['ai_intake_instruction']=request.instruction
        state['ai_intake_mail_source']={'fingerprint':request.fingerprint,'kinds':list(request.kinds)}
        state['ai_intake_mail_attachments']=deepcopy(list(attachments))
        if extract:
            state['ai_intake_mail_pending']={'token':str(uuid4()),'fingerprint':request.fingerprint}


def consume_pending(state, instruction):
    pending=state.pop('ai_intake_mail_pending',None)
    return bool(pending and state.get('ai_intake_consent') is True
                and pending['fingerprint']==fingerprint(instruction))


def _safe_trade(raw, kind, instruction, family, attachments):
    from Quotation_KEKOREA.agent.extractor import _schema, verify_item_quotes
    from Quotation_KEKOREA.agent.ci_import import prepare_ci_import, ci_import_issues
    from Quotation_KEKOREA.orchestration.workflows.commercial_values import normalize_trade_values
    if not isinstance(raw,dict) or not isinstance(raw.get('items'),list):
        raise ValueError('AI 무역서류 응답의 품목 목록이 유효하지 않습니다.')
    schema=_schema()
    allowed=set(schema['properties'])|{'source_document_type','source_total'}
    fields=set(schema['properties']['items']['items']['properties'])|{'source_line_total'}
    data={k:deepcopy(v) for k,v in raw.items() if k in allowed}
    if any(not isinstance(row,dict) for row in raw['items']):
        raise ValueError('AI 품목 행이 유효하지 않습니다.')
    data['items']=[{k:deepcopy(v) for k,v in row.items() if k in fields} for row in raw['items']]
    data['document_type']=kind
    data['product_family']=family
    # DRAFT is a label, never an invented final invoice number.
    data['document_number']=data.get('document_number') or 'DRAFT'
    from .mail_trade_normalization import explicit_ship_to, synchronize_nullable_quantities
    if not explicit_ship_to(instruction) and not (attachments and explicit_ship_to(data.get('ship_to_source'))):
        data['ship_to']=None
    data=verify_item_quotes(data,instruction,image_context=bool(attachments))
    data=synchronize_nullable_quantities(normalize_trade_values(data))
    if kind=='CI':
        prepare_ci_import(data,requested_type='CI',has_attachments=bool(attachments))
        for issue in ci_import_issues(data):
            if issue not in data.setdefault('missing_fields',[]):data['missing_fields'].append(issue)
    return normalize_trade_values(data)


def _analysis_from_trade(data):
    row=(data.get('items') or [{}])[0]
    terms={'products':row.get('product_name'),'quantity':row.get('quantity'),
           'unit':row.get('unit'),'unit_price':row.get('unit_price'),
           'currency':data.get('currency'),'delivery':data.get('incoterms'),
           'payment_trigger':data.get('payment_terms')}
    return {'contract_type':'sale','parties':[dict(data.get(role) or {},roles=[role]) for role in ('seller','buyer')],
            'terms':[{'key':k,'value':v,'status':'suggested','source_refs':[]} for k,v in terms.items() if v is not None],
            'questions':[],'issues':[]}


@traced('trade.extract')
def extract_mail_candidates(instruction,kinds,env,*,consent,language='ko',family='solar_cell',
                            attachments=(),trade_opener=None,contract_opener=None):
    if not consent:
        raise PermissionError('선택한 메일 및 선택한 첨부의 외부 AI 처리 동의가 필요합니다.')
    if not isinstance(instruction,str) or not instruction.strip() or len(instruction)>MAX_MAIL_CHARS:
        raise ValueError('메일 거래조건은 1~12,000자여야 합니다.')
    kinds=classify('','',list(kinds))
    if not kinds:
        raise ValueError('준비할 문서 종류를 선택해 주세요.')
    if family not in {'solar_cell','wafer','polysilicon','solar_module','cosmetics'}:
        raise ValueError('상품군을 확인해 주세요.')
    from Quotation_KEKOREA.agent.attachments import validate_attachments
    files=validate_attachments(list(attachments))
    from Quotation_KEKOREA.agent.extractor import extract_trade_data
    trades={}
    # Buy-side PO and sell-side documents must never share inferred party roles/prices.
    groups=[['PO']] if 'PO' in kinds else []
    sales=[k for k in ('CI','PI','PL') if k in kinds]
    if sales: groups.append(sales)
    for group in groups:
        primary=group[0]
        kwargs={'images':files,'env':env,'requested_document_type':primary,
                'packing_source':'PL' in group}
        if trade_opener is not None:kwargs['opener']=trade_opener
        raw=extract_trade_data(instruction,**kwargs)
        for kind in group:
            trades[kind]=_safe_trade(raw,kind,instruction,family,files)
    analysis=None;contract=None
    if 'CONTRACT' in kinds:
        from Quotation_KEKOREA.contracts.service import analyze_trade
        from Quotation_KEKOREA.contracts.models import new_snapshot
        from Quotation_KEKOREA.orchestration.workflows.ai_intake import make_contract_candidate
        analysis=analyze_trade([{'role':'user','content':instruction}],new_snapshot('mail-intake','sale',language),[],
                               env=env,client=contract_opener)
        # Missing facts stay absent and editable; never turn them into confirmations.
        candidate_analysis=deepcopy(analysis)
        candidate_analysis['terms']=[t for t in candidate_analysis['terms']
                                     if not (t.get('status')=='missing' and t.get('value') in (None,''))]
        for term in candidate_analysis['terms']:
            if term.get('status')=='missing':term['status']='suggested'
        contract=make_contract_candidate(candidate_analysis,language)
    if analysis is None:
        analysis=_analysis_from_trade(next(iter(trades.values())))
    bundle={kind:contract if kind=='CONTRACT' else trades[kind] for kind in kinds}
    return {'analysis':analysis,'candidates':bundle}
