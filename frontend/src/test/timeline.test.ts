import { describe, expect, it } from "vitest";
import { buildTimeline } from "../utils/timeline";
import type { Incident, SecurityEvent } from "../types";

function event(
  id: number,
  changes: Partial<SecurityEvent> = {},
): SecurityEvent {
  return {
    id,
    reference: `EVT-${String(id).padStart(5, "0")}`,
    timestamp: `2026-10-08T10:30:${String(id).padStart(2, "0")}Z`,
    source: "linux",
    event_type: "authentication_failure",
    severity: "medium",
    source_ip: "203.0.113.42",
    destination_ip: null,
    hostname: "lab",
    username: "admin",
    message: "Failed password",
    metadata: {},
    ...changes,
  };
}
function incident(events: SecurityEvent[]): Incident {
  return {
    id: 1,
    reference: "INC-00001",
    title: "Investigation",
    description: "",
    severity: "high",
    status: "open",
    assigned_to: null,
    source_ip: "203.0.113.42",
    hostname: "lab",
    created_at: "2026-10-08T10:31:00Z",
    updated_at: "2026-10-08T10:31:00Z",
    resolved_at: null,
    mitre_techniques: [],
    events,
    notes: [],
  };
}
describe("chronological evidence grouping", () => {
  it("groups consecutive failures without discarding source events", () => {
    const result = buildTimeline(
      incident([
        event(1),
        event(2),
        event(3, { event_type: "authentication_success" }),
      ]),
    );
    expect(result[0].title).toBe("2 unsuccessful sign-in attempts");
    expect(result[0].events?.map((row) => row.id)).toEqual([1, 2]);
    expect(result[1].title).toBe("Successful sign-in");
  });
  it("does not conflate different users or targets", () => {
    const result = buildTimeline(
      incident([
        event(1),
        event(2, { username: "other" }),
        event(3, { hostname: "other-host" }),
      ]),
    );
    expect(result).toHaveLength(4);
  });
  it("does not hide a note interleaved with source evidence", () => {
    const value = incident([event(1), event(3)]);
    value.notes = [
      {
        id: 1,
        content: "Reviewed",
        kind: "note",
        author: "Analyst",
        created_at: "2026-10-08T10:30:02Z",
      },
    ];
    const result = buildTimeline(value);
    expect(result.map((row) => row.type)).toEqual([
      "event",
      "note",
      "event",
      "system",
    ]);
  });
});
