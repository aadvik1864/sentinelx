import type {
  Analysis,
  DashboardMetrics,
  Incident,
  SecurityEvent,
  Severity,
} from "../src/types";
import { createWorkspace, demoUser } from "./fixtures";
import type { Workspace } from "./fixtures";

export const AI_REQUEST_TIMEOUT = 200000;
const hour = 3600000;
const incidentStatuses = ["open", "investigating", "contained", "resolved"];
const alertStatuses = [
  "open",
  "acknowledged",
  "investigating",
  "resolved",
  "false_positive",
];
const priorities: Severity[] = ["critical", "high", "medium", "low"];

class DemoError extends Error {}

function find<T extends { id: number }>(rows: T[], id: number): T {
  const row = rows.find((item) => item.id === id);
  if (!row)
    throw new DemoError(
      "That example record does not exist. Choose one from the list.",
    );
  return row;
}

function body(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new DemoError("Enter the example's required fields.");
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, maximum: number, minimum = 0): string {
  if (
    typeof value !== "string" ||
    value.trim().length < minimum ||
    value.length > maximum
  ) {
    throw new DemoError(`Enter between ${minimum} and ${maximum} characters.`);
  }
  return value.trim();
}

interface Filterable {
  id: number;
  severity?: string;
  status?: string;
  timestamp?: string;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
}

function list<T extends Filterable>(rows: T[], params: URLSearchParams) {
  const limit = Math.min(200, Math.max(1, Number(params.get("limit")) || 25));
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const query = (params.get("q") ?? "").trim().toLowerCase();
  const searchableFields = new Set([
    "source_ip",
    "hostname",
    "username",
    "source",
    "event_type",
    "severity",
  ]);
  const filtered = rows
    .filter((row) => {
      const fields = row as unknown as Record<string, unknown>;
      if (
        ["severity", "status", "source"].some(
          (key) => params.get(key) && fields[key] !== params.get(key),
        )
      )
        return false;
      if (
        params.get("source_id") &&
        row.metadata?.source_id !== Number(params.get("source_id"))
      )
        return false;
      if (
        params.get("start_time") &&
        row.timestamp &&
        row.timestamp < params.get("start_time")!
      )
        return false;
      if (
        params.get("end_time") &&
        row.timestamp &&
        row.timestamp > params.get("end_time")!
      )
        return false;
      return query.split(/\s+/).every((term) => {
        const separator = term.indexOf(":");
        const key = term.slice(0, separator);
        if (separator > 0 && searchableFields.has(key)) {
          return String(fields[key] ?? "")
            .toLowerCase()
            .includes(term.slice(separator + 1));
        }
        return JSON.stringify(row).toLowerCase().includes(term);
      });
    })
    .sort(
      (a, b) =>
        (b.timestamp ?? b.updated_at ?? b.created_at ?? "").localeCompare(
          a.timestamp ?? a.updated_at ?? a.created_at ?? "",
        ) || b.id - a.id,
    );
  return {
    items: filtered.slice(offset, offset + limit),
    total: filtered.length,
    limit,
    offset,
  };
}

function dashboard(workspace: Workspace): DashboardMetrics {
  const { now, events, alerts, incidents, sources } = workspace;
  const active = alerts.filter(
    (alert) => !["resolved", "false_positive"].includes(alert.status),
  );
  const addresses = [
    ...new Set(
      events.map((event) => event.source_ip).filter((ip): ip is string => !!ip),
    ),
  ];
  return {
    total_events: events.length,
    events_per_second: 0,
    active_alerts: active.length,
    critical_alerts: active.filter((alert) => alert.severity === "critical")
      .length,
    open_incidents: incidents.filter(
      (incident) => incident.status !== "resolved",
    ).length,
    resolved_incidents: incidents.filter(
      (incident) => incident.status === "resolved",
    ).length,
    monitored_assets: sources.length,
    unique_source_ips: addresses.length,
    severity_counts: Object.fromEntries(
      priorities.map((priority) => [
        priority,
        alerts.filter((alert) => alert.severity === priority).length,
      ]),
    ) as Record<Severity, number>,
    activity: Array.from({ length: 24 }, (_, index) => {
      const start = now - (24 - index) * hour;
      return {
        timestamp: new Date(start).toISOString(),
        events: events.filter((event) => {
          const timestamp = new Date(event.timestamp).getTime();
          return timestamp >= start && timestamp < start + hour;
        }).length,
      };
    }),
    top_ips: addresses
      .map((ip) => ({
        ip,
        count: events.filter((event) => event.source_ip === ip).length,
      }))
      .sort((a, b) => b.count - a.count),
    event_types: [...new Set(events.map((event) => event.event_type))].map(
      (type) => ({
        type,
        count: events.filter((event) => event.event_type === type).length,
      }),
    ),
  };
}

