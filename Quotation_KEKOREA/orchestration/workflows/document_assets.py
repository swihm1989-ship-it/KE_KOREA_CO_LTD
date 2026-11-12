"""Server-side Master document asset checks.

Never returns secret keys, account numbers, private PNGs, or arbitrary remote errors.
The document renderer remains the single existing KE KOREA renderer.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse

from Quotation_KEKOREA.agent.branding import resolve_company_seal

EXPECTED_PROJECT = "jusozufdsnpdxezxptfp"


def seal_health(env, *, root=None, resolver=resolve_company_seal):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    has_local = (root / "assets" / "image.png").is_file()
    project = urlparse(str(env.get("SUPABASE_URL") or "")).hostname or ""
    has_url = bool(env.get("SUPABASE_URL"))
    key_present = bool(env.get("SUPABASE_SECRET_KEY"))
    has_base64 = bool(env.get("KEKOREA_COMPANY_SEAL_BASE64"))
    if not has_local and not (has_url and key_present) and not has_base64:
        return "not_configured", "Master 서버에 직인 저장소 접속 정보가 없습니다. SUPABASE_URL 및 SUPABASE_SECRET_KEY를 확인하세요."
    if has_url and project != EXPECTED_PROJECT + ".supabase.co":
        return "wrong_project", "Master가 기존 KE KOREA Supabase 프로젝트가 아닌 다른 주소를 사용하고 있습니다."
    try:
        path, payload, error = resolver(root, env)
    except (OSError, RuntimeError, ValueError):
        return "storage_error", "Supabase 직인 파일의 안전한 다운로드 또는 무결성 검증에 실패했습니다."
    if payload is not None or path.is_file():
        return "ready", "기존 KE KOREA 직인 확인 완료. 기존 문서 출력 엔진으로 생성할 수 있습니다."
    # Report only known categories: never display raw service responses.
    if not key_present and not has_base64:
        return "missing_key", "SUPABASE_SECRET_KEY 설정을 찾지 못했습니다. Streamlit Secrets의 최상위 설정을 확인하세요."
    if error and "HTTP 401" in error or error and "HTTP 403" in error:
        return "access_denied", "Supabase Storage 접근 권한 오류입니다. 서버용 키 또는 정책을 확인하세요."
    if error and ("not been uploaded" in error or "not been created" in error):
        return "missing_object", "설정된 프로젝트에서 기존 직인 경로를 찾지 못했습니다."
    if error and ("does not match" in error):
        return "hash_mismatch", "직인 파일의 검증값이 기존 KE KOREA 원본과 일치하지 않습니다."
    return "storage_error", "저장소 통신 또는 직인 검증에 실패했습니다. Supabase 연결 설정을 확인하세요."
