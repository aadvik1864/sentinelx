# Detection rules

Defaults are JSON files under `detection-rules/`; they are installed once and become database-managed configuration. Administrator edits/enable/disable/delete operations are audit logged and persist across restarts.

| Pattern | Defaults | Evidence / ATT&CK |
|---|---|---|
| `threshold` | 10 failures in 300s, high | Same source/target; T1110 |
| `successful_after_failures` | Success after ≥10 failures in 300s, critical | Same source/target/user; T1110, T1078 |
| `privilege_escalation` | Privileged event, high | sudo/su activity; T1548.003 |
| `port_scan` | ≥8 distinct destination ports in 60s, high | Validated normalized connection metadata; T1046 |
| `http_errors` | ≥500 requests, ≥0.30 error ratio in 300s, medium | HTTP status ≥400 is an error; no inferred technique |
| `suspicious_authentication` | Success after ≥5 failed/invalid-user events in 300s, critical | At least one invalid-user flag/event; T1110, T1078 |

Thresholds are **inclusive** (`>=`). A threshold of 10 triggers on the tenth matching event. Windows include both endpoints and group by source IP and hostname. Source-less events do not trigger network/authentication thresholds. Privileged events can trigger without an IP, but are not automatically attributed to an earlier SSH source.

Successful-login patterns additionally match the successful event's username. Failed attempts against another account/host do not establish that the successful account was brute-forced.

```json
{
  "name": "SSH brute force",
  "kind": "threshold",
  "event_type": "authentication_failure",
  "threshold": 10,
  "window_seconds": 300,
  "severity": "high",
  "enabled": true,
  "mitre_techniques": ["T1110"],
  "config": {}
}
```

Windows/thresholds/severity/technique IDs are validated. Supported config is `error_ratio` (strictly greater than zero, at most one) and optional `sources` (a non-empty list of supported log formats). A sources scope filters both the triggering event and historical evidence; it is a format scope, not a connection-ID scope. There is no execution of arbitrary rule expressions or uploaded Python.

The local real-monitoring setup scopes the SSH/sudo rules to `linux` and installs separate `application` authentication/error-burst rules, so app sign-ins are not labeled SSH attacks. In the rule editor, use **Log formats** to change this scope. Application error-burst rules need client IPs under the existing threshold grouping semantics; source-less errors remain searchable but do not trigger that rule. Multiple connections sharing a hostname/IP can contribute to the same format-scoped detection/case; use distinct logical hostnames when separate virtual hosts/apps should not be grouped.

Alert suppression uses a rule/source/host window around the matched event timestamp; subsequent matches update the count without repeatedly opening cases. Sustained activity beyond the initial suppression window may generate another alert. Open incidents correlate by source/host for 30 minutes; severity only escalates automatically.

## Interpretation and limits

A match is a detection hypothesis, not proof of compromise. Authorized administration, legitimate retries, and penetration tests can trigger these deliberately simple patterns. The privileged-activity rule intentionally does not infer whether sudo was malicious.

The engine evaluates the newly arriving event. It does not replay past success events when older failures arrive later. Use chronological input for the demo; late events remain searchable but need analyst review. Port-scan ingestion describes connection records; the simulator does not perform actual network scans. Rule changes affect future ingestion and do not backfill historical events.
