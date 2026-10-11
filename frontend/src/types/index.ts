export type Severity = "critical" | "high" | "medium" | "low";
export type Role = "ADMIN" | "ANALYST" | "VIEWER";
export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  must_change_password?: boolean;
  mfa_enabled?: boolean;
  mfa_required?: boolean;
  disabled?: boolean;
  created_at: string;
}
export interface Session {
  access_token: string;
  user: User;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface SecurityEvent {
  id: number;
  reference: string;
  timestamp: string;
  source: string;
  event_type: string;
  severity: Severity;
  source_ip: string | null;
  destination_ip: string | null;
  hostname: string;
  username: string | null;
  message: string;
  metadata: Record<string, unknown>;
}
export interface Alert {
  id: number;
  reference: string;
  title: string;
  description: string;
  severity: Severity;
  status: string;
  source_ip: string | null;
  hostname: string;
  event_count: number;
  created_at: string;
  detected_at: string;
  incident_id: number | null;
  mitre_techniques: string[];
  event?: SecurityEvent;
  rule?: Rule;
}
export interface Note {
  id: number;
  content: string;
  kind: string;
  author: string;
  created_at: string;
}
export interface IOC {
  id: number;
  type: string;
  value: string;
  reputation: string;
  confidence: number | null;
  source: string;
  first_seen: string;
  last_seen: string;
  metadata: Record<string, unknown>;
}
export interface Incident {
  id: number;
  reference: string;
  title: string;
  description: string;
  severity: Severity;
  status: string;
  assigned_to: number | null;
  assigned_name?: string;
  source_ip: string | null;
  hostname: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  mitre_techniques: string[];
  events?: SecurityEvent[];
  alerts?: Alert[];
  notes?: Note[];
  iocs?: IOC[];
  event_total?: number;
  evidence_truncated?: boolean;
}
export interface Rule {
  id: number;
  reference: string;
  name: string;
  description: string;
  kind: string;
  event_type: string;
  threshold: number;
  window_seconds: number;
  severity: Severity;
  enabled: boolean;
  mitre_techniques: string[];
  config: Record<string, unknown>;
}
export interface Asset {
  id: number;
  hostname: string;
  ip_address: string;
  type: string;
  environment: string;
  owner: string;
  status: string;
}
export interface Analysis {
  summary: string;
  likely_attack: string;
  evidence: string[];
  affected_assets: string[];
  mitre_techniques: string[];
  confidence: string;
  recommended_investigation: string[];
  recommended_containment: string[];
  false_positive_indicators: string[];
  mode: "offline" | "llm";
  provider?: "offline" | "ollama" | "openai";
  model: string | null;
  notice: string;
}
export interface SystemInfo {
  version: string;
  environment: string;
  demo_mode: boolean;
  live_monitoring?: boolean;
  ai_provider: string;
  ai_model?: string | null;
  threat_intel_provider: string;
}

export interface LogSource {
  id: number;
  name: string;
  kind: "linux" | "nginx" | "apache" | "application";
  hostname: string;
  log_path: string;
  enabled: boolean;
  status:
    "not_connected" | "receiving" | "waiting" | "offline" | "error" | "paused";
  last_heartbeat_at: string | null;
  last_event_at: string | null;
  last_event_timestamp: string | null;
  last_error: string;
  total_events: number;
}
export interface DashboardMetrics {
  total_events: number;
  events_per_second: number;
  active_alerts: number;
  critical_alerts: number;
  open_incidents: number;
  resolved_incidents: number;
  monitored_assets: number;
  unique_source_ips: number;
  severity_counts: Record<Severity, number>;
  activity: { timestamp: string; events: number }[];
  top_ips: { ip: string; count: number }[];
  event_types: { type: string; count: number }[];
}
