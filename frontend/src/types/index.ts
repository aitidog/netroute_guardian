/** Shared TypeScript interfaces mirroring backend Pydantic schemas. */

export type RiskLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO' | 'PASS';

export interface Device {
  id: number;
  hostname: string;
  ip_address: string;
  device_type: 'edgeconnect' | 'cisco_nexus' | 'cisco_router';
  connection_mode: 'mock' | 'live';
  location: string;
  description: string;
  config_json: Record<string, unknown>;
  created_at: string;
}

export interface ImportantRoute {
  id: number;
  prefix: string;
  description: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface RoutePath {
  next_hop: string;
  interface: string;
  protocol: string;
  admin_distance: number | null;
  metric: number | null;
  peer_priority: number | null;
  raw_metric: string;
}

export interface RouteDiffEntry {
  vrf: string;
  prefix: string;
  prefix_len: number;
  change_type: 'removed' | 'added' | 'changed';
  before_paths: RoutePath[];
  after_paths: RoutePath[];
  removed_paths: RoutePath[];
  added_paths: RoutePath[];
  unchanged_path_count: number;
  is_important: boolean;
  matched_rules: string[];
  importance_reasons: string[];
  severity: RiskLevel;
  affected_ip_count: number;
  fallback_status: string | null;
  fallback_parent_prefix: string | null;
  fallback_parent_egress: string | null;
  active_path_changed: boolean | null;
  backup_only_changed: boolean | null;
  best_before_summary: string | null;
  best_after_summary: string | null;
  next_hop_changes: string[];
  findings: string[];
  explanation: string;
}

export interface PipelineStageTrace {
  name: string;
  description: string;
  duration_ms: number;
  details: Record<string, unknown>;
}

export interface ComparisonSummaryStats {
  device_label: string;
  before_raw_entries: number;
  after_raw_entries: number;
  before_unique_prefixes: number;
  after_unique_prefixes: number;
  removed_count: number;
  added_count: number;
  changed_count: number;
  unchanged_count: number;
  total_differences: number;
  important_count: number;
  normal_count: number;
  large_prefix_alert_count: number;
  prespecified_alert_count: number;
  large_prefix_threshold: number;
  affected_ips_excluding_default: number;
  risk_level: RiskLevel;
}

export interface ComparisonReportPayload {
  device_label: string;
  risk_level: RiskLevel;
  executive_summary: string;
  summary_stats: ComparisonSummaryStats;
  important_entries: RouteDiffEntry[];
  normal_entries: RouteDiffEntry[];
  all_entries: RouteDiffEntry[];
  pipeline_stages?: PipelineStageTrace[];
}

export interface ComparisonReport {
  id: number;
  change_id: number | null;
  device_id: number | null;
  device_label: string;
  before_snapshot_id: number;
  after_snapshot_id: number;
  risk_level: RiskLevel;
  summary_stats: ComparisonSummaryStats;
  report_payload: ComparisonReportPayload;
  email_recipient: string | null;
  email_status: string;
  email_error: string | null;
  email_sent_at: string | null;
  created_at: string;
}

export interface SnapshotSummary {
  id: number;
  device_id: number | null;
  change_id: number | null;
  device_label: string;
  phase: string;
  source_type: string;
  raw_entry_count: number;
  unique_prefix_count: number;
  captured_at: string;
}

export interface ChangeRequest {
  id: number;
  chg_number: string;
  title: string;
  description: string;
  scheduled_start: string;
  scheduled_end: string | null;
  capture_scheduled_at: string;
  engineer_name: string;
  engineer_email: string;
  status: string;
  sync_source: string;
  retry_count: number;
  last_error: string | null;
  synced_at: string;
  updated_at: string;
  devices: Device[];
  pre_snapshot_count: number;
  post_snapshot_count: number;
  report_count: number;
  highest_risk_level: RiskLevel | null;
}

export interface ChangeRequestDetail extends ChangeRequest {
  snapshots: SnapshotSummary[];
  reports: ComparisonReport[];
}

export interface CollapsedRouteItem {
  vrf: string;
  prefix: string;
  prefix_len: number;
  is_summary: boolean;
  covered_count: number;
  covered_routes: string[];
}

export interface SupernetSuggestion {
  vrf: string;
  suggested_supernet: string;
  member_count: number;
  member_prefixes: string[];
}

export interface RouteSummaryResponse {
  source_label: string;
  device_type: string | null;
  device_ip: string | null;
  total_raw_entries: number;
  total_unique_prefixes: number;
  ignored_default_routes: number;
  output_route_count: number;
  summary_route_count: number;
  remaining_route_count: number;
  covered_route_count: number;
  compression_ratio_pct: number;
  vrf_groups: Array<{
    vrf: string;
    unique_prefixes: number;
    output_count: number;
    summary_count: number;
    remaining_count: number;
  }>;
  summary_routes: CollapsedRouteItem[];
  remaining_routes: CollapsedRouteItem[];
  all_output_routes: CollapsedRouteItem[];
  supernet_suggestions: SupernetSuggestion[] | null;
  pipeline_stages: PipelineStageTrace[];
}

export interface MockServiceNowChange {
  id: number;
  chg_number: string;
  title: string;
  description: string;
  scheduled_start: string;
  scheduled_end: string | null;
  engineer_name: string;
  engineer_email: string;
  state: 'scheduled' | 'implement' | 'closed' | 'cancelled';
  ci_device_ids: number[];
  updated_at: string;
}

export interface AppSettings {
  servicenow_mode: string;
  servicenow_window_hours: number;
  pre_capture_lead_minutes: number;
  large_prefix_threshold: number;
  max_concurrent_device_collections: number;
  pipeline_executor_mode: string;
  pipeline_max_workers: number;
  mailpit_web_url: string;
}

export interface SchedulerStatus {
  running: boolean;
  servicenow_mode: string;
  last_sync_at: string | null;
  last_dispatch_at: string | null;
  synced_changes_count: number;
  pending_pre_captures: number;
  next_due_capture_at: string | null;
  jobs: Array<{ id: string; name: string; next_run_time: string | null }>;
}
