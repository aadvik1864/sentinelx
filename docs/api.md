# API

Base path: `/api/v1`. JSON request/response bodies. Integer IDs are API identifiers; `EVT-00001`, `ALT-00001`, and `INC-00001` are display references. List endpoints return `items`, `total`, `limit`, and `offset` unless documented as a small configuration list.

Interactive OpenAPI docs are disabled by default. Development-only opt-in: `API_DOCS_ENABLED=true` exposes `/api/docs` and `/api/openapi.json`; production rejects that setting. API hosts must be explicitly listed in `ALLOWED_HOSTS` (defaults: `localhost,127.0.0.1`).

## Sessions

| Method | Path | Access |
|---|---|---|
| POST | `/auth/register` | ADMIN only; compatibility alias for creating a VIEWER |
| POST | `/auth/login` | Public, rate limited |
| POST | `/auth/refresh` | Rotating HTTP-only refresh cookie |
| POST | `/auth/logout` | Revokes cookie session family |
| GET | `/auth/me` | Authenticated |
| POST | `/auth/change-password` | Authenticated, current password required |

Login accepts `{ "email": "…", "password": "…" }` and returns `{ "access_token": "…", "token_type": "bearer", "user": { … } }`. Access tokens belong in `Authorization: Bearer …`, not local storage or URLs. The browser keeps them in memory. Refresh cookies use the `/api/v1/auth` path, SameSite Strict, and HTTP-only; Secure is mandatory in production. Cookie-backed mutations require an approved `Origin` header.

## Permissions

| Resource | VIEWER | ANALYST | ADMIN |
|---|---|---|---|
| Dashboard, alerts, incidents | Read | Read/write alert/case workflows | Same |
| Events | None | Read/ingest | Same |
| Assets, rules | None | Read | Create/edit (delete rules) |
| Log sources | None | Status/setup read | Create, pause/resume, replace key |
| Intelligence, assistant | None | Use | Use |
| Users, audit trail | None | Assignee names only | Create accounts / manage roles / read audit |
| Isolated simulator | None | None | Development + explicit demo flag only |

There is no organization boundary in this single-workspace MVP. There is no anonymous sign-up. Administrators admit trusted people; intentionally admitted Viewers can read shared alert evidence and investigation notes.

## Events

- `GET /events`: `q`, `severity`, `source`, `source_id` (a collector connection), `event_type`, `source_ip`, `destination_ip`, `hostname`, `username`, `start_time`, `end_time`, `limit` (1–200), `offset`.
- `GET /events/{id}`.
- `POST /events`: normalized event, returns `{ event, alerts, incident_id }`.
- `POST /events/raw`: `{ source, line, hostname, timestamp? }`.

```json
{
  "timestamp": "2026-10-08T10:30:00Z",
  "source": "linux",
  "event_type": "authentication_failure",
  "severity": "medium",
  "source_ip": "203.0.113.42",
  "hostname": "linux-lab-01",
  "username": "admin",
  "message": "Failed SSH authentication",
  "metadata": {}
}
```

Field search accepts `source_ip:203.0.113.42 severity:medium`, quoted strings, and plain message substrings. Fields are allowlisted; queries are not SQL. SQL LIKE wildcard characters in plain search are escaped. Time filters need UTC offsets. Maximum request body is 256 KB; events cap message/metadata sizes.

## Collector connections

| Method | Path | Access / body |
|---|---|---|
| GET | `/sources` | ADMIN/ANALYST; `{ items }` with status, counters, timestamps, and safe error text |
| GET | `/sources/agent` | ADMIN/ANALYST; downloadable Python agent |
| POST | `/sources` | ADMIN; `{ name, kind, hostname, log_path? }` |
| PATCH | `/sources/{id}` | ADMIN; `{ enabled }` |
| POST | `/sources/{id}/rotate-key` | ADMIN; revokes the previous key immediately |
| POST | `/sources/{id}/heartbeat` | That source's collector key; `{ state: "listening" }` or `{ state: "error", error: "file_unavailable" }` |
| POST | `/sources/{id}/events` | That source's collector key; `{ record_key, line, timestamp? }` |

Creating/replacing a key returns `{ source, collector_key }` once. Only its SHA-256 digest is stored; read responses/audit metadata never return the key or digest. Keys authorize ingestion/health **only for their source**, not dashboard access, raw-event reads, or source management. They have no automatic expiry; pause or replace them to revoke use. Keep private configuration files at 0600.

