# Collectors and simulator

## Monitoring agent (real sources)

Use **Connected systems → Connect a system** or [the local three-source setup](monitoring.md). `collectors/agent.py` supports authorized files and one selected Compose container per source. It uses source-only hashed credentials, not a human refresh session. Default first start tails new records; subsequent starts resume checkpoints. Source formats are Linux auth/syslog, Nginx/Apache common/combined or supported JSON access logs, and application JSON-lines.

- A private SQLite state file stores device/inode/generation/byte offsets or container/timestamp cursors, plus one pending redacted payload per source. A pending payload is persisted **before** delivery. The cursor advances only after acknowledgement or explicit quarantine of a permanently rejected record.
- Network failures, server errors, and rate limits retry with bounded backoff. A response lost after commit is retried with the same record key; the server's source receipt and event commit together. Duplicate retries do not increment event/source totals or rerun detection. Reusing a key for different content returns 409 and is quarantined.
- Ordinary rename rotation is followed; retained sibling files with the saved inode are resumed after restart. Detectable truncation, vanished inodes, and container replacement produce persistent `log_gap` notices. Compressed/deleted logs cannot be recovered; rapid copytruncate that regrows past the old offset is not reliably detectable. Use rename rotation with sufficient retention rather than copytruncate.
- Docker follows timestamped stdout/stderr, replays inclusively from its checkpoint, and deduplicates stable container/timestamp/content keys. Containers removed/recreated during downtime can lose unread logs; same-timestamp identical records can collapse. The initial cursor is saved even if the stream is quiet. Docker retention is bounded to three 10 MB files for the local monitored containers.
- Linux ISO timestamps retain their offset; classic English syslog timestamps use the configured IANA/local timezone and current year with a New Year rollover heuristic. Old multi-year imports, localized syslog, journald/RFC5424 export, and DST ambiguity are not supported. JSON records must supply an offset-aware occurrence timestamp; web common/combined timestamps are parsed. Clocks more than 60 seconds ahead are rejected, not silently changed.
- Credential-like JSON fields, common password/token assignments, and Bearer values are redacted before spooling/transmission; web query strings are omitted. Redaction is best-effort, not a substitute for safe application logging. Raw invalid/oversized records are omitted from quarantine to avoid retaining unreviewed secrets. Server-rejected redacted payloads remain in private quarantine for operator review.
- Only the local self-monitoring sources set `self_monitoring=true`: ingestion, source management, health checks, and read-only API polling are excluded to prevent event-refresh loops. Other applications' API requests are **not** filtered by these SentinelX-specific exclusions.
- The process deliberately sends at most about eight requests/second across its sources (including heartbeats). It does not provide a high-volume spool: unread backlog stays in the original logs. Provision retention for outages and supervise collector/tunnel processes. State files and production evidence must remain outside git.

Rejected-record and gap notices stay visible until reviewed. Inspect the private SQLite `quarantine` and `notices` tables with an approved local database tool; after fixing the cause and preserving needed evidence, explicitly clear the reviewed entries for that source while its collector is stopped, then restart. Do not delete the checkpoint database merely to clear a warning; that loses replay state. Automatic quarantine repair/replay and an in-console acknowledgement workflow are not implemented.

## Legacy one-shot lab collector

`collectors/collect.py` forwards an authorized local log file to a **loopback SentinelX API**. It remains a simple lab/import utility, not the monitoring agent above. It never performs scans, exploits, or remote commands. Use an analyst account; the API enforces ingestion permissions. Dependencies are included in the backend requirements.

```bash
.venv/bin/python collectors/collect.py \
  --source linux \
  --file collectors/linux/sample.log \
  --hostname linux-lab-01 \
  --email admin@sentinelx.dev
```

Password entry is interactive and not shown in process arguments. Automation can set `SENTINELX_COLLECTOR_PASSWORD` through a secure environment. Other sources: `nginx`, `apache`, `application`. `--follow` reads appended lines but has no durable cursor or log-rotation support; restart manually after rotation. File permissions remain the operator's responsibility.

### Legacy timestamp semantics

The simple file collector supplies UTC **receipt time**, because classic syslog has neither year nor timezone. This is suitable for live lab demonstrations, not faithful historical imports. To preserve occurrence time, send normalized events with an explicit timestamp or submit raw envelopes with a known timezone-aware timestamp.

For direct raw API input without an override, Nginx/Apache timestamps are parsed; application JSON may supply a timestamp. Classic Linux syslog timestamps assume the current UTC year, with a New Year rollover heuristic. RFC5424/journald/locale-specific parsing is not implemented.

Sudo logs often omit source IPs. Such events produce standalone privileged-activity evidence unless the authorized source supplies a known IP in a normalized event. The collector does not guess network attribution.

### Legacy delivery limitations

The collector stops visibly on a rejected record, connection failure, or rate limit. It does not silently discard failed lines, implement persistent offsets, automatically recover rotations, or promise exactly-once delivery. Refresh tokens rotate when access expires, and the session is logged out after a completed non-following import. Restarting the collector can duplicate records.

## Isolated simulator

The UI simulator and CLI call the same administrator-only API, which requires `ENVIRONMENT=development` and `DEMO_MODE=true`.

```bash
.venv/bin/python scripts/simulate.py
```

Only synthetic record insertion occurs. The sequence uses 12 failed logins, success, and a privileged command record; it never executes the command. Source IPs are chosen from `203.0.113.0/24`, reserved for documentation, and events contain `metadata.simulated=true`. The CLI rejects non-loopback API destinations. The development gateway itself binds only to loopback by default.
