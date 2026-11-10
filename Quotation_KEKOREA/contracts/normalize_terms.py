"""Conservative, multilingual normalization for contract-extracted field labels.

Only keys are standardized; original extracted values and evidence are retained.
A token such as 'kg' is a unit, not a quantity. 'Value' can be unit or total.
"""
from decimal import Decimal, InvalidOperation
from copy import deepcopy
import re
import unicodedata
_NUM = re.compile(r"([-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)")

# Maintain this as an exact-alias list rather than fuzzy keyword matching: fuzzy
# matching may turn 'total price' into 'unit_price' or 'delivery cost' into delivery.
ALIASES = {
    'products': ('product','product name','product description','product specifications','product specification','goods','commodity','material','item','items','sku','grade','model','product type','description of goods','specification','produk','nama produk','jenis barang','barang','komoditas','spesifikasi barang','spesifikasi produk','품목','제품','제품명','품명','제품 규격','제품 및 필수 규격','상품명','상품','모델명','원자재','규격'),
    'quantity': ('qty','q ty','qtty','quantity','quantities','quantity ordered','order quantity','volume','vol','volume ordered','trade volume','monthly volume','monthly quantity','monthly qty','contract volume','contract quantity','order volume','total qty','net weight','gross weight','weight','tonnage','tonnage quantity','jumlah','kuantitas','jumlah barang','jumlah pesanan','volume bulanan','jumlah bulanan','berat','berat bersih','jumlah total','수량','물량','월 물량','월물량','월간 물량','총 수량','총수량','주문 수량','중량','무게','톤수','발주수량','거래물량'),
    'unit': ('uom','unit of measure','quantity unit','unit of quantity','measurement unit','unit measure','u/m','units','unit type','satuan','satuan jumlah','satuan ukur','unit pengukuran','단위','수량 단위','물량 단위','중량단위','계량 단위'),
    'unit_price': ('unit price','price per unit','price per kg','price per mt','price/kg','price/mt','price per kilogram','price per ton','price per tonne','per kg price','per mt price','price rate','unit rate','rate per kg','rate per mt','unit cost','unitprice','u price','u/p','unit value','selling price per unit','purchase price per unit','harga satuan','harga per unit','harga per kg','harga per ton','harga per mt','harga unit','tarif satuan','nilai per unit','단가','단위 가격','단위가격','kg당 가격','kg당 단가','톤당 가격','톤당 단가','제품 단가','판매단가','구매단가','매입단가','매출단가','개당 가격','개당 단가','와트당 단가','단위당 가격'),
    'currency': ('currency','currency code','payment currency','invoice currency','denomination','ccy','mata uang','jenis mata uang','valuta','통화','통화 코드','거래 통화','결제 통화','표시 통화'),
    'total_contract_value': ('total value','total amount','total price','contract value','contract amount','contract price','total contract value','total contract amount','transaction value','invoice value','extended price','amount payable','grand total','nilai total','nilai kontrak','total nilai kontrak','jumlah keseluruhan','nilai transaksi','harga total','총액','총금액','계약금액','계약 총액','계약총액','거래금액','총 거래금액','총 대금','합계금액'),
    'payment_trigger': ('payment trigger','payment terms','terms of payment','payment condition','payment method','payment','payment schedule','settlement terms','remittance terms','advance payment','prepayment terms','tt terms','t t terms','syarat pembayaran','ketentuan pembayaran','cara pembayaran','metode pembayaran','jadwal pembayaran','pembayaran','결제 조건','결제조건','결제방식','대금 지급','대금지급','지급 조건','지급조건','대금 지급 조건','대금지급조건','지급 방식','결제방식','선급금 조건','송금조건'),
    'payment_deadline': ('payment due','payment date','payment due date','due date','payment deadline','payment term days','days to pay','due for payment','jatuh tempo','tanggal jatuh tempo','tenggat pembayaran','batas pembayaran','tanggal pembayaran','jatuh tempo pembayaran','결제 기한','결제기한','지급 기한','지급기한','지급일','결제일','대금 지급일','송금기한'),
    'delivery': ('delivery','delivery terms','delivery condition','delivery place','place of delivery','delivery point','delivery location','delivery schedule','delivery date','shipment terms','shipping terms','shipment','shipping','incoterm','incoterms','incoterms 2020','port of loading','port of discharge','port of destination','destination','origin','trade term','pengiriman','syarat pengiriman','ketentuan pengiriman','tempat penyerahan','jadwal pengiriman','tanggal pengiriman','penyerahan barang','pelabuhan muat','pelabuhan tujuan','인도','인도 조건','인도조건','인도 장소','인도장소','인도 일정','선적조건','선적 조건','선적항','도착항','납기','납품 조건','인도 조건 장소 일정'),
    'inspection_claims': ('inspection','claims','inspection claims','inspection and claims','quality inspection','acceptance inspection','claim period','warranty claims','quality claim','product inspection','pemeriksaan','inspeksi','klaim','pemeriksaan kualitas','inspeksi dan klaim','pengajuan klaim','검수','검사','품질검사','검수 조건','검수 클레임 처리','검수/클레임 처리','클레임','하자','하자보증'),
    'contract_date': ('contract date','agreement date','effective date','commencement date','effective from','start date','date of contract','date of agreement','tanggal kontrak','tanggal perjanjian','tanggal berlaku','tanggal efektif','tanggal mulai kontrak','계약 시작일','계약일','효력 발생일','발효일','계약 체결일','시작일'),
    'contract_duration': ('contract duration','contract term','term of contract','duration','contract period','agreement period','validity period','tenor','jangka waktu kontrak','masa kontrak','masa berlaku','jangka waktu perjanjian','계약 기간','계약기간','유효기간','존속기간','계약 존속기간'),
    'scope': ('scope','scope of transaction','scope of work','scope of supply','transaction scope','covered goods','purpose','object of agreement','ruang lingkup','ruang lingkup pekerjaan','cakupan pekerjaan','cakupan transaksi','tujuan kontrak','범위','거래 범위','업무 범위','계약 목적','계약범위','공급 범위','거래 목적'),
    'governing_law': ('governing law','applicable law','choice of law','jurisdiction law','hukum yang berlaku','hukum yang mengatur','pilihan hukum','준거법','적용법','적용 법률'),
    'dispute_resolution': ('dispute resolution','dispute settlement','settlement of disputes','arbitration','arbitration venue','dispute forum','forum selection','penyelesaian sengketa','arbitrase','forum sengketa','분쟁 해결','분쟁해결','분쟁 해결 절차','중재','중재지','관할법원'),
    'monthly_quantity_mt': ('monthly mt equivalent','monthly quantity conversion','monthly tonnage equivalent','konversi bulanan mt','월 물량 환산','월 톤수 환산'),
    'total_contract_quantity': ('total contract volume','total quantity over contract','total contract quantity','total contract weight','contract total volume','cumulative volume','jumlah total kontrak','volume total kontrak','총 계약 물량','계약 총 물량','총 계약 수량','3년 총 물량 계산','계약기간 총물량'),
    'commission_formula': ('commission rate','commission percentage','commission formula','brokerage fee rate','success fee rate','fee formula','komisi','tarif komisi','rumus komisi','비율 수수료','수수료율','커미션율','커미션 산식','수수료 산식'),
    'commission_basis': ('commission base','commission basis','fee base','commissionable amount','basis for commission','dasar komisi','dasar perhitungan komisi','수수료 기준금액','수수료 산정 기준','커미션 기준금액'),
    'commission_payer': ('commission payer','fee payer','payer of commission','pembayar komisi','pihak pembayar komisi','수수료 지급자','커미션 지급자'),
    'covered_transaction': ('covered transaction','eligible transaction','transaction covered','transaksi tercakup','transaksi yang dicakup','대상 거래','적용 거래'),
    'success_trigger': ('success condition','success trigger','commission trigger','success fee trigger','kondisi keberhasilan','pemicu komisi','성공 조건','수수료 발생 조건'),
    'term_or_deal_scope': ('deal scope','covered period','applicable term','jangka waktu cakupan','기간 또는 거래범위','적용 기간 또는 특정 거래 범위'),
    'funding_type': ('funding type','financing type','investment type','jenis pendanaan','jenis investasi','자금 형태','투자 형태'),
    'project': ('project','project name','investment project','proyek','nama proyek','프로젝트','투자 프로젝트'),
}


