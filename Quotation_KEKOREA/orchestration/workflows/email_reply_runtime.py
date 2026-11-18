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

REPLY_RUNTIME_REVISION = "master-reply-20261118-live-diagnostic-v1"
DRAFT_MODULE = "Quotation_KEKOREA.orchestration.workflows.email_reply_drafts"
HANDOFF_MODULE = "Quotation_KEKOREA.orchestration.workflows.email_reply_handoff"


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
    """Explicit user-triggered Responses API probe with dummy input only.

    No user email text is sent, no SMTP action occurs, and no server response
    body is shown in a UI. Small model usage may be billed.
    """
    key = str(env.get("OPENAI_API_KEY") or "").strip()
    model = configured_model(env)
    if not key:
        return "설정 오류: OPENAI_API_KEY가 없습니다."
    if not model:
        return "설정 오류: CONTRACT_OPENAI_MODEL 또는 OPENAI_MODEL이 없습니다."
    # Same Responses endpoint and JSON mode used by the real generator, but
    # with completely synthetic data, no inbox, customer or transaction text.
    payload = {
        "model": model,
        "instructions": "Reply with a short JSON object containing exactly one boolean field named ok set to true.",
        "input": [{"role": "user", "content": "Synthetic connectivity test. No personal or customer data."}],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": 256,
        "store": False,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=25) as response:
            raw = response.read(25001)
        if len(raw)>25000:
            return "진단 실패: 모델 응답이 너무 큽니다."
        result = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        http_code = error.code
        # Keep only allowlisted structured provider identifiers, never provider
        # message text, request body, mailbox content or credential values.
        hint = ""
        try:
            detail = json.loads(error.read(4096).decode("utf-8"))
            data = detail.get("error", {}) if isinstance(detail, dict) else {}
            codes = [str(data.get(k, "")) for k in ("code", "param")] if isinstance(data, dict) else []
            identifiers = [v for v in codes if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", v)]
            if identifiers:
                hint = " (" + ", ".join(identifiers) + ")"
        except (OSError, UnicodeError, ValueError, TypeError):
            pass
        finally:
            error.close()
        names = {
            400: "모델·응답 형식 또는 요청 옵션 오류",
            401: "API 키 오류 또는 만료",
            403: "API 모델 접근 권한 문제",
            404: "모델을 찾지 못하거나 접근 권한 없음",
            429: "API 사용량·요금 한도 초과",
            500: "OpenAI 서버 일시 오류",
            502: "OpenAI 서버 일시 오류",
            503: "OpenAI 서버 일시 오류",
        }
        return "진단 실패 (HTTP "+str(http_code)+"): "+names.get(http_code,"API 응답 오류")+hint
    except (urllib.error.URLError, OSError, TimeoutError):
        return "진단 실패: AI 서버 연결 또는 요청 시간 초과"
    except (UnicodeError, json.JSONDecodeError):
        return "진단 실패: AI 서버 응답을 읽을 수 없습니다."
    try:
        if not isinstance(result, dict) or result.get("status") != "completed":
            return "진단 실패: AI 요청이 완료되지 않았습니다."
        parts = [
            x.get("text","")
            for item in result.get("output",[]) if isinstance(item,dict)
            for x in item.get("content",[]) if isinstance(x,dict) and x.get("type")=="output_text"
        ]
        probe_json = json.loads("".join(parts))
    except (ValueError, TypeError, KeyError):
        return "진단 실패: 모델이 요청한 JSON 응답을 만들지 못했습니다."
    if not isinstance(probe_json,dict) or probe_json.get("ok") is not True:
        return "진단 실패: AI 모델 응답 형식이 올바르지 않습니다."
    return "진단 성공: API 인증·모델 응답 정상. 실제 메일 회신 생성은 별도 확인이 필요합니다."
