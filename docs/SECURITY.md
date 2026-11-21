# Security

## Threat model

Sentinel is a **read-only observer** on one Linux server. It defends the administrator's ability to
see evidence: an operator who loses access to logs still has stored, explained events. It does
**not** defend against a root-level attacker, does not block IPs, kill processes or change files on
the monitored host, and is not an intrusion prevention system.

Trust boundaries:

- **Monitored system** (untrusted input): log lines, process lists, network snapshots, file metadata.
  Parsers treat every line as hostile, cap lengths, and never interpolate input into SQL or commands.
- **Sentinel DB** (trusted but sensitive): events, findings, incidents, users, sessions, config.
  It belongs to Sentinel only and is never shared with the monitored workload.
- **Browser** (untrusted client): the UI may hide controls but every mutation is checked server-side.
- **Notification destinations** (outbound): only enabled channels receive data, and only titles,
  severities and reasons — never file contents or secrets.

## Authentication and sessions

Users are stored in the DB with `scrypt$n$r$p$salt$hash` (n=2^15, r=8, p=1, 16-byte salt,
32-byte key), verified with `hmac.compare_digest`. There are no default credentials and no
self-registration; the first admin is created interactively. Passwords must be at least 12
characters and are checked against a small common-password list. Failed logins are counted per user
and per IP, lock for 15 minutes with exponential repeats, and return a uniform error.

Sessions use a 256-bit random token; only its SHA-256 hash is stored. Cookies are `HttpOnly`,
`SameSite=Strict`, `Path=/` and become `Secure` behind TLS. Sessions rotate on login and are revoked
on logout, password change and disable.

## CSRF and RBAC

Unsafe methods require `X-CSRF-Token` matching an HMAC of the session id, plus a matching `Origin`
when supplied. Viewers may read; admins mutate. RBAC is enforced by dependencies on every mutating
route, not by the UI.

## Secrets

SMTP passwords, webhook secrets and bot tokens are read from environment variables. The DB stores
only the variable **name**; the API reports a boolean "set/not set" and never the value. `.env` is
git-ignored and `.env.example` contains placeholders only. Log output passes through a redaction
filter for `password`, `secret`, `token`, `authorization` and `cookie`.

## Stored and never stored

Stored: normalised events, hashes, severity provenance, enrichment flags, metadata-only snapshots
(hashes of files, fingerprints of keys), findings, incidents, score reasons, audit rows and config.

Never stored: `/etc/shadow` contents, private keys, full process command lines, file contents,
notification secrets or session tokens. Monitored paths such as shadow files are forced to
`metadata_only`.

## Headers and proxy

The web app sets a nonce-based CSP (`default-src 'self'`, `connect-src 'self'`,
`frame-ancestors 'none'`), `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and
`X-Content-Type-Options: nosniff`. The API sends `Cache-Control: no-store` on authenticated JSON.
The reverse proxy should terminate TLS, enable HSTS, disable buffering for `/api/stream`, and
restrict source IPs; SSH tunnelling is the default remote-access method.