def _fold(key):
    value=unicodedata.normalize('NFKC', str(key or '')).casefold().strip()
    value=re.sub(r'[_\-./()]+',' ',value)
    return ' '.join(value.split())

_INDEX={}
for canonical, aliases in ALIASES.items():
    for alias in (canonical,*aliases):
        folded=_fold(alias)
        other=_INDEX.get(folded)
        if other is not None and other!=canonical:
            raise ValueError(f'Overlapping term alias {alias!r}: {other} vs {canonical}')
        _INDEX[folded]=canonical

_UNIT_WORDS={'kg','kgs','kilogram','kilograms','kilogramme','mt','metric ton','metric tons','metric tonne','ton','tonne','tons','tonnes','pcs','pc','piece','pieces','mw','wp','watt','watts','unit','units','kg 월','mt 월'}
_PRICE_EVIDENCE=re.compile(r'(?i)(?:/\s*(?:kg|mt|ton|tonne|pcs?|mw|wp|watt|unit)|\bper\s+(?:kg|mt|ton|tonne|pcs?|mw|wp|watt|unit)|(?:kg|mt|ton|pcs?|mw|wp)\s*당|per\s+(?:kilogram|tonne|unit))')
_TOTAL_EVIDENCE=re.compile(r'(?i)\b(?:total|contract|aggregate|invoice|amount|sum|overall|grand)\b|총액|합계|계약금액|nilai\s+kontrak|total\s+nilai')
_AMBIGUOUS={'price','rate','value','harga','nilai','가격','금액','대금','total','amount','tarif','biaya','cost'}


