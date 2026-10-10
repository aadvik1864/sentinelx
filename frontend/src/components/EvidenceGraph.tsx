import { Background, Controls, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Incident, SecurityEvent } from "../types";
import { humanize } from "./ui";

export default function EvidenceGraph({ incident }: { incident: Incident }) {
  const groups = new Map<string, SecurityEvent[]>();
  for (const event of incident.events ?? [])
    groups.set(event.event_type, [
      ...(groups.get(event.event_type) ?? []),
      event,
    ]);
  const keys = [...groups.keys()].slice(0, 8);
  const nodes = [
    {
      id: "source",
      position: { x: 0, y: 90 },
      data: { label: `Source\n${incident.source_ip ?? "Unknown"}` },
      className: "graph-source",
    },
    ...keys.map((key, index) => ({
      id: key,
      position: { x: (index + 1) * 230, y: 90 },
      data: { label: `${humanize(key)}\n${groups.get(key)?.length} events` },
      className: "graph-event",
    })),
    {
      id: "incident",
      position: { x: (keys.length + 1) * 230, y: 90 },
      data: {
        label: `${incident.reference}\n${humanize(incident.severity)} severity`,
      },
      className: "graph-incident",
    },
  ];
  const ids = nodes.map((node) => node.id);
  const edges = ids.slice(1).map((id, index) => ({
    id: `${ids[index]}-${id}`,
    source: ids[index],
    target: id,
    style: { stroke: "var(--accent-border)" },
  }));
  return (
    <div className="evidence-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        minZoom={0.25}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        colorMode="dark"
      >
        <Background color="var(--line)" gap={24} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
