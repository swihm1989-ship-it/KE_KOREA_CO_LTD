# MASTER mailbox connection and KE KOREA welcome screen

## Mailbox

The Mailbox menu now uses a read-only Whois adapter rather than sample messages. Samples remain on the demo dashboard. Configure server-only top-level WHOIS_POP_* / WHOIS_SMTP_* values and the separate WHOIS_MAIL_OWNER_EMAILS allowlist. The latter contains Master OIDC login addresses, not necessarily the Whois mailbox address. The exact placeholder-only template is available in the authenticated mailbox screen. Insert top-level keys before [auth] or other TOML sections and preserve existing secrets. Never commit or send real passwords in chat.

Explicit POP3 TLS authentication + UIDL probe, SMTP TLS authentication probe (no sending), latest-30 refresh, plain text MIME/HTML fallback, bounded attachment downloads and selected-message handoff into the existing AI editor are implemented. No DELE or SMTP send commands exist. TLS certificate verification stays enabled; there is no plaintext fallback. Secrets are excluded from repr and error messages. Mailbox contents are kept in the current user's session, without shared/global caching or durable copies. Each fetch uses stable server UIDL values; this is not a persistent background synchronization service.

Message limit 5 MB, attachment limit 2 MB, refresh batch limit 20 MB, maximum ten attachments per message. Larger messages/attachments are reported and skipped. Missing or non-owner mailbox configuration fails closed. Account changes discard the old session mailbox. Importing a selected mail clears old transaction fields, generated files and AI consents. The user must review the imported text and explicitly consent again; attachments are not automatically sent to AI.

Actual mailbox authentication is pending: no account address, product-specific hosts or private credentials have been supplied. Outbound sending, durable send-intent claims and background polling are not enabled. Existing demo email review remains non-sendable. This phase prepares the connection and real read-only inbox; it does not claim a live connected account.

## Welcome screen

Reference: user-provided blue/white login image. Use the existing KE KOREA logo at top right, navy/blue/cyan palette, MASTER GRAPH identity, Korean headline and white Google-login panel. Mobile CSS at 640 and 360 pixels. The existing Google OIDC action is reused, with the same verified-email/expiry/allowlist checks. No anonymous preview, private data or new authentication bypass is added. Missing configuration/unauthorized accounts remain blocked.

## Verification

153 orchestration tests passed, including three welcome-screen AppTests and 12 mailbox adapter/UI cases. The unauthenticated library test now asserts the redesigned public hero while retaining the assertions that workspace controls are absent. Full offline legacy suite: 645/648 passed; existing ECLADO seed failures remain test_eclado_local_seed_has_separate_purchase_and_buyer_price_tables, test_dear_glow_price_is_not_applied_to_an_unregistered_buyer, test_purchase_and_sale_prices_are_selected_by_document_direction. All three were also present on unchanged main. git diff --check passed. No live mail login, fetch or send occurred during development; protocol tests use synthetic messages and fake transports. Production OIDC and real mailbox verification require the account configuration. Existing README files remain unchanged under the owner's MASTER documentation exception; current behavior is recorded here.