def _canonical_key(candidate):
    key=str(candidate.get('key') or '').strip()
    folded=_fold(key)
    known=_INDEX.get(folded)
    if known:
        return known, None
    # Unit symbols indicate UOM, not quantity. A numeric value under such a
    # label is a malformed extraction: preserve instead of asserting quantity.
    if folded in _UNIT_WORDS:
        return 'unit', None if re.search(r'[a-zA-Z가-힣]',str(candidate.get('value') or '')) else 'unit_label_with_numeric_value'
    if folded in _AMBIGUOUS:
        value=str(candidate.get('value') or '')
        unit=str(candidate.get('unit') or '')
        combined=f'{key} {value} {unit}'
        if _PRICE_EVIDENCE.search(combined):
            return 'unit_price', None
        if _TOTAL_EVIDENCE.search(key):
            return 'total_contract_value',None
        # Plain 'price' is a common per-unit label, but must remain flagged
        # until its price basis is checked. Preserve the raw numeric value.
        if folded in {'price','harga','가격'}:
            return 'unit_price', 'unit_price_basis_unverified'
        # 'value', 'amount', 'rate' etc. may denote the total rather than per-unit.
        return key, 'ambiguous_price_or_amount'
    return key, None


_INCOTERMS = re.compile(r'(?<![A-Z])(?:EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)(?![A-Z])', re.I)
_SCHEDULE = re.compile(r'일정|납기|지연|통지|협의|인수|schedule|delay|notice|notify|coordinate|agree.*date|jadwal|keterlambatan|pemberitahuan', re.I)
_UNIT = re.compile(r'(?i)(?:/|per\s+|당\s*)(kg|kgs|kilogram|kilograms|mt|metric\s+tons?|tonne?s?|pcs?|units?|wp|watts?)\b')

# A unit explicitly attached to a numeric quantity is evidence, not a guess.
_QUANTITY_VALUE_UNIT = re.compile(
    r'(?i)^\s*[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*'
    r'(kg|kgs|kilograms?|mt|metric\s+tons?|tonnes?|tons?|pcs?|pieces?|units?|mw|wp|watts?)\s*
    matches={m.upper() for m in _INCOTERMS.findall(str(text or ''))}
    return matches


def _delivery_schedule_only(item):
    value=' '.join(str(item.get(k) or '') for k in ('value','unit'))
    return bool(_SCHEDULE.search(value)) and not _extract_incoterm(value)


def _first_number(text):
    match=_NUM.search(str(text or ''))
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(',',''))
    except (InvalidOperation, ValueError):
        return None


