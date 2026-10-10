import type { Incident, SecurityEvent } from "../types";
import { time } from "../components/ui";
import { eventLabel } from "./labels";

export interface TimelineEntry {
  key: string;
  timestamp: string;
  title: string;
  body: string;
  reference: string;
  label: string;
  severity: string;
  type: string;
  events?: SecurityEvent[];
  groupKey?: string;
}

export function buildTimeline(incident: Incident): TimelineEntry[] {
  const rows: TimelineEntry[] = [
    ...(incident.events ?? []).map((event) => ({
      key: `event-${event.id}`,
      timestamp: event.timestamp,
      title: eventLabel(event.event_type),
      body: event.message,
      reference: event.reference,
      label: event.hostname,
      severity: event.severity,
      type: "event",
      events: [event],
      groupKey: ["authentication_failure", "invalid_user"].includes(
        event.event_type,
      )
        ? [
            event.event_type,
            event.hostname,
            event.source_ip,
            event.username,
            event.severity,
          ].join(":")
        : undefined,
    })),
    ...(incident.notes ?? []).map((note) => ({
      key: `note-${note.id}`,
      timestamp: note.created_at,
      title: note.kind === "evidence" ? "Evidence added" : "Investigation note",
      body: note.content,
      reference: note.author,
      label: "Added by an investigator",
      severity: "low",
      type: "note",
    })),
    {
      key: "created",
      timestamp: incident.created_at,
      title: "Investigation opened",
      body: incident.description,
      reference: incident.reference,
      label: "Case management",
      severity: incident.severity,
      type: "system",
    },
    ...(incident.resolved_at
      ? [
          {
            key: "resolved",
            timestamp: incident.resolved_at,
             title: "Investigation closed",
             body: "Related alerts were closed, except those already marked Not an issue. No systems were changed.",
            reference: incident.reference,
            label: "Case management",
            severity: "low",
            type: "system",
          },
        ]
      : []),
  ].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
  const grouped: TimelineEntry[] = [];
  for (const entry of rows) {
    const previous = grouped.at(-1);
    if (
      entry.groupKey &&
      previous?.groupKey === entry.groupKey &&
      previous.events &&
      entry.events
    ) {
      previous.events.push(...entry.events);
      const first = previous.events[0],
        last = previous.events.at(-1)!;
      previous.title = `${previous.events.length} ${first.event_type === "invalid_user" ? "attempts with unknown accounts" : "unsuccessful sign-in attempts"}`;
      previous.body = `${first.username ?? "Unknown account"} from ${first.source_ip ?? "an unknown source"} between ${time(first.timestamp)} and ${time(last.timestamp)}.`;
      previous.reference = `${first.reference}–${last.reference}`;
    } else grouped.push(entry);
  }
  return grouped;
}
