# MASTER login denial diagnostics

Google authentication succeeded during live mailbox verification, but the app denied access with a combined account/expiration error. Add fixed, non-secret explanations to distinguish allowlist mismatch, expired identity, missing expiration and unverified email. No claims, tokens, secret values or configured allowlist are rendered. Existing authorization checks are unchanged; no accounts are added and no expiration check is bypassed. Actual mailbox checks remain pending until the existing access condition is satisfied.