def _normalized_measure(item, kind):
    value=str(item.get('value') or '').strip()
    unit=str(item.get('unit') or '').strip().casefold()
    number=_first_number(value)
    if number is None:
        return None
    # Match '2,324,938 PCS' with value='2324938', unit='PCS', without
    # modifying the original extraction or assuming a missing unit.
    if kind=='quantity' and not unit:
        embedded=_QUANTITY_VALUE_UNIT.fullmatch(value)
        if embedded:
            unit=embedded.group(1).casefold().replace(' ','')
    evidence=' '.join((value,unit))
    found=_UNIT.search(evidence)
    if found and kind=='unit_price':
        unit=found.group(1).casefold().replace(' ','')
    unit=unit.replace(' ','')
    units={'kgs':'kg','kilogram':'kg','kilograms':'kg','metricton':'mt','metrictons':'mt','ton':'mt','tons':'mt','tonne':'mt','tonnes':'mt','pc':'pcs','piece':'pcs','pieces':'pcs','unit':'pcs','units':'pcs'}
    unit=units.get(unit,unit)
    if kind=='quantity':
        if unit=='mt':return number*1000,'kg'
        return number,unit
    if kind=='unit_price':
        if unit=='mt':return number/1000,'kg'
        return number,unit
    return number,unit


def _currency(item):
    text=' '.join(str(item.get(k) or '') for k in ('currency','value'))
    codes={x.upper() for x in re.findall(r'(?<![A-Z])(?:USD|KRW|EUR|IDR|CNY|RMB|SGD|MYR|INR|JPY|GBP|AUD|CAD)(?![A-Z])',text,re.I)}
    if len(codes)>1:return None
    if codes:return next(iter(codes))
    if '$' in text:return 'UNSPECIFIED_DOLLAR'
    return ''


def _equivalent_terms(a,b,key):
    if key in {'quantity','unit_price','total_contract_value','total_contract_quantity','monthly_quantity_mt','contract_duration'}:
        left=_normalized_measure(a,key)
        right=_normalized_measure(b,key)
        if left and right:
            # Unknown or incompatible units should never be treated as equal.
            if left!=right:return False
            if key in {'unit_price','total_contract_value'}:
                return _currency(a)==_currency(b)
            return True
    return all(' '.join(str(item.get(k) or '').split()).casefold()==
               ' '.join(str(b.get(k) or '').split()).casefold()
               for k in ('value','unit','currency') for item in (a,))


def normalize_term_keys(analysis):
    """Normalize candidate labels, preserve evidence and report real ambiguities.

    Duplicate delivery conditions are only contradictory if they assert
    incompatible Incoterms; logistics scheduling is kept separately.
    All extracted values remain suggestions, never user confirmed facts.
    """
    result=deepcopy(analysis)
    seen={}
    normalized=[]
    warnings=[]
    for item in result.get('terms',[]):
        candidate=deepcopy(item)
        raw=str(candidate.get('key') or '').strip()
        key,warning=_canonical_key(candidate)
        candidate['key']=key
        candidate['status']='suggested' if str(candidate.get('value') or '').strip() else 'missing'
        if warning:
            warnings.append({'key':key,'first':raw,'other':str(candidate.get('value') or ''),
                             'message':f'Uncertain label {raw!r}: {warning}. Confirm original meaning.'})
        if key in seen:
            prev=seen[key]
            if _equivalent_terms(prev,candidate,key):
                continue
            if key=='delivery':
                first_terms=_extract_incoterm(prev.get('value'))
                next_terms=_extract_incoterm(candidate.get('value'))
                if first_terms and _delivery_schedule_only(candidate):
                    extra=deepcopy(candidate)
                    extra['key']='delivery_schedule_notes'
                    normalized.append(extra)
                    continue
                if next_terms and _delivery_schedule_only(prev):
                    extra=deepcopy(prev)
                    extra['key']='delivery_schedule_notes'
                    normalized=[extra if x is prev else x for x in normalized]
                    normalized.append(candidate)
                    seen[key]=candidate
                    continue
                if first_terms and next_terms and first_terms==next_terms:
                    # Location/scheduling extensions may be complementary,
                    # but differing places cannot be assumed compatible.
                    pass
            first=tuple(str(prev.get(k) or '').strip() for k in ('value','unit','currency'))
            other=tuple(str(candidate.get(k) or '').strip() for k in ('value','unit','currency'))
            warnings.append({'key':key,'first':first,'other':other,
                             'message':f'Conflicting or non-equivalent candidates for {key}; verify source.'})
            continue
        seen[key]=candidate
        normalized.append(candidate)
    result['terms']=normalized
    return result,warnings

)

def _extract_incoterm(text):
    matches={m.upper() for m in _INCOTERMS.findall(str(text or ''))}
    return matches


def _delivery_schedule_only(item):
    value=' '.join(str(item.get(k) or '') for k in ('value','unit'))
    return bool(_SCHEDULE.search(value)) and not _extract_incoterm(value)


