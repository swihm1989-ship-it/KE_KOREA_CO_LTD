"""Controlled promotion of one existing contract reference to the shared library.

The original contract-scoped record is untouched. The new library record is
pending approval, not automatically searchable by the AI.
"""
from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from Quotation_KEKOREA.contracts.library import register_sample


def promote_contract_reference(repo, contract_id, reference_id, *, title, contract_types, language):
    if not contract_id or not reference_id:
        raise ValueError('먼저 계약과 해당 참고자료를 선택해 주세요.')
    references = repo.contract_references(contract_id)
    matched = [r for r in references if str(r.get('id')) == str(reference_id)]
    if len(matched) != 1:
        raise ValueError('현재 계약에 속한 참고자료를 찾을 수 없습니다.')
    record = matched[0]
    filename = str(record.get('filename') or '')
    suffix = filename.rpartition('.')[-1].lower()
    if suffix not in {'pdf', 'docx'}:
        raise ValueError('공통 라이브러리로 등록 가능한 참고자료는 PDF 또는 DOCX입니다.')
    storage_path = str(record.get('storage_path') or '')
    if not storage_path.startswith(f'{contract_id}/references/') or '..' in PurePosixPath(storage_path).parts:
        raise ValueError('원본 참고자료 저장 경로가 올바르지 않습니다.')
    data = repo.download_private_file('kekorea-contracts', storage_path)
    if hashlib.sha256(data).hexdigest() != record.get('content_hash'):
        raise ValueError('원본 파일의 해시 검증에 실패했습니다. 등록하지 않았습니다.')
    if not str(title or '').strip():
        raise ValueError('개인정보가 없는 공통 참고 제목을 입력해 주세요.')
    return register_sample(repo, data, filename, title=title.strip(),
                           contract_types=contract_types, language=language)
