import { describe, expect, it, vi } from "vitest";
import { createDemoApi } from "./api";
import { createWorkspace } from "./fixtures";
import type {
  Alert,
  Analysis,
  DashboardMetrics,
  Incident,
  Page,
  SecurityEvent,
} from "../src/types";

const now = new Date("2026-10-13T12:00:00Z");

describe("browser-only showcase data", () => {
  it("derives chart totals and source counts from the same fictional records", async () => {
    const api = createDemoApi(now);
    const workspace = createWorkspace(now);
    const { data } = await api.get<DashboardMetrics>("/dashboard");
    expect(data.total_events).toBe(workspace.events.length);
    expect(
      data.activity.reduce((total, point) => total + point.events, 0),
    ).toBe(data.total_events);
    expect(
      workspace.sources.reduce(
        (total, source) => total + source.total_events,
        0,
      ),
    ).toBe(data.total_events);
    expect(
      workspace.events.every((event) => event.metadata.simulated === true),
    ).toBe(true);
  });

  it("filters, sorts and paginates records without a server", async () => {
    const api = createDemoApi(now);
    const first = await api.get<Page<SecurityEvent>>(
      "/events?q=source_ip:203.0.113.42&limit=5",
    );
    const second = await api.get<Page<SecurityEvent>>(
      "/events?q=source_ip:203.0.113.42&limit=5&offset=5",
    );
    expect(first.data.total).toBe(14);
    expect(first.data.items).toHaveLength(5);
    expect(second.data.items).toHaveLength(5);
    expect(
      first.data.items.some((event) =>
        second.data.items.some((next) => next.id === event.id),
      ),
    ).toBe(false);
    expect(first.data.items.map((event) => event.timestamp)).toEqual(
      first.data.items
        .map((event) => event.timestamp)
        .sort()
        .reverse(),
    );
    const filtered = await api.get<Page<SecurityEvent>>(
      "/events?source_id=3&severity=medium&start_time=2026-10-13T11:00:00Z",
    );
    expect(filtered.data.total).toBe(3);
  });

  it("isolates notes, status changes and returned objects between visitors", async () => {
    const first = createDemoApi(now);
    const second = createDemoApi(now);
    await first.post("/incidents/1/notes", {
      content: "Practice note",
      kind: "note",
    });
    await first.patch("/incidents/1", { status: "resolved" });
    const { data: changed } = await first.get<Incident>("/incidents/1");
    const { data: untouched } = await second.get<Incident>("/incidents/1");
    expect(changed.notes?.at(-1)?.content).toBe("Practice note");
    expect(untouched.notes).toHaveLength(1);
    expect(untouched.status).toBe("open");
    changed.title = "Mutating a response does not mutate the dataset";
    expect((await first.get<Incident>("/incidents/1")).data.title).not.toBe(
      changed.title,
    );
    expect(
      (await first.get<Page<Alert>>("/alerts?status=open")).data.total,
    ).toBe(1);
    expect(
      (await second.get<Page<Alert>>("/alerts?status=open")).data.total,
    ).toBe(3);
  });

  it("links sample evidence once and creates a bounded practice investigation", async () => {
    const api = createDemoApi(now);
    const { data: records } = await api.get<Page<SecurityEvent>>(
      "/events?source_id=3",
    );
    const ids = records.items.map((event) => event.id);
    const { data: created } = await api.post<Incident>("/incidents", {
      title: "Practice service review",
      description: "Fictional notes",
      severity: "medium",
      event_ids: ids,
    });
    await api.post(`/incidents/${created.id}/events`, {
      event_ids: [...ids, ...ids],
    });
    expect(
      (await api.get<Incident>(`/incidents/${created.id}`)).data.event_total,
    ).toBe(3);
    await expect(
      api.post("/incidents/1/events", { event_ids: [99999] }),
    ).rejects.toThrow("does not exist");
  });

  it("labels explanations as samples and cites only linked example evidence", async () => {
    const api = createDemoApi(now);
    const { data: analysis } = await api.post<Analysis>(
      "/ai/analyze-incident",
      { incident_id: 1 },
    );
    const { data: incident } = await api.get<Incident>("/incidents/1");
    expect(analysis.mode).toBe("offline");
    expect(analysis.model).toBeNull();
    expect(analysis.notice).toContain(
      "No model or external service was called",
    );
    expect(
      analysis.evidence.every((item) =>
        incident.events?.some((event) => item.startsWith(event.reference)),
      ),
    ).toBe(true);
  });

  it("rejects invalid edits before changing any practice state", async () => {
    const api = createDemoApi(now);
    await expect(
      api.patch("/incidents/1", { status: "resolved", severity: "invalid" }),
    ).rejects.toThrow("Choose an investigation priority");
    expect((await api.get<Incident>("/incidents/1")).data.status).toBe("open");
    expect((await api.get<Page<Alert>>("/alerts?status=open")).data.total).toBe(
      3,
    );
  });

  it("rejects monitoring, account and external endpoints without making a network request", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const xhr = vi.spyOn(XMLHttpRequest.prototype, "open");
    try {
      const api = createDemoApi(now);
      for (const target of [
        "/auth/login",
        "/auth/refresh",
        "/sources/1/events",
        "/events",
        "/events/raw",
        "https://example.com/events",
        "//example.com/events",
      ]) {
        await expect(api.post(target, {})).rejects.toThrow();
      }
      await expect(
        api.patch("/alerts/1", { status: "invalid" }),
      ).rejects.toThrow("Choose an alert status");
      expect(fetch).not.toHaveBeenCalled();
      expect(xhr).not.toHaveBeenCalled();
    } finally {
      fetch.mockRestore();
      xhr.mockRestore();
    }
  });
});
