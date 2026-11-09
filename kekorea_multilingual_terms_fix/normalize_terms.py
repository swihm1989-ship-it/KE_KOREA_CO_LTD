"""Conservative normalization of AI clause term keys (not term values).

The input language can be Korean, English, Indonesian or mixed. AI must still
return stable schema keys; this mapper catches common synonyms without making
commercial decisions. Unknown keys are preserved as suggestions for review.
"""
import re
import unicodedata
from copy import deepcopy

# Canonical model keys are language-neutral; never translate stored values.
ALIASES = {
    'products': ('product', 'product name', 'product specification', 'produk', 'nama produk', 'spesifikasi produk', 'barang', '품목', '제품', '제품명', '품명', '제품 규격', '제품 및 필수 규격'),
    'quantity': ('qty', 'volume', 'monthly volume', 'monthly quantity', 'jumlah', 'jumlah barang', 'jumlah bulanan', 'kuantitas', '수량', '월 물량', '월물량', '총 수량'),
    'unit': ('quantity unit', 'unit of measure', 'satuan', 'satuan jumlah', '수량 단위'),
    'unit_price': ('unit price', 'price per unit', 'price/kg', 'unitprice', 'harga satuan', 'harga per unit', 'harga per kg', '단가', '단위 가격', 'kg당 가격', '제품 단가'),
    'currency': ('currency code', 'mata uang', '통화', '결제 통화'),
    'payment_trigger': ('payment terms', 'payment condition', 'payment method', 'payment', 'terms of payment', 'syarat pembayaran', 'cara pembayaran', 'pembayaran', '결제 조건', '결제방식', '대금 지급', '지급 조건', '대금 지급 조건'),
    'payment_deadline': ('payment due date', 'payment deadline', 'due date', 'batas pembayaran', 'jatuh tempo pembayaran', '결제 기한', '지급 기한'),
    'delivery': ('delivery terms', 'delivery condition', 'delivery place', 'incoterms', 'pengiriman', 'syarat pengiriman', 'penyerahan barang', '인도 조건', '인도조건', '인도 장소', '인도 조건/장소/일정'),
    'inspection_claims': ('inspection', 'claims', 'inspection claims', 'pemeriksaan', 'klaim', 'inspeksi dan klaim', '검수', '검수/클레임 처리'),
    'contract_date': ('effective date', 'commencement date', 'tanggal berlaku', 'tanggal mulai kontrak', '계약 시작일', '계약일', '효력 발생일'),
    'scope': ('scope of transaction', 'scope of work', 'ruang lingkup', '범위', '거래 범위'),
    'governing_law': ('applicable law', 'governing law', 'hukum yang berlaku', '준거법'),
    'dispute_resolution': ('dispute resolution', 'settlement of disputes', 'penyelesaian sengketa', '분쟁 해결'),
    'contract_duration': ('contract duration', 'contract term', 'duration', 'jangka waktu kontrak', 'masa kontrak', '계약 기간', '계약기간'),
    'monthly_quantity_mt': ('monthly mt equivalent', 'monthly quantity conversion', 'konversi bulanan mt', '월 물량 환산'),
    'total_contract_quantity': ('total contract volume', 'total quantity over contract', 'total contract quantity', 'jumlah total kontrak', '총 계약 물량', '3년 총 물량 계산'),
}


def _fold(key):
    value = unicodedata.normalize('NFKC', str(key or '')).casefold().strip()
    value = re.sub(r'[_\-./()]+', ' ', value)
    return ' '.join(value.split())


_INDEX = {}
for canonical, aliases in ALIASES.items():
    for alias in (canonical, *aliases):
        folded = _fold(alias)
        if folded in _INDEX and _INDEX[folded] != canonical:
            raise ValueError(f'Overlapping term alias: {alias}')
        _INDEX[folded] = canonical


def normalize_term_keys(analysis):
    """Normalize recognizable keys; preserve all others without certifying.

    Two differently named keys mapped to the same canonical field may conflict.
    Keep the first proposal and return conflict messages for manual review.
    """
    result = deepcopy(analysis)
    seen = {}
    normalized = []
    conflicts = []
    for item in result.get('terms', []):
        candidate = deepcopy(item)
        original = str(candidate.get('key') or '').strip()
        key = _INDEX.get(_fold(original), original)
        candidate['key'] = key
        candidate['status'] = 'suggested' if str(candidate.get('value') or '').strip() else 'missing'
        if key in seen:
            previous = seen[key]
            old_fact = tuple(str(previous.get(k) or '').strip() for k in ('value', 'unit', 'currency'))
            new_fact = tuple(str(candidate.get(k) or '').strip() for k in ('value', 'unit', 'currency'))
            if old_fact != new_fact:
                conflicts.append({'key': key, 'first': old_fact, 'other': new_fact,
                                  'message': f'Conflicting extracted candidates for {key}; review against original text.'})
            continue
        seen[key] = candidate
        normalized.append(candidate)
    result['terms'] = normalized
    return result, conflicts
