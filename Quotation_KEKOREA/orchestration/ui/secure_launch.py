"""Render-only OIDC config loader for the independent Streamlit app.

Never print credentials. Settings are written at runtime with private
permissions and are not committed to Git. Missing settings fail closed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse


def build_oidc_secrets(env: dict[str, str]) -> str | None:
    keys = {
        "client_id": "ORCHESTRATION_OIDC_CLIENT_ID",
        "client_secret": "ORCHESTRATION_OIDC_CLIENT_SECRET",
        "server_metadata_url": "ORCHESTRATION_OIDC_METADATA_URL",
        "redirect_uri": "ORCHESTRATION_OIDC_REDIRECT_URI",
        "cookie_secret": "ORCHESTRATION_OIDC_COOKIE_SECRET",
    }
    values = {name: str(env.get(key) or "").strip() for name, key in keys.items()}
    if not all(values.values()):
        return None
    redirect = urlparse(values["redirect_uri"])
    metadata = urlparse(values["server_metadata_url"])
    if (metadata.scheme != "https" or not metadata.netloc or
            (redirect.scheme != "https" and not (
                redirect.scheme == "http" and redirect.hostname in {"localhost", "127.0.0.1"}
            )) or not redirect.netloc or
            not redirect.path.endswith("/oauth2callback") or
            len(values["cookie_secret"]) < 32):
        raise ValueError("Invalid secure OIDC configuration")
    return "[auth]\n" + "".join(f"{key} = {json.dumps(value)}\n"
                                for key, value in values.items())


def configure_runtime(env: dict[str, str], root: Path):
    content = build_oidc_secrets(env)
    if content is None:
        return False
    folder = root / ".streamlit"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = folder / "secrets.toml"
    with destination.open("w", encoding="utf-8") as handle:
        os.chmod(destination, 0o600)
        handle.write(content)
    return True


def probe_smtp_on_startup(env: dict[str, str]) -> None:
    """One-shot, no-send SMTP handshake/auth probe; log only safe status."""
    import logging
    from Quotation_KEKOREA.orchestration.adapters.whois_mail import (
        mail_config, probe_smtp, MailConnectionError,
    )
    logger = logging.getLogger("master.smtp.startup")
    try:
        owner = str(env.get("WHOIS_SMTP_USERNAME", "")).strip()
        config = mail_config(env, owner)
        if config.smtp is None:
            logger.warning("smtp_startup_probe result=not_configured")
            return
        endpoint = config.smtp
        allow_legacy = (
            endpoint.host.lower() == "smtp.whoisworks.com"
            and endpoint.port == 587 and endpoint.security == "starttls"
        )
        probe_smtp(endpoint, allow_legacy_dh=allow_legacy)
        logger.warning("smtp_startup_probe result=success port=%d security=%s",
                       endpoint.port, endpoint.security)
    except MailConnectionError as exc:
        # Only the adapter's sanitized error is safe to emit.
        logger.warning("smtp_startup_probe result=failed reason=%s", str(exc))
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        logger.warning("smtp_startup_probe result=configuration_or_network_error")


def verify_public_staging_lab() -> None:
    """Run synthetic regression tests on the deployed Render instance.

    A failed test prevents the new staging deployment from becoming live,
    without affecting the separate production app. No real mail or API use.
    """
    from Quotation_KEKOREA.orchestration.workflows.multiagent_staging import smoke_tests

    results = smoke_tests()
    passed = sum(1 for _, ok in results if ok)
    print(f"multiagent_staging_smoke passed={passed} total={len(results)}", flush=True)
    if passed != len(results):
        failed_names = [label for label, ok in results if not ok]
        raise RuntimeError("Staging regressions failed: " + ", ".join(failed_names))


def main():
    root = Path.cwd()
    configured = configure_runtime(dict(os.environ), root)
    if not configured:
        # No secret content emitted. UI login gate remains locked.
        print("OIDC configuration unavailable: private workspace remains locked.")
    verify_public_staging_lab()
    # The public lab has no SMTP credentials or mail access; skip SMTP probe.
    port = os.environ.get("PORT", "8501")
    if not port.isdigit():
        raise ValueError("Invalid server port")
    os.execv(
        os.sys.executable,
        [os.sys.executable, "-m", "streamlit", "run",
         "Quotation_KEKOREA/orchestration/ui/streamlit_page.py",
         "--server.address", "0.0.0.0", "--server.port", port,
         "--server.headless", "true", "--browser.gatherUsageStats", "false",
         "--client.toolbarMode", "minimal", "--ui.hideTopBar", "true"],
    )


if __name__ == "__main__":
    main()
