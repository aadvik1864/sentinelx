import type { Severity } from "../types";

export const priorityLabels: Record<Severity, string> = {
  critical: "Urgent",
  high: "Important",
  medium: "Moderate",
  low: "Low priority",
};

export const roleLabels: Record<string, string> = {
  ADMIN: "Administrator",
  ANALYST: "Investigator",
  VIEWER: "Read-only",
};

const statuses: Record<string, string> = {
  open: "Needs review",
  acknowledged: "Seen",
  investigating: "Being reviewed",
  resolved: "Closed",
  false_positive: "Not an issue",
  contained: "Containment recorded",
};

const events: Record<string, string> = {
  authentication_failure: "Unsuccessful sign-in",
  authentication_success: "Successful sign-in",
  invalid_user: "Unknown account used",
  privilege_escalation: "Administrator activity",
  http_request: "Website request",
  application_request: "App activity",
  application_error: "App error",
  application_event: "App activity",
  system_event: "Computer activity",
  connection_attempt: "Connection attempt",
  network_connection: "Network connection",
  password_changed: "Password changed",
  session_logout: "User signed out",
  refresh_replay: "Repeated sign-in session rejected",
};

export function readable(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase());
}

export function statusLabel(value: string) {
  return statuses[value] ?? roleLabels[value] ?? readable(value);
}

export function eventLabel(value: string) {
  return events[value] ?? readable(value);
}

export function formatLabel(value: string) {
  const formats: Record<string, string> = {
    linux: "Linux computer",
    nginx: "Website · Nginx",
    apache: "Website · Apache",
    application: "Web app",
    network: "Network activity",
  };
  return formats[value] ?? readable(value);
}
