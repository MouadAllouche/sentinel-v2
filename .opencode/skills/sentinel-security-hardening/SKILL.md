---
name: sentinel-security-hardening
description: Security requirements for Sentinel itself - authentication, sessions, CSRF, RBAC, login throttling, headers, input validation, secrets handling, outbound notification safety, safe parsing, and audit. Load when writing auth, API, web, notification, drift, or any code touching secrets or untrusted input.
---

# Hardening checklist

**Auth**: users in DB; `hashlib.scrypt` (n=2^15, r=8, p=1, 16-byte salt, 32-byte key; encoded `scrypt$n$r$p$salt$hash`); `hmac.compare_digest`; min 12 chars; common-password list; rehash on login if params changed; no default credentials; first admin via interactive CLI (`getpass`, never argv); no self-registration.
**Sessions**: 256-bit random token, store only SHA-256; cookie `HttpOnly; SameSite=Strict; Path=/` (+`Secure` behind HTTPS); idle + absolute timeouts; rotate on login; revoke on logout/password change/disable.
**CSRF**: double-submit cookie token HMAC'd with `SENTINEL_SESSION_KEY`; header `X-CSRF-Token` on all unsafe methods; check `Origin`/`Host`.
**Login throttling**: count by username and IP; lock after 5 failures/15 min; uniform error + timing (dummy hash); audit.
**RBAC**: `viewer` read-only; `admin` mutates. Enforce on the **server**; the UI only hides.
**Headers**: nosniff, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on authed JSON; web: strict CSP (`default-src 'self'`, `frame-ancestors 'none'`, `connect-src 'self'`), `X-Frame-Options: DENY`. No CORS (same-origin proxy).
**Input**: pydantic forbid-extra, size limits, bounded params, parameterised SQL, regex safety (length, nested quantifiers), path validation for monitored paths (absolute, normalised, allowed prefixes, no traversal), CSV formula-injection protection (`= + - @` prefixed with `'`), markdown-lite sanitisation for notes (no raw HTML).
**Secrets**: only env vars; DB stores env-var **names**; UI shows "set/not set" never values; never log secrets (logging redaction filter for `password|secret|token|authorization|cookie`); `.env` git-ignored; `.env.example` has placeholders only.
**Stored data**: never file contents, command args/cmdlines, key material, shadow contents.
**Outbound**: only enabled notification channels; global kill switch default off; timeouts, retries with backoff, HMAC-signed webhooks, SMTP STARTTLS required; payloads contain no secrets/contents; tests use fake transports.
**Parsing**: treat logs as hostile; length caps; no `eval/exec/shell=True`; fuzz parsers.
**Audit**: every mutation (who, what, before, after, IP) in the same transaction.
**Self-protection**: engine and API run as unprivileged user in group `adm`; systemd hardening in deploy docs; API/web bind to 127.0.0.1.