def _first_number(text):
    match=_NUM.search(str(text or ''))
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(',',''))
    except (InvalidOperation, ValueError):
        return None


def _normalized_measure(item, kind):
    value=str(item.get('value') or '').strip()
    unit=str(item.get('unit') or '').strip().casefold()
    number=_first_number(value)
    if number is None:
        return None
    evidence=' '.join((value,unit))
    found=_UNIT.search(evidence)
    if found and kind=='unit_price':
        unit=found.group(1).casefold().replace(' ','')
    unit=unit.replace(' ','')
    units={'kgs':'kg','kilogram':'kg','kilograms':'kg','metricton':'mt','metrictons':'mt','ton':'mt','tons':'mt','tonne':'mt','tonnes':'mt','pc':'pcs','piece':'pcs','pieces':'pcs','unit':'pcs','units':'pcs'}
    unit=units.get(unit,unit)
    if kind=='quantity':
        if unit=='mt':return number*1000,'kg'
        return number,unit
    if kind=='unit_price':
        if unit=='mt':return number/1000,'kg'
        return number,unit
    return number,unit


def _currency(item):
    text=' '.join(str(item.get(k) or '') for k in ('currency','value'))
    codes={x.upper() for x in re.findall(r'(?<![A-Z])(?:USD|KRW|EUR|IDR|CNY|RMB|SGD|MYR|INR|JPY|GBP|AUD|CAD)(?![A-Z])',text,re.I)}
    if len(codes)>1:return None
    if codes:return next(iter(codes))
    if '$' in text:return 'UNSPECIFIED_DOLLAR'
    return ''


def _equivalent_terms(a,b,key):
    if key in {'quantity','unit_price','total_contract_value','total_contract_quantity','monthly_quantity_mt','contract_duration'}:
        left=_normalized_measure(a,key)
        right=_normalized_measure(b,key)
        if left and right:
            # Unknown or incompatible units should never be treated as equal.
            if left!=right:return False
            if key in {'unit_price','total_contract_value'}:
                return _currency(a)==_currency(b)
            return True
    return all(' '.join(str(item.get(k) or '').split()).casefold()==
               ' '.join(str(b.get(k) or '').split()).casefold()
               for k in ('value','unit','currency') for item in (a,))


def normalize_term_keys(analysis):
    """Normalize candidate labels, preserve evidence and report real ambiguities.

    Duplicate delivery conditions are only contradictory if they assert
    incompatible Incoterms; logistics scheduling is kept separately.
    All extracted values remain suggestions, never user confirmed facts.
    """
    result=deepcopy(analysis)
    seen={}
    normalized=[]
    warnings=[]
    for item in result.get('terms',[]):
        candidate=deepcopy(item)
        raw=str(candidate.get('key') or '').strip()
        key,warning=_canonical_key(candidate)
        candidate['key']=key
        candidate['status']='suggested' if str(candidate.get('value') or '').strip() else 'missing'
        if warning:
            warnings.append({'key':key,'first':raw,'other':str(candidate.get('value') or ''),
                             'message':f'Uncertain label {raw!r}: {warning}. Confirm original meaning.'})
        if key in seen:
            prev=seen[key]
            if _equivalent_terms(prev,candidate,key):
                continue
            if key=='delivery':
                first_terms=_extract_incoterm(prev.get('value'))
                next_terms=_extract_incoterm(candidate.get('value'))
                if first_terms and _delivery_schedule_only(candidate):
                    extra=deepcopy(candidate)
                    extra['key']='delivery_schedule_notes'
                    normalized.append(extra)
                    continue
                if next_terms and _delivery_schedule_only(prev):
                    extra=deepcopy(prev)
                    extra['key']='delivery_schedule_notes'
                    normalized=[extra if x is prev else x for x in normalized]
                    normalized.append(candidate)
                    seen[key]=candidate
                    continue
                if first_terms and next_terms and first_terms==next_terms:
                    # Location/scheduling extensions may be complementary,
                    # but differing places cannot be assumed compatible.
                    pass
            first=tuple(str(prev.get(k) or '').strip() for k in ('value','unit','currency'))
            other=tuple(str(candidate.get(k) or '').strip() for k in ('value','unit','currency'))
            warnings.append({'key':key,'first':first,'other':other,
                             'message':f'Conflicting or non-equivalent candidates for {key}; verify source.'})
            continue
        seen[key]=candidate
        normalized.append(candidate)
    result['terms']=normalized
    return result,warnings