function explain(incident: Incident): Analysis {
  const events = incident.events ?? [];
  return {
    mode: "offline",
    provider: "offline",
    model: null,
    confidence: "low",
    summary: `This fictional investigation contains ${events.length} linked records. ${incident.description}`,
    likely_attack:
      "The example shows a pattern to investigate, not proof of an attack.",
    evidence: events
      .slice(-5)
      .map((event) => `${event.reference}: ${event.message}`),
    affected_assets: [...new Set(events.map((event) => event.hostname))],
    mitre_techniques: incident.mitre_techniques,
    recommended_investigation: [
      "Read the linked records in time order.",
      "Verify maintenance and deployment activity with the system owner.",
    ],
    recommended_containment: [
      "Only consider changes after an authorized person has verified the evidence.",
    ],
    false_positive_indicators: [
      "Mistyped passwords, maintenance, or an application outage can explain some of this activity.",
    ],
    notice:
      "Browser-only sample summary. No model or external service was called, and no action was executed.",
  };
}

export function createDemoApi(now = new Date()) {
  const workspace = createWorkspace(now);

  function linkedEvents(value: unknown): SecurityEvent[] {
    if (
      !Array.isArray(value) ||
      value.length > 100 ||
      value.some((id) => !Number.isInteger(id))
    ) {
      throw new DemoError(
        "Choose up to 100 IDs from the example activity records.",
      );
    }
    return [...new Set(value)].map((id) => find(workspace.events, Number(id)));
  }

  function request(method: string, target: string, payload?: unknown): unknown {
    if (!target.startsWith("/") || target.startsWith("//")) {
      throw new DemoError("The showcase cannot connect to a server.");
    }
    const url = new URL(target, "https://showcase.invalid");
    if (url.origin !== "https://showcase.invalid") {
      throw new DemoError("The showcase cannot connect to a server.");
    }
    const path = url.pathname;
    const match = path.match(
      /^\/(alerts|incidents)\/(\d+)(?:\/(notes|events|enrich))?$/,
    );
    if (method === "GET") {
      switch (path) {
        case "/system":
          return {
            version: "showcase",
            environment: "browser-only",
            demo_mode: true,
            live_monitoring: false,
            ai_provider: "offline",
            threat_intel_provider: "unconfigured",
          };
        case "/dashboard":
          return dashboard(workspace);
        case "/sources":
          return { items: workspace.sources };
        case "/users/assignees":
          return { items: [{ id: demoUser.id, name: demoUser.name }] };
        case "/events":
          return list(workspace.events, url.searchParams);
        case "/alerts":
          return list(workspace.alerts, url.searchParams);
        case "/incidents":
          return list(workspace.incidents, url.searchParams);
      }
      if (match && !match[3]) {
        return match[1] === "alerts"
          ? find(workspace.alerts, Number(match[2]))
          : find(workspace.incidents, Number(match[2]));
      }
    }
    if (
      method === "POST" &&
      ["/ai/analyze-incident", "/ai/explain-alert"].includes(path)
    ) {
      const values = body(payload);
      const id =
        path === "/ai/explain-alert"
          ? find(workspace.alerts, Number(values.alert_id)).incident_id
          : Number(values.incident_id);
      return explain(find(workspace.incidents, Number(id)));
    }
    if (method === "POST" && path === "/incidents") {
      const values = body(payload);
      if (workspace.incidents.length >= 20)
        throw new DemoError(
          "This tab has enough practice investigations. Reset the demo to start again.",
        );
      if (!priorities.includes(values.severity as Severity))
        throw new DemoError("Choose an investigation priority.");
      const events = linkedEvents(values.event_ids ?? []);
      const id =
        Math.max(...workspace.incidents.map((incident) => incident.id)) + 1;
      const created = new Date().toISOString();
      const incident: Incident = {
        id,
        reference: `INC-${String(id).padStart(5, "0")}`,
        title: text(values.title, 200, 3),
        description: text(values.description, 8000),
        severity: values.severity as Severity,
        status: "open",
        assigned_to: null,
        hostname: events[0]?.hostname ?? "",
        source_ip: events[0]?.source_ip ?? null,
        created_at: created,
        updated_at: created,
        resolved_at: null,
        mitre_techniques: [],
        events,
        event_total: events.length,
        evidence_truncated: false,
        alerts: [],
        notes: [],
        iocs: [],
      };
      workspace.incidents.push(incident);
      return incident;
    }
    if (match && method === "PATCH" && !match[3]) {
      const values = body(payload);
      if (match[1] === "alerts") {
        const alert = find(workspace.alerts, Number(match[2]));
        if (!alertStatuses.includes(String(values.status)))
          throw new DemoError("Choose an alert status.");
        alert.status = String(values.status);
        return alert;
      }
      const incident = find(workspace.incidents, Number(match[2]));
      if (
        values.status !== undefined &&
        !incidentStatuses.includes(String(values.status))
      ) {
        throw new DemoError("Choose an investigation status.");
      }
      if (
        values.severity !== undefined &&
        !priorities.includes(values.severity as Severity)
      ) {
        throw new DemoError("Choose an investigation priority.");
      }
      if (
        values.assigned_to !== undefined &&
        values.assigned_to !== null &&
        values.assigned_to !== demoUser.id
      ) {
        throw new DemoError("Choose the example investigator.");
      }
      if (values.status !== undefined) {
        incident.status = String(values.status);
        incident.resolved_at =
          incident.status === "resolved" ? new Date().toISOString() : null;
        if (incident.status === "resolved") {
          for (const alert of incident.alerts ?? []) {
            if (alert.status !== "false_positive") alert.status = "resolved";
          }
        }
      }
      if (values.severity !== undefined) {
        incident.severity = values.severity as Severity;
      }
      if (values.assigned_to !== undefined) {
        incident.assigned_to = values.assigned_to as number | null;
        incident.assigned_name =
          values.assigned_to === null ? undefined : demoUser.name;
      }
      incident.updated_at = new Date().toISOString();
      return incident;
    }
    if (match?.[1] === "incidents" && method === "POST" && match[3]) {
      const incident = find(workspace.incidents, Number(match[2]));
      if (match[3] === "notes") {
        const values = body(payload);
        const notes = (incident.notes ??= []);
        if (notes.length >= 100)
          throw new DemoError(
            "Reset the demo before adding more practice notes.",
          );
        if (!["note", "evidence"].includes(String(values.kind)))
          throw new DemoError("Choose a contribution type.");
        const note = {
          id: Math.max(0, ...notes.map((item) => item.id)) + 1,
          content: text(values.content, 8000, 1),
          kind: String(values.kind),
          author: demoUser.name,
          created_at: new Date().toISOString(),
        };
        notes.push(note);
        incident.updated_at = note.created_at;
        return note;
      }
      if (match[3] === "events") {
        const events = linkedEvents(body(payload).event_ids);
        const existing = new Set(incident.events?.map((event) => event.id));
        incident.events = [
          ...(incident.events ?? []),
          ...events.filter((event) => !existing.has(event.id)),
        ];
        incident.event_total = incident.events.length;
        incident.updated_at = new Date().toISOString();
        return incident;
      }
      if (match[3] === "enrich") {
        incident.iocs = incident.source_ip
          ? [
              {
                id: incident.id,
                type: "ip",
                value: incident.source_ip,
                reputation: "unknown",
                confidence: null,
                source: "Demo sample",
                first_seen: incident.created_at,
                last_seen: incident.updated_at,
                metadata: {
                  notice:
                    "Reserved example address. No reputation provider was contacted.",
                },
              },
            ]
          : [];
        return incident;
      }
    }
    throw new DemoError(
      "That action is not available in the public demo. Explore the example investigations instead.",
    );
  }

  async function respond<T>(method: string, target: string, payload?: unknown) {
    return { data: structuredClone(request(method, target, payload)) as T };
  }

  return {
    get: <T>(path: string, options?: { signal?: AbortSignal }) => {
      if (options?.signal?.aborted) {
        return Promise.reject(
          new DOMException("Request cancelled", "AbortError"),
        );
      }
      return respond<T>("GET", path);
    },
    post: <T>(path: string, payload?: unknown) =>
      respond<T>("POST", path, payload),
    patch: <T>(path: string, payload?: unknown) =>
      respond<T>("PATCH", path, payload),
  };
}

export const api = createDemoApi();

export function errorMessage(error: unknown): string {
  return error instanceof DemoError
    ? error.message
    : "The example could not be opened. Reset the demo and try again.";
}

export function reconcile() {
  window.dispatchEvent(new Event("sentinelx:refresh"));
}
