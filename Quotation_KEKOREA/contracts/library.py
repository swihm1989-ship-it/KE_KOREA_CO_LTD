"""Private original samples and explicitly reviewed, traceable retrieval guidance.

Vectors are model-tagged JSONB data in the existing reference table. Search scans
at most 500 source records; this is not a claimed pgvector database index.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from Quotation_KEKOREA.contracts.references import extract_reference
from Quotation_KEKOREA.contracts.repository import ContractRepositoryError

DEFAULT_MODEL = 'text-embedding-3-small'
DIMENSIONS = 512
KINDS = {'sale', 'trade_commission', 'investment_commission'}


class LibraryChunk(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=100)
    locator: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=20, max_length=2500)
    embedding: list[float] = Field(default_factory=list, max_length=3072)

    @field_validator('embedding')
    @classmethod
    def finite_vector(cls, vector):
        if any(not math.isfinite(v) for v in vector) or (vector and not any(vector)):
            raise ValueError('Embedding vectors must be finite and nonzero.')
        return vector


class LibraryManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = 1
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=160)
    contract_types: list[str] = Field(min_length=1, max_length=3)
    language: str
    jurisdictions: list[str] = Field(default_factory=list, max_length=10)
    approved: bool = False
    active: bool = True
    reviewed_at: str | None = None
    embedding_model: str = DEFAULT_MODEL
    chunks: list[LibraryChunk] = Field(default_factory=list, max_length=64)

    @field_validator('contract_types')
    @classmethod
    def valid_types(cls, values):
        if not set(values).issubset(KINDS):
            raise ValueError('Choose supported contract types.')
        return list(dict.fromkeys(values))

    @field_validator('language')
    @classmethod
    def valid_language(cls, value):
        if value not in {'ko', 'en'}:
            raise ValueError('Choose ko or en.')
        return value


def read_manifest(record):
    locations = record.get('source_locations') or []
    if not locations or locations[0].get('kind') != 'contract_sample_library':
        raise ValueError('Not a managed shared sample.')
    manifest = LibraryManifest.model_validate(locations[0].get('manifest'))
    if manifest.version != 1:
        raise ValueError('Unsupported library manifest version.')
    return manifest


def _locations(record, manifest):
    original = [loc for loc in record.get('source_locations', []) if loc.get('kind') != 'contract_sample_library']
    return [{'kind': 'contract_sample_library', 'manifest': manifest.model_dump()}] + original


def register_sample(repo, data, filename, *, title, contract_types, language):
    bucket = repo.private_bucket('kekorea-contracts')
    if not bucket or bucket.get('public') is not False:
        raise ValueError('Sample originals require a verified private bucket.')
    digest = hashlib.sha256(data).hexdigest()
    reference_id = str(uuid5(NAMESPACE_URL, 'kekorea-contract-sample:' + digest))
    existing = repo.get_library_record(reference_id)
    if existing:
        if existing['content_hash'] != digest or hashlib.sha256(repo.download_private_file(
                'kekorea-contracts', existing['storage_path'])).hexdigest() != digest:
            raise ValueError('Stored sample verification failed; no original was overwritten.')
        return existing
    reference = extract_reference(data, filename)
    manifest = LibraryManifest(title=title, contract_types=contract_types, language=language)
    suffix = filename.rsplit('.', 1)[-1].lower()
    path = f'library/sources/{digest}/original.{suffix}'
    mime = {'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pdf': 'application/pdf', 'hwp': 'application/x-hwp'}.get(filename.rsplit('.', 1)[-1].lower())
    try:
        repo.upload_private_file('kekorea-contracts', path, data, mime or 'application/octet-stream')
    except ContractRepositoryError as exc:
        if 'HTTP 409' not in str(exc):
            raise
    if hashlib.sha256(repo.download_private_file('kekorea-contracts', path)).hexdigest() != digest:
        raise ValueError('Uploaded sample hash verification failed.')
    record = {'id': reference_id, 'contract_id': None, 'filename': filename,
              'content_hash': digest, 'storage_path': path, 'extraction_status': 'library_pending',
              'extracted_text': reference['extracted_text'], 'source_locations': reference['source_locations']}
    record['source_locations'] = _locations(record, manifest)
    try:
        repo.save_reference(record)
    except ContractRepositoryError:
        raced = repo.get_library_record(reference_id)
        if not raced or raced.get('content_hash') != digest:
            raise
    verified = repo.get_library_record(reference_id)
    if not verified or verified.get('content_hash') != digest:
        raise ValueError('Database sample registration was not confirmed.')
    return verified


def embed_texts(texts, *, env, opener=urllib.request.urlopen):
    if not env.get('OPENAI_API_KEY'):
        raise ValueError('Embedding API is not configured.')
    if not texts or len(texts) > 64 or any(not t or len(t) > 6000 for t in texts):
        raise ValueError('Embedding input exceeds the batch limit.')
    model = env.get('CONTRACT_LIBRARY_EMBEDDING_MODEL') or DEFAULT_MODEL
    if model not in {'text-embedding-3-small', 'text-embedding-3-large'}:
        raise ValueError('Configure a supported library embedding model.')
    request = urllib.request.Request('https://api.openai.com/v1/embeddings',
        data=json.dumps({'model': model, 'input': texts, 'dimensions': DIMENSIONS, 'encoding_format': 'float'}).encode(),
        headers={'Authorization': 'Bearer ' + env['OPENAI_API_KEY'], 'Content-Type': 'application/json'}, method='POST')
    try:
        with opener(request, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Embedding response exceeded the limit.')
        rows = sorted(json.loads(raw)['data'], key=lambda row: row['index'])
        if [row['index'] for row in rows] != list(range(len(texts))):
            raise ValueError('Embedding response index mismatch.')
        vectors = [row['embedding'] for row in rows]
        for vector in vectors:
            if len(vector) != DIMENSIONS or not any(vector) or any(not math.isfinite(v) for v in vector):
                raise ValueError('Invalid embedding vector.')
        return vectors
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError):
        raise RuntimeError('Semantic search is unavailable; use keyword search until reindexing succeeds.') from None


def publish_sample(repo, reference_id, chunks, *, env, embedder=None):
    record = repo.get_library_record(reference_id)
    if not record:
        raise ValueError('Shared sample not found.')
    manifest = read_manifest(record)
    locators = {loc.get('locator') for loc in record['source_locations'] if loc.get('locator')}
    checked = []
    for row in chunks:
        if row.get('locator') not in locators:
            raise ValueError('Each guidance location must match the original sample.')
        text = str(row.get('text') or '').strip()
        if re.search(r'[\w.+-]+@[\w.-]+|\d(?:[ -]?\d){6,}|\d\s*%', text):
            raise ValueError('Remove contacts, account/phone numbers and inherited percentages from guidance.')
        chunk_id = hashlib.sha256((row['locator'] + '\n' + text).encode()).hexdigest()[:24]
        checked.append(LibraryChunk(id=chunk_id, locator=row['locator'], topic=row['topic'], text=text))
    if not checked or len(checked) > 64:
        raise ValueError('Publish between 1 and 64 reviewed guidance chunks.')
    notices = []
    try:
        vectors = (embedder or embed_texts)([c.topic + '\n' + c.text for c in checked], env=env)
        if len(vectors) != len(checked) or len({len(v) for v in vectors}) != 1:
            raise ValueError('Embedding count/dimension mismatch.')
        checked = [LibraryChunk(**{**c.model_dump(), 'embedding': v}) for c, v in zip(checked, vectors)]
    except (RuntimeError, ValueError):
        notices.append('의미 검색 벡터를 만들지 못했습니다. 키워드 검색으로 등록되며 재승인으로 벡터를 갱신할 수 있습니다.')
    old_revision = manifest.revision
    manifest.chunks = checked
    manifest.approved = True
    manifest.active = True
    manifest.revision += 1
    manifest.reviewed_at = datetime.now(timezone.utc).isoformat()
    manifest.embedding_model = env.get('CONTRACT_LIBRARY_EMBEDDING_MODEL') or DEFAULT_MODEL
    repo.update_library_record(reference_id, {'source_locations': _locations(record, manifest),
                                             'extraction_status': 'library_approved'}, expected_revision=old_revision)
    saved = repo.get_library_record(reference_id)
    if not saved or read_manifest(saved).revision != manifest.revision:
        raise ValueError('Shared sample publication was not confirmed.')
    return {'record': saved, 'notices': notices}


def set_sample_active(repo, reference_id, active):
    record = repo.get_library_record(reference_id)
    manifest = read_manifest(record)
    previous = manifest.revision
    manifest.active = bool(active)
    manifest.revision += 1
    repo.update_library_record(reference_id, {'source_locations': _locations(record, manifest)}, expected_revision=previous)


def _tokens(text):
    words = re.findall(r'[a-z0-9]+|[가-힣]+', text.casefold())
    return set(words) | {word[i:i+2] for word in words if re.search('[가-힣]', word)
                         for i in range(max(0, len(word)-1))}


def search_library(repo, snapshot, query, *, env, embedder=None, limit=6):
    records = repo.list_library_records(approved_only=True)
    candidates, notices = [], []
    if len(records) >= 500:
        notices.append('샘플 검색 한도에 도달했습니다. 전체 검색을 위해 DB 인덱스 확장이 필요합니다.')
    for record in records[:500]:
        try:
            manifest = read_manifest(record)
        except ValueError:
            notices.append('형식을 검증할 수 없는 샘플은 검색에서 제외했습니다.')
            continue
        if not manifest.approved or not manifest.active or snapshot.get('contract_type') not in manifest.contract_types:
            continue
        candidates.extend((record['id'], manifest, chunk) for chunk in manifest.chunks)
    if not candidates:
        return {'references': [], 'sources': [], 'mode': 'keyword', 'notices': notices}
    query = str(query or snapshot.get('contract_type') or '')[:6000]
    vector = None
    model = env.get('CONTRACT_LIBRARY_EMBEDDING_MODEL') or DEFAULT_MODEL
    try:
        if not embedder and not env.get('OPENAI_API_KEY'):
            raise ValueError('Not configured')
        vector = (embedder or embed_texts)([query], env=env)[0]
        if not vector or any(not math.isfinite(v) for v in vector) or not any(vector):
            raise ValueError('Invalid query vector')
    except (RuntimeError, ValueError, IndexError):
        notices.append('의미 검색을 사용할 수 없어 키워드로 참고 조항을 검색했습니다.')
    query_tokens = _tokens(query)
    ranked = []
    for reference_id, manifest, chunk in candidates:
        words = _tokens(chunk.topic + ' ' + chunk.text)
        lexical = len(words & query_tokens) / max(1, len(query_tokens))
        semantic = 0.0
        if vector and manifest.embedding_model == model and len(chunk.embedding) == len(vector):
            norm = math.sqrt(sum(x*x for x in vector) * sum(x*x for x in chunk.embedding))
            if norm:
                semantic = sum(a*b for a,b in zip(vector, chunk.embedding)) / norm
        score = max(0.0, semantic) * 0.8 + lexical * 0.2
        if score > 0.02:
            ranked.append((score, reference_id, manifest, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1], item[3].id))
    references, sources, seen = [], [], set()
    for score, reference_id, manifest, chunk in ranked:
        signature = chunk.text.casefold().strip()
        if signature in seen:
            continue
        seen.add(signature)
        context_id = f'library:{reference_id}:{chunk.id}:v{manifest.revision}'
        references.append({'id': context_id, 'filename': manifest.title,
                           'extracted_text': chunk.text})
        sources.append({'id': context_id, 'title': manifest.title, 'locator': chunk.locator,
                        'topic': chunk.topic, 'text': chunk.text, 'revision': manifest.revision,
                        'language': manifest.language, 'jurisdictions': manifest.jurisdictions})
        if len(references) >= min(8, max(1, limit)):
            break
    has_vectors = vector is not None and any(c.embedding and len(c.embedding) == len(vector)
                                             and m.embedding_model == model for _,m,c in candidates)
    return {'references': references, 'sources': sources, 'mode': 'hybrid' if has_vectors else 'keyword',
            'notices': list(dict.fromkeys(notices))}
