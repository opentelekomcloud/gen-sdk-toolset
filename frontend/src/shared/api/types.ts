/**
 * The API contract, named the way the UI talks about it. Every type is an alias
 * into the generated `schema.gen.ts` - nothing is declared here, so nothing can
 * drift; the names only drop the backend's HTTP suffix. Shapes the schema does
 * not carry live in `features/scan/types.ts`.
 */
import type { components } from "./schema.gen";

type Schemas = components["schemas"];

export type ScanStatus = Schemas["ScanStatus"];
export type RescanReason = Schemas["RescanReason"];
export type JobKind = Schemas["JobKind"];
export type JobStatus = Schemas["JobStatus"];

export type IssueCount = Schemas["IssueCount"];
export type AttentionRule = Schemas["AttentionRule"];
export type Summary = Schemas["SummaryResponse"];

export type ServiceListItem = Schemas["ServiceListItem"];
export type ServicesResponse = Schemas["ServicesResponse"];
export type ServiceDetail = Schemas["ServiceDetailResponse"];
export type ExcludedService = Schemas["ExcludedServiceResponse"];
export type Ineligible = Schemas["IneligibleRepositoryResponse"];

export type Snapshot = Schemas["SnapshotResponse"];
export type SnapshotsResponse = Schemas["SnapshotsResponse"];

export type DocumentListItem = Schemas["DocumentListItem"];
export type DocumentsResponse = Schemas["DocumentsResponse"];
export type DocumentDetail = Schemas["DocumentDetailResponse"];
export type SectionDetail = Schemas["SectionDetail"];
export type Parameter = Schemas["ParameterResponse"];

export type Job = Schemas["JobResponse"];
export type ScanRequest = Schemas["ScanRequest"];
export type ScanResponse = Schemas["StartScanResponse"];
export type ExcludeRequest = Schemas["ExcludeRequest"];
export type ActivateSnapshotRequest = Schemas["ActivateSnapshotRequest"];
