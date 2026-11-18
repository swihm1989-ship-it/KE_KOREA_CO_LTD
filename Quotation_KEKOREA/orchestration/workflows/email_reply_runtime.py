"""Runtime-safe OpenAI reply engine access and owner-only diagnostic.

Prevents stale Python module objects in long-lived Streamlit processes after
GitHub deployments. Does not send actual email and never reads actual inbox
content during a connectivity diagnostic.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import threading
import json
import re
import urllib.error
import urllib.request

REPLY_RUNTIME_REVISION = "master-reply-20261118-personal-salutation-v3"
REPLY_RUNTIME_SOURCE_MTIME_NS = Path(__file__).stat().st_mtime_ns
DRAFT_MODULE = "Quotation_KEKOREA.orchestration.workflows.email_reply_drafts"
HANDOFF_MODULE = "Quotation_KEKOREA.orchestration.workflows.email_reply_handoff"
MAIL_UI_MODULE = "Quotation_KEKOREA.orchestration.ui.email_outbox_page"


_RELOAD_LOCK = threading.RLock()


def _latest(module_name, expected):
    # Streamlit reruns an entrypoint but often retains imported submodules.
    # Compare source mtime as well as revision and serialize across sessions.
    with _RELOAD_LOCK:
        module = importlib.import_module(module_name)
        try:
            source_mtime = Path(module.__file__).stat().st_mtime_ns
        except (TypeError, OSError):
            raise RuntimeError("AI 회신 모듈 파일이 유효하지 않습니다. 서버를 다시 배포하세요.") from None
        if (getattr(module, "REPLY_RUNTIME_REVISION", None) != expected or
                getattr(module, "REPLY_SOURCE_MTIME_NS", None) != source_mtime):
            importlib.invalidate_caches()
            module = importlib.reload(module)
        if (getattr(module, "REPLY_RUNTIME_REVISION", None) != expected or
                getattr(module, "REPLY_SOURCE_MTIME_NS", None) != Path(module.__file__).stat().st_mtime_ns):
            raise RuntimeError("실행 중인 AI 회신 모듈이 배포 버전과 다릅니다. Streamlit Cloud에서 앱 재시작이 필요합니다.")
        return module


def current_outbox_page():
    """Refresh Streamlit page module before rendering the outbox UI."""
    return _latest(MAIL_UI_MODULE, REPLY_RUNTIME_REVISION)


def _drafts():
    return _latest(DRAFT_MODULE, REPLY_RUNTIME_REVISION)


def _handoff():
    return _latest(HANDOFF_MODULE, REPLY_RUNTIME_REVISION)


def generate_reply_candidates(source, model_config, language):
    return _drafts().generate_candidates(source, model_config, language)


def prepare_email_handoff(*args, **kwargs):
    # Override the stale function object captured as a default argument by
    # earlier imports. This uses the module actually loaded from current code.
    kwargs.setdefault("generate", _drafts().generate_candidates)
    return _handoff().prepare_email_handoff(*args, **kwargs)


def configured_model(env):
    return str(env.get("CONTRACT_OPENAI_MODEL") or env.get("OPENAI_MODEL") or "").strip()


def status(env):
    """Safe metadata only; never reveal key values or request/response bodies."""
    key = str(env.get("OPENAI_API_KEY") or "").strip()
    model = configured_model(env)
    return {
        "runtime": REPLY_RUNTIME_REVISION,
        "key_configured": bool(key),
        "model_configured": bool(model),
        "model": model[:100] if model else "설정 없음",
    }


def probe_connection(env, *, opener=None):
    """Explicitly clicked, dummy-only OpenAI Responses API compatibility check.

    No original customer messages, real contacts, SMTP actions or API keys
    are logged or displayed. Can consume a small number of model tokens.
    """
    key = str(env.get("OPENAI_API_KEY") or "").strip()
    model = configured_model(env)
    if not key:
        return "설정 오류: OPENAI_API_KEY가 없습니다."
    if not model:
        return "설정 오류: CONTRACT_OPENAI_MODEL 또는 OPENAI_MODEL이 없습니다."
    provider = _drafts()  # Ensure cached module is current after Streamlit hot-deploy.
    _post_response = provider._post_response
    _safe_http_failure = provider._safe_http_failure
    payload = {
        "model": model,
        "instructions": "Respond with a JSON object with exactly one boolean property named ok, set to true.",
        "input": [{"role": "user", "content": "Synthetic connectivity test. No personal or customer data."}],
        "text": {"format": {
            "type": "json_schema",
            "name": "mail_reply_connection_probe",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        }},
        "max_output_tokens": 256,
        "store": False,
    }
    used_plain_text = False
    first_format_failure = None
    try:
        try:
            result = _post_response(payload, key, opener or urllib.request.urlopen, timeout=25)
        except urllib.error.HTTPError as error:
            failure = _safe_http_failure(error)
            if not failure["format_rejected"]:
                return "진단 실패: " + failure["message"]
            first_format_failure = failure
            fallback = dict(payload)
            fallback["text"] = {"format": {"type": "text"}}
            used_plain_text = True
            try:
                result = _post_response(fallback, key, opener or urllib.request.urlopen, timeout=25)
            except urllib.error.HTTPError as retry_error:
                retry = _safe_http_failure(retry_error)
                # Preserve first failure's safe identifier when the provider
                # does not provide another useful error code/param.
                detail = retry["message"]
                if not retry["code"] and not retry["param"]:
                    detail += " · 최초 형식 오류: " + first_format_failure["message"]
                return "진단 실패: " + detail
    except (urllib.error.URLError, OSError, TimeoutError):
        return "진단 실패: AI 서버 연결 또는 요청 시간 초과"
    except (UnicodeError, json.JSONDecodeError):
        return "진단 실패: AI 서버 응답을 읽을 수 없습니다."
    except RuntimeError as error:
        return "진단 실패: " + str(error)[:220]
    try:
        if not isinstance(result, dict) or result.get("status") != "completed":
            return "진단 실패: AI 요청이 완료되지 않았습니다."
        parts = [
            x.get("text", "")
            for item in result.get("output", []) if isinstance(item, dict)
            for x in item.get("content", []) if isinstance(x, dict) and x.get("type") == "output_text"
        ]
        probe_json = json.loads("".join(parts))
    except (ValueError, TypeError, KeyError):
        return "진단 실패: 모델이 요청한 JSON 응답을 만들지 못했습니다."
    if not isinstance(probe_json, dict) or probe_json.get("ok") is not True:
        return "진단 실패: AI 모델 응답 형식이 올바르지 않습니다."
    if used_plain_text:
        return "진단 성공: API 인증·모델 응답 정상 (구조화 형식 대신 일반 텍스트 호환 방식 사용)"
    return "진단 성공: API 인증·모델 응답 정상. 실제 메일 회신 생성은 별도 확인이 필요합니다."
