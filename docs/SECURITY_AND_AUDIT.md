# Security, privacy and audit readiness

Written to help NIO's IT team and their CERT-In empanelled auditor. Confirm the exact checklist
NIO uses (often based on the OWASP Top 10 and CERT-In guidelines) and update this file to match.

## Data protection (Digital Personal Data Protection Act, 2023)

| Topic | How the platform handles it |
| --- | --- |
| Consent | Two-tier consent in the registration form: care for everyone; research use optional. Persons without research consent are excluded from research exports and research-only questions are skipped |
| Data minimisation | Names, phones and addresses are stored only in `person_pii`; everything else uses sticker IDs |
| Purpose limitation | Role-based access: scientists and ward members never receive names or phone numbers |
| De-identified exports | CSV exports omit identifiers and round GPS to about 100 m |
| Retention | To be set in the data-sharing agreement; backups are deleted after 30 days |
| Rights of the person | All records for a person share one sticker ID, so correction or erasure is a single database operation (an admin screen for this is still to build) |

Still needed before real data: ethics committee approval, a signed data-sharing agreement naming the
data fiduciary (MAGICS / CEDAC for health data, CSIR-NIO for environmental data), and a breach
response contact.

## Application security

| Control | Implementation |
| --- | --- |
| Authentication | Username and password; PBKDF2-SHA256, 310,000 iterations; 10-character minimum |
| Brute force | Account locked for 15 minutes after 5 failures; nginx limits login to 5 requests per minute per IP |
| Sessions | Signed JWT, 8-hour expiry, checked against an active user on every request |
| Authorisation | Role check on every endpoint, plus per-user site restriction |
| Audit log | Every API request: time, user, method, path, status, IP (`audit_log` table, Admin tab). CERT-In directions require logs to be kept for 180 days |
| Transport | HTTPS only (TLS 1.2/1.3), HSTS in production, HTTP redirected |
| Browser hardening | Content-Security-Policy (`default-src 'self'`, no inline scripts, no third-party scripts or fonts), X-Frame-Options DENY, nosniff, no-referrer |
| Output encoding | All data shown in the dashboard is HTML-escaped |
| Input validation | Typed request models; uploads limited to 5 MB CSV; form-level constraints in ODK |
| SQL injection | All queries through SQLAlchemy ORM with bound parameters |
| Errors | Generic error message to users; API docs disabled in production |
| Containers | App runs as a non-root user; database not exposed outside the Docker network |
| Secrets | Only in `.env` on the server, never in the code repository |
| Dependencies | Pinned in `requirements.txt`; scan with `pip-audit` before each release |
| Backups | Nightly, GPG-encrypted, 30-day retention |
| Third-party services | Open-Meteo (weather, no personal data). Sarvam AI (optional): receives only team-written message text, never names, phones or health records |

## Clinical safety

- Every household or community message is created as a **draft** and must be **approved by a
  doctor** before it can be marked sent (enforced by the API, tested).
- Risk levels and the scenario model are decision support for the team, not diagnoses.
- Model coefficients are priors until refitted on Phase 1 data; the dashboard says so.

## Suggested pre-audit checklist

- [ ] Run `pip-audit -r requirements.txt` and update any flagged package
- [ ] Run an automated scan (for example OWASP ZAP) against staging
- [ ] Replace demo users; confirm `OBS_ENVIRONMENT=production` (demo loader refuses to run)
- [ ] Set strong `OBS_SECRET_KEY` and `OBS_DB_PASSWORD`; rotate if ever shared
- [ ] Confirm log retention of 180 days and time sync (NTP) on the server
- [ ] Test a backup restore
- [ ] Review ODK Central's own security settings and keep it updated
