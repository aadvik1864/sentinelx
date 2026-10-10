import {
  Activity, Bell, Boxes, FileText, LayoutDashboard, Radio,
  Shield, SlidersHorizontal, Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavigationItem {
  path: string;
  label: string;
  icon: LucideIcon;
  viewer?: boolean;
  advanced?: boolean;
}

export const navigation: NavigationItem[] = [
  { path: "/dashboard", label: "Overview", icon: LayoutDashboard, viewer: true },
  { path: "/alerts", label: "Alerts", icon: Bell, viewer: true },
  { path: "/incidents", label: "Investigations", icon: FileText, viewer: true },
  { path: "/events", label: "Activity", icon: Activity },
  { path: "/sources", label: "Connected systems", icon: Radio },
  { path: "/ai-assistant", label: "Assistant", icon: Sparkles },
  { path: "/assets", label: "Device list", icon: Boxes, advanced: true },
  { path: "/rules", label: "Alert rules", icon: SlidersHorizontal, advanced: true },
  { path: "/threat-intelligence", label: "Address checks", icon: Shield, advanced: true },
];
