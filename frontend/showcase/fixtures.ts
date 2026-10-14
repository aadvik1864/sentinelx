import type {
  Alert,
  Incident,
  LogSource,
  Rule,
  SecurityEvent,
  User,
} from "../src/types";

export const demoUser: User = {
  id: 1,
  name: "Demo investigator",
  email: "investigator@example.test",
  role: "ANALYST",
  created_at: "2026-01-01T00:00:00Z",
};

export function createWorkspace(now = new Date()) {
  const at = (minutesAgo: number) =>
    new Date(now.getTime() - minutesAgo * 60000).toISOString();
  const sources: LogSource[] = [
    {
      id: 1,
      name: "Example Linux server",
      kind: "linux",
      hostname: "linux.example.test",
    },
    {
      id: 2,
      name: "Example website",
      kind: "nginx",
      hostname: "web.example.test",
    },
    {
      id: 3,
      name: "Example application",
      kind: "application",
      hostname: "app.example.test",
    },
  ].map((source) => ({
    ...source,
    kind: source.kind as LogSource["kind"],
    log_path: `/example/${source.kind}.log`,
    enabled: true,
    status: source.id === 3 ? "offline" : "receiving",
    token_expires_at: at(-90 * 1440),
    last_heartbeat_at: at(source.id === 3 ? 40 : 1),
    last_event_at: null,
    last_event_timestamp: null,
    last_error: "",
    total_events: 0,
  }));
  const events: SecurityEvent[] = [];

  function addEvent(
    sourceId: number,
    minutesAgo: number,
    values: Partial<SecurityEvent>,
  ) {
    const source = sources.find((item) => item.id === sourceId)!;
    const id = events.length + 1;
    const event: SecurityEvent = {
      id,
      reference: `EVT-${String(id).padStart(5, "0")}`,
      timestamp: at(minutesAgo),
      source: source.kind,
      event_type: "http_request",
      severity: "low",
      source_ip: "192.0.2.20",
      destination_ip: null,
      hostname: source.hostname,
      username: null,
      message: "GET /health 200",
      ...values,
      metadata: { ...values.metadata, source_id: sourceId, simulated: true },
    };
    events.push(event);
    return event;
  }

  for (let hour = 23; hour >= 0; hour--) {
    for (let index = 0; index < 2 + (hour % 3); index++) {
      addEvent(2, hour * 60 + 30 + index * 2, {});
    }
    addEvent(1, hour * 60 + 35, {
      event_type: "authentication_success",
      username: "sam",
      message: "Scheduled maintenance account signed in from 192.0.2.20",
    });
  }

  const signIns = Array.from({ length: 12 }, (_, index) =>
    addEvent(1, 18 - index / 5, {
      event_type: "authentication_failure",
      severity: "medium",
      source_ip: "203.0.113.42",
      username: "sam",
      message: "Failed password for sam from 203.0.113.42",
    }),
  );
  const accepted = addEvent(1, 14, {
    event_type: "authentication_success",
    source_ip: "203.0.113.42",
    username: "sam",
    message: "Accepted password for sam from 203.0.113.42",
  });
  const elevated = addEvent(1, 13, {
    event_type: "privilege_escalation",
    severity: "high",
    source_ip: "203.0.113.42",
    username: "sam",
    message: "sudo: sam : USER=root ; COMMAND=/usr/bin/id",
  });
  const failures = [48, 47, 46].map((minute) =>
    addEvent(3, minute, {
      event_type: "application_error",
      severity: "medium",
      source_ip: "198.51.100.18",
      message: "GET /checkout 503: upstream connection timed out",
      metadata: { http_status: 503 },
    }),
  );

  function rule(
    id: number,
    name: string,
    event: SecurityEvent,
    threshold: number,
  ): Rule {
    return {
      id,
      reference: `RULE-${String(id).padStart(5, "0")}`,
      name,
      description: "Synthetic example rule for the portfolio demo.",
      kind: "threshold",
      event_type: event.event_type,
      threshold,
      window_seconds: 300,
      severity: event.severity,
      enabled: true,
      mitre_techniques: [],
      config: {},
    };
  }

  const alerts: Alert[] = [
    {
      id: 1,
      title: "Repeated sign-in attempts",
      event: signIns[11],
      count: 12,
      incident: 1,
      severity: "high",
      techniques: ["T1110"],
    },
    {
      id: 2,
      title: "Elevated access after a sign-in",
      event: elevated,
      count: 1,
      incident: 1,
      severity: "high",
      techniques: ["T1548.003", "T1078"],
    },
    {
      id: 3,
      title: "Application requests are failing",
      event: failures[2],
      count: 3,
      incident: 2,
      severity: "medium",
      techniques: [],
    },
  ].map((sample) => ({
    id: sample.id,
    reference: `ALT-${String(sample.id).padStart(5, "0")}`,
    title: sample.title,
    description: "A pattern in fictional activity, not a confirmed attack.",
    severity: sample.severity as Alert["severity"],
    status: "open",
    source_ip: sample.event.source_ip,
    hostname: sample.event.hostname,
    event_count: sample.count,
    created_at: sample.event.timestamp,
    detected_at: sample.event.timestamp,
    incident_id: sample.incident,
    mitre_techniques: sample.techniques,
    event: sample.event,
    rule: rule(sample.id, sample.title, sample.event, sample.count),
  }));

  const incidents: Incident[] = [
    {
      id: 1,
      title: "Review access to the example Linux server",
      description:
        "Repeated failures were followed by a successful sign-in and sudo use. Verify whether this was authorized maintenance.",
      severity: "high",
      events: [...signIns, accepted, elevated],
      techniques: ["T1110", "T1078", "T1548.003"],
    },
    {
      id: 2,
      title: "Check the example checkout service",
      description:
        "Three requests failed shortly after a fictional release. An outage is possible; these records do not establish an attack.",
      severity: "medium",
      events: failures,
      techniques: [],
    },
  ].map((sample) => ({
    id: sample.id,
    reference: `INC-${String(sample.id).padStart(5, "0")}`,
    title: sample.title,
    description: sample.description,
    severity: sample.severity as Incident["severity"],
    status: "open",
    assigned_to: 1,
    assigned_name: demoUser.name,
    source_ip: sample.events[0].source_ip,
    hostname: sample.events[0].hostname,
    created_at: sample.events[0].timestamp,
    updated_at: sample.events.at(-1)!.timestamp,
    resolved_at: null,
    mitre_techniques: sample.techniques,
    events: sample.events,
    event_total: sample.events.length,
    evidence_truncated: false,
    alerts: alerts.filter((alert) => alert.incident_id === sample.id),
    notes: [
      {
        id: sample.id,
        author: demoUser.name,
        kind: "note",
        content:
          "This is a fictional investigation. Try adding a note; it stays in this tab and disappears on reload.",
        created_at: at(10),
      },
    ],
    iocs: [],
  }));

  for (const source of sources) {
    const collected = events.filter(
      (event) => event.metadata.source_id === source.id,
    );
    source.total_events = collected.length;
    source.last_event_at =
      collected
        .map((event) => event.timestamp)
        .sort()
        .at(-1) ?? null;
    source.last_event_timestamp = source.last_event_at;
  }
  return { now: now.getTime(), events, alerts, incidents, sources };
}

export type Workspace = ReturnType<typeof createWorkspace>;
