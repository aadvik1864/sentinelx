# Architecture

## A complete vertical slice

The backend accepts normalized events or a raw log envelope. Pydantic validates types, address formats, timezone-aware timestamps, metadata size, port/status ranges, and input limits. The normalizer recognizes Linux SSH/sudo logs, web access logs, and application JSON.

The ingestion service stores the event and evaluates enabled rules in the same SQLAlchemy transaction. Matching alerts create or join an open incident. Evidence links, severity escalation, and ATT&CK mappings commit with the detection. Errors roll back the transaction. The event API returns the committed event, newly created alerts, and correlated incident ID.

Real collectors instead call `/sources/{id}/events` with a source-only credential. PostgreSQL locks the source row and commits a unique source/record receipt with the event/detection/counters. A stable replay returns the original event ID; it does not run detection twice. A local private SQLite checkpoint/pending payload survives collector restarts. Source health is explicit and independent of the browser's live notification status. The gateway/application omit ingestion, health, and polling traffic to avoid feeding event notifications back into collection. See [monitoring](monitoring.md).

```text
POST /events or /events/raw
  → authorization + rate limit
  → validation / normalization
  → database transaction
      event + matching alerts + incident + evidence
  → commit
  → Redis Pub/Sub notification
  → authenticated WebSocket
  → REST reconciliation in React
```

## Concurrency and consistency

- PostgreSQL transaction-scoped advisory locks serialize ingestion for the same source-IP/hostname group across processes. A development-only in-process lock covers SQLite.
- Detection windows use UTC event time, not arrival time. Server receipt time is stored separately as `created_at`.
- Source IP **and target hostname** are part of detection and incident grouping. Successful-login patterns additionally require the same username.
- A rule/group creates one alert per configured suppression window. The matching event count is refreshed as activity continues.
- Related open incidents correlate for 30 minutes of event-time activity. A resolved incident is not reopened automatically. Subsequent suppressed activity can still be stored without creating a new case.
- Redis Pub/Sub is ephemeral. A crash after commit and before publication can lose a notification, but not the database record. REST fetches on reconnect and every 30 seconds restore the view. This is not an exactly-once system.
- WebSocket queues are bounded to 100 messages. Under backpressure, old notifications can be dropped; clients reconcile authoritative database state.
- The browser never derives authoritative metrics from synthetic counters. `/dashboard` performs database aggregations for the last 24 hours.

## Storage

PostgreSQL is the Compose/default deployment database; SQLite is the explicit developer fallback. Alembic owns schema changes. Application startup does not silently create tables. Startup bootstraps an administrator only when an explicit password is configured. A persistent audit marker makes default rule installation one-time, preserving rule edits/deletions across restarts.

Events are indexed by time/type/source and by the compound detection grouping key. The MVP uses bounded pagination but deliberately does not attempt a custom search datastore or enterprise-scale ingestion. Window evaluation loads candidate rows; sustained high-volume workloads need indexed aggregate queries, worker processing, and capacity testing.

## Integrations

Threat intelligence is behind a provider interface. AbuseIPDB is optional for public IPs; domain/hash and non-public address requests return provenance-aware local context. Results cache for six hours and can link to incidents. Unknown reputation is not a benign verdict.

The SOC assistant retrieves up to 100 recent linked events. External LLM context allows at most 100 records with 500-character messages and a 60,000-character JSON budget; the optional free local Qwen3/Ollama integration uses at most 20 records, 300-character messages, and a 12,000-character budget. Selected intelligence fields, assets, and mappings are included; arbitrary metadata, notes, and configuration are excluded. Character budgets can reduce the sample further and are not exact token counts. Responses are validated against a schema, asset/technique allowlists, and supplied event reference IDs; each evidence item must cite an actual supplied record. Validation is not factual verification. There is no action executor or tool access. `LLM_PROVIDER=offline` returns deterministic analysis with `mode: offline`; `auto` preserves key-based external/offline selection. Ollama returns `mode: llm`, `provider: ollama`, requires no key, and never falls back to an external service. See [local AI setup](local-ai.md).

## Extension path

1. Durable ingestion queue and transactional outbox before introducing multiple detection workers.
2. Broader ingestion idempotency beyond source collectors, late-event watermarking, and retroactive pattern evaluation.
3. Retention/partitioning and aggregate window evaluation with measured performance targets.
4. Organization isolation, resource-scoped RBAC, managed collector-secret distribution, and security review.
5. Additional authorized providers, audited playbooks with manual approvals, and optional RAG.
