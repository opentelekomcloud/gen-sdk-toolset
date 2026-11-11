import type { DocumentListItem, Layout, ServiceDetail, Snapshot } from "../shared/api/types";

/**
 * Answers of the panel API as the backend serves them, complete and typed: a
 * test names only what it is about, and a field the schema adds is a compile
 * error here once, not an `undefined` in every copy of a fixture.
 */

/** A persisted scan snapshot. */
export function snapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    id: 3,
    branch: "main",
    commit_hash: "a".repeat(40),
    completeness: 1,
    created_at: "2026-08-01T10:00:00Z",
    docs_ok: 100,
    document_schema_version: "1",
    documents_total: 2,
    endpoints_total: 2,
    failed_count: 0,
    issues_total: 0,
    last_scanned_at: "2026-08-01T10:00:00Z",
    non_endpoint_documents: 0,
    ok_count: 2,
    parser_ok: 100,
    partial_count: 0,
    scanner_version: "0.1.0",
    source_job_id: 1,
    unsupported_count: 0,
    ...overrides,
  };
}

/** A service scanned once, its one snapshot active and latest, nothing failed. */
export function serviceDetail(overrides: Partial<ServiceDetail> = {}): ServiceDetail {
  const active = snapshot();
  return {
    name: "opentelekomcloud-docs/ecs",
    label: "ecs",
    scan_status: "scanned",
    documents: 2,
    read_in_full: 2,
    docs_ok: 100,
    scanner_version: "0.1.0",
    scanned_at: "2026-08-01T10:00:00Z",
    docs_changed: false,
    rescan_reason: null,
    overall_breakdown: { ok: 2 },
    unread_breakdown: {},
    unread_documents: 0,
    rows_unrecognized: 0,
    section_rollup: {},
    error: null,
    error_at: null,
    active_snapshot: active,
    latest_snapshot: active,
    head_commit: active.commit_hash,
    interruption: null,
    top_issues: [],
    non_endpoint_documents: 0,
    ...overrides,
  };
}

/** An endpoint document that was read in full. */
export function endpoint(overrides: Partial<DocumentListItem> = {}): DocumentListItem {
  return {
    id: 1,
    path: "api-ref/source/servers/list_servers.rst",
    title: "Querying servers",
    method: "GET",
    uri: "/v1/{project_id}/cloudservers",
    overall_status: "ok",
    issues: [],
    ...overrides,
  };
}

/** A layout after the grouping: one version with one unconfirmed resource, nothing left over. */
export function layout(overrides: Partial<Layout> = {}): Layout {
  return {
    has_layout: true,
    versions: [
      {
        api_version: "v1",
        resources: [{ id: 1, name: "cloudservers", confirmed_by: null, confirmed_at: null, endpoints: [endpoint()] }],
        unassigned: [],
      },
    ],
    no_version: [],
    ...overrides,
  };
}
