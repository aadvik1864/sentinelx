# Operator acceptance and security review

**Default decision: NO-GO for deployment.** This is an acceptance template, not a record that controls were installed. The approved current scope is release preparation and a synthetic one-day-capacity test. No existing live installation, account, collector, secret, or database is to be replaced or exposed.

Keep the completed record and evidence in separately controlled private storage, not this public repository. Use references to secret-manager entries; never record actual secrets, recovery codes, private keys, raw logs, or personal account details here.

## Required decisions and evidence

| Control | Operator must supply and demonstrate | Owner/sign-off |
|---|---|---|
| Release identity | Reviewed commit, inspected CI run, exact deployed image IDs, migration rehearsal and rollback backup | Pending |
| Capacity | Average/peak rate, actual event sizes/types, retained-data budget and alert/evidence growth; repeat load/burst/soak tests at that size | Pending |
| Hosting and TLS | A separate approved target, hostname/origin, private service networks, trusted certificate, renewal procedure and tested expiry alert | Pending |
| Time | Maintained clock synchronization; no backward steps during acceptance; a tested skew alert and a runbook for rejecting affected test results | Pending |
| Secrets | Secret-manager delivery, unique credentials, encrypted storage, reviewed permissions, separately recoverable MFA key and private recovery custody | Pending |
| Database privilege | Reviewed bootstrap/migration/runtime role separation and grants; the bundled `POSTGRES_USER` application connection is a PostgreSQL administrator, not a least-privilege runtime role | Pending |
| People | Verified membership, least-privilege roles, private starter-password delivery, MFA enrollment, recovery identity checks and tested offboarding | Pending |
| Recovery | Approved off-host destination and age recipient; separately stored identity/config/MFA/collector checkpoints; schedule, RPO/RTO and a measured off-host restore drill | Pending |
| Retention | Approved raw-log period/legal holds, projected storage and protected evidence/receipt/audit lifecycle; review the dry-run before scheduling any write | Pending |
| Monitoring | External availability and collector-gap/quarantine/disk/backup/certificate/clock checks, actual notification channel, test alerts and acknowledged runbooks | Pending |
| Audit integrity | Separately controlled immutable destination; independently retained export cursor/hash; tested interruption/retry procedure | Pending |
| Independent review | Named independent reviewer, authorized scope, exact release reference, findings, remediation and retest evidence | Pending |

The one-day fixture is **864,000 records**, not a retention policy. Minimum raw retention is seven days; continuous 10 EPS would produce 6,048,000 records over that minimum, before permanently retained receipts, alerts, investigations and audit data. Do not approve that larger footprint from a one-day test. Select limits and capacity based on the actual average rate and legal/evidence obligations.

## Runbooks to rehearse

- **Availability:** run `scripts/health_check.py` from an external authorized monitor using the exact approved HTTPS origin and trusted CA. Connect nonzero exits to a real alert channel. The script does not schedule checks or send notifications itself; readiness is not proof of complete collection.
- **Collection gaps:** monitor connected-source health and the private collector's gap/quarantine notices. Confirm the affected time range and preserve checkpoints/quarantine before retrying; never delete replay protection to make counts look healthy.
- **Backup failure or age breach:** alert on absence of a successful encrypted backup, not just existence of a file. Preserve failed outputs separately, correct the cause, and verify a new off-host restore into a new `sentinelx_restore_<label>` database. Measure recovery time and recovered data against approved RPO/RTO.
- **Clock instability:** investigate the host/hypervisor time source outside the application. Re-run affected authentication/correlation/capacity checks on a stable runner; do not disable JWT time checks or alter live evidence timestamps to hide the failure.
- **Offboarding or lost MFA:** use administrator disabling for offboarding and independently verified operator MFA recovery for loss. Recovery revokes sessions; it never resets evidence, roles, or passwords automatically.
- **Retention:** approve legal holds and the dry-run, confirm the exact selected database, run bounded batches only after approval, and monitor backlog/disk growth. No maintenance is scheduled by preparing this release.
- **Audit export:** exclusively create private exports, anchor their cursor/hash in the separately controlled destination, and resume only from its last acknowledged anchor. Local hashes alone are not tamper-resistant storage.
- **Rollback:** preserve the pre-migration backup and configuration; rehearse restoring separately. Receipt tombstones can make a schema downgrade intentionally unsafe; do not drop receipts, reset source keys, or discard collector checkpoints to force it.

Operational command details and constraints are in the [production release checklist](production-release.md).

## Independent security review brief

Authorize testing only on a separate synthetic fixture. Supply the exact source/image references, [security boundaries](security.md), [API contract](api.md), migrations and test reports. Include:

- Starter-password/MFA gates on REST and sockets; encrypted enrollment, replay protection, recovery codes, refresh/logout locking and disable/role-change races.
- Role boundaries, actor revalidation, account admission/offboarding, audit-secret exclusion and cookie/Origin/Host/TLS policy.
- Collector-key isolation, retries/tombstones, timestamp validation, retention/evidence preservation and upgrade/restore behavior.
- Assistant prompt-injection/privacy limitations and proof that recommendations have no action executor.
- Dependency/OS findings, container permissions, deployment secret/backup/egress boundaries and clock/capacity failure modes.

An author/assistant code review, passing CI, a dependency audit, or this template is **not an independent penetration test or security certification**. Record reviewer findings and retests privately. Final GO requires the accountable operator's approval of every applicable control; any unresolved required control means NO-GO.
