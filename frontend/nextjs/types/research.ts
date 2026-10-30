/** Version one wire contracts; the server validates values at the boundary. */
export type ReportType =
  | 'research_report' | 'resource_report' | 'outline_report' | 'custom_report'
  | 'detailed_report' | 'subtopic_report' | 'deep' | 'multi_agents';

export type ReportSource =
  | 'web' | 'local' | 'azure' | 'langchain_documents'
  | 'langchain_vectorstore' | 'static' | 'hybrid';

export type ToneName =
  | 'Objective' | 'Formal' | 'Analytical' | 'Persuasive' | 'Informative'
  | 'Explanatory' | 'Descriptive' | 'Critical' | 'Comparative' | 'Speculative'
  | 'Reflective' | 'Narrative' | 'Humorous' | 'Optimistic' | 'Pessimistic'
  | 'Simple' | 'Casual';

export type TaskStatus =
  | 'queued' | 'running' | 'waiting_for_review' | 'succeeded' | 'failed'
  | 'cancel_requested' | 'cancelled' | 'interrupted';

export type ReviewStatus =
  | 'not_requested' | 'pending' | 'approved' | 'needs_revision'
  | 'needs_review' | 'rejected';

export type ExportStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface Budget {
  max_tool_calls?: number;
  max_seconds?: number;
  max_tokens?: number | null;
  max_cost_usd?: number | null;
}

export interface SourcePolicy {
  allowed_kinds?: ReportSource[];
  network_allowed?: boolean;
}

export interface ResearchTaskRequest {
  task: string;
  report_type?: ReportType;
  report_source?: ReportSource;
  tone?: ToneName;
  source_urls?: string[];
  document_urls?: string[];
  query_domains?: string[];
  source_policy?: SourcePolicy;
  budget?: Budget;
  mcp_enabled?: boolean;
  mcp_config_refs?: string[];
  include_human_feedback?: boolean;
  max_search_results?: number | null;
  mcp_strategy?: 'fast' | 'deep';
}

export interface TaskEvent {
  version: 1;
  research_id: string;
  attempt_id?: string | null;
  seq: number;
  type: string;
  /** ISO 8601 aware timestamp, serialized in UTC. */
  created_at: string;
  payload: Record<string, JsonValue>;
}

export interface SubscribeCommand {
  version: 1;
  type: 'subscribe';
  research_id: string;
  after_seq: number;
}

export interface ResearchResult {
  report_markdown: string;
  sources: Record<string, JsonValue>[];
  context_refs: string[];
  cost_summary: Record<string, JsonValue>;
  review_status: ReviewStatus;
  warnings: string[];
  artifact_refs: string[];
}
