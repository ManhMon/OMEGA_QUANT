import { API_BASE, apiRequest } from './client';

export type JobStatus = 'CREATED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'DEAD_LETTERED';

export interface ProvenanceEnvelope {
  source: string;
  dataset_id: string;
  dataset_version: string;
  as_of: string;
  computed_at: string;
  requested_pit_cutoff: string | null;
  effective_cutoff: string;
  input_timezone: string;
  normalized_timezone: 'UTC';
  cutoff_resolution: 'REQUESTED' | 'AS_OF_DEFAULT';
  max_included_available_at: string | null;
  excluded_future_rows: number;
  content_hash: string;
  artifact_uri: string | null;
  is_synthetic: false;
}

export interface ErrorEnvelope {
  error_code: string;
  message: string;
  request_id: string;
  retryable: boolean;
  details: Record<string, unknown> | null;
  timestamp: string;
}

export interface JobSubmitRequest {
  task_type: string;
  payload: Record<string, unknown>;
  pit_cutoff: string;
  max_attempts?: number;
}

export interface JobAcceptedResponse {
  job_id: string;
  status: 'QUEUED';
  job_url: string;
  stream_url: string;
  request_id: string;
  submitted_at: string;
  request_sha256: string;
}

export interface JobStatusResponse {
  job_id: string;
  task_type: string;
  status: JobStatus;
  progress_pct: number;
  stage: string;
  message: string;
  submitted_at: string;
  updated_at: string;
  pit_cutoff: string;
  request_sha256: string;
  attempt_count: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  error: ErrorEnvelope | null;
}

export const advancedQuantApi = {
  submitJob: (request: JobSubmitRequest, idempotencyKey: string, signal?: AbortSignal) =>
    apiRequest<JobAcceptedResponse>('/api/v1/jobs', {
      method: 'POST',
      body: JSON.stringify(request),
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      signal,
    }),
  getJob: (jobId: string, signal?: AbortSignal) =>
    apiRequest<JobStatusResponse>(`/api/v1/jobs/${encodeURIComponent(jobId)}`, { signal }),
  cancelJob: (jobId: string, signal?: AbortSignal) =>
    apiRequest<{ job_id: string; status: JobStatus; cancellation_requested_at: string }>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST', signal },
    ),
  eventUrl: (streamUrl: string) => new URL(streamUrl, API_BASE).toString(),
};
