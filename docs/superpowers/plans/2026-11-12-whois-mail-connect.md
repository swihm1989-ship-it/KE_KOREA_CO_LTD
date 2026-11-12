# Whois Mail Connection Implementation Plan

**Goal:** Replace MASTER's demo-only inbox with an authenticated, read-only Whois inbox and explicit connection tests.
**Architecture:** Python standard-library POP3 and SMTP adapters, TLS required, server secrets only. An additional exact mailbox-owner allowlist limits access beyond general app login. Explicit refresh retrieves up to 30 messages and bounded attachments into the current user's session; no deletion, durable mailbox copy, implicit AI request or SMTP send. A selected message can populate the existing AI request editor; the existing AI consent must be checked again.
**Spec:** Existing orchestration/README.md Whois POP3/SMTP design and user's authorization to start connecting.

## Scope and decisions

Use the existing POP3/SMTP design, rather than changing providers or automating the webmail UI. Implement connection/authentication and manual inbox refresh first because the actual mailbox, hosts and credentials are absent. Automatic background polling and outbound sending require durable synchronization/send records and actual account verification; they are not enabled in this phase. SMTP probe authenticates only and sends no message.

## Tasks

- [x] Write adapter regression tests: owner access denial, missing/invalid settings, TLS before authentication, UIDL identity, no DELE, MIME/plain text, attachment bounds, credential-redacted errors and no SMTP send.
- [x] Implement adapters/whois_mail.py: immutable config, TLS probe, bounded read-only fetch and MIME parsing. No third-party dependencies.
- [x] Add ui/mailbox_page.py: configuration status, copyable placeholder-only secrets template, separate POP/SMTP tests, manual refresh, local message/attachment display, explicit handoff to AI editor. No settings/password entry into chat or public files.
- [x] Switch only the Mailbox menu to the real inbox and keep sample dashboard workflows available. Stable sidebar widget key supports safe pre-render navigation callbacks.
- [x] Add Streamlit AppTest for no implicit network, missing/denied config, refresh and safe handoff with renewed AI consent. Run full orchestration tests and repository contract suite; record existing seed failures separately if still present.
- [ ] Review, publish PR, wait for CI, merge. Report account authentication as pending until the user fills private server secrets. No actual email sent during development.

## Review focus

No credentials in repr/errors/widgets; no mailbox access for ordinary app users absent owner allowlist; no fallback to plaintext on TLS failure; no previous-user message/consent leakage; hostile HTML and attachment names remain inert; failed refresh preserves same-account data with a stale warning.

## Added user requirement

Apply the supplied login reference to the public start screen with the KE KOREA logo top right, existing navy/blue/cyan palette, responsive Korean hero and real Google OIDC button. Preserve auth checks and do not add an anonymous preview. Covered by test_login_page.py and existing auth/library tests.