Supported kinds: `linux`, `nginx`, `apache`, `application`. The registered kind/hostname are authoritative; collectors cannot override them in a record. `record_key` is source-scoped, 16–128 safe identifier characters. Accepted retries return `{ event_id, duplicate: true }` without a second event/detection. Different content under the same key returns 409. Linux collection requires an explicit occurrence timestamp; JSON records require a timestamp in the envelope or record. Common/combined web logs supply their own occurrence time. Timestamp validation does not silently use receipt time for missing collector timestamps.

Heartbeat error codes are allowlisted rather than arbitrary collector exception strings. Paused sources return 403. Status becomes offline after 90 seconds without a heartbeat; waiting is not the same as offline. These endpoints never open the configured `log_path` on the backend. See [monitoring setup](monitoring.md) and [delivery limits](collectors.md).

## Alerts and incidents

| Method | Path | Body / behavior |
|---|---|---|
| GET | `/alerts` | severity/status/source IP/q/pagination |
| GET | `/alerts/{id}` | Includes triggering event and rule |
| PATCH | `/alerts/{id}` | `{ "status": "investigating" }` |
| GET | `/incidents` | severity/status/q/pagination |
| POST | `/incidents` | title, description?, severity?, event_ids?, alert_ids? |
| GET | `/incidents/{id}` | Chronological events, notes, alerts, IOCs |
| PATCH | `/incidents/{id}` | title?, severity?, status?, assigned_to? (null unassigns) |
| POST | `/incidents/{id}/notes` | content, kind (`note` / `evidence`) |
| POST | `/incidents/{id}/events` | event_ids, duplicate links ignored |
| POST | `/incidents/{id}/enrich` | Enrich up to 20 distinct linked source IPs |

Alert statuses: `open`, `acknowledged`, `investigating`, `resolved`, `false_positive`.
Incident statuses: `open`, `investigating`, `contained`, `resolved`.
Resolving an incident closes its related alerts except false positives. It never performs containment. Incident responses include up to 500 events and 500 notes; `event_total` and `evidence_truncated` expose event sampling.

## Configuration and assistance

- `GET/POST /rules`, `GET/PATCH/DELETE /rules/{id}`. PATCH preserves unspecified values. See [rule semantics](detection-rules.md).
- `GET/POST /assets`, `PATCH /assets/{id}`. Asset PATCH accepts the complete editable asset document.
- `GET /threat-intelligence/ip/{ip}`, `/domain/{domain}`, `/hash/{hash}`. Provider context is cached in IOC records; lookups are audit logged.
- `POST /ai/analyze-incident`: `{ "incident_id": 1 }`.
- `POST /ai/explain-alert`: `{ "alert_id": 1 }`.
- `GET /users`, `POST /users`, `PATCH /users/{id}` (ADMIN only). Creation accepts `{ "name": "…", "email": "…", "password": "…" }` and always creates a VIEWER; role fields are rejected. Names are trimmed; passwords must be 12–128 characters. Duplicate emails return 409. Creation audits the administrator and role, never the password. No invitation email is sent and starter-password change is recommended, not enforced. PATCH accepts `{ "role": "ANALYST" }`; self-demotion is disallowed.
- `GET /users/assignees`, `GET /audit-logs`, `GET /system`, `GET /dashboard`.
- `POST /demo/simulate`: development-only synthetic sequence.

AI responses include summary, likely_attack, evidence, affected_assets, mitre_techniques, qualitative confidence, recommended_investigation, recommended_containment, false_positive_indicators, mode, provider, model, and notice. `mode` is `offline` or `llm`; `provider` is `offline`, `ollama` (local), or `openai` (external compatible service). Invalid/provider-unavailable output returns 502 instead of a fabricated success; an already-active local generation returns 503. No external fallback occurs. The authenticated `/system` response reports `ai_provider` (`offline`, `ollama`, or legacy external label `llm`) and `ai_model`, not credentials or internal URLs. This is configured state, not a provider health check.

## Real-time protocol

Connect to `/ws/events`, `/ws/alerts`, or `/ws/incidents` from an approved origin. Send `{ "token": "<access token>" }` as the first frame within 10 seconds. Tokens are never query parameters. Events require an analyst/admin role; alert/incident streams allow viewers.

Server messages: `connected`, `heartbeat`, `new_event`, `new_alert`, `updated_alert`, `new_incident`, `updated_incident`, `reconcile`. Payloads use `{ "type": "new_alert", "data": { … } }`. Revalidate the session on each broadcast/20-second heartbeat. After reconnect, fetch REST state—there is no replay cursor.

Errors: 401 unauthenticated/expired, 403 unauthorized/origin, 404 missing, 409 conflicts, 413 oversized, 422 invalid input, 429 throttled, 502 upstream failure, 503 unavailable infrastructure.
