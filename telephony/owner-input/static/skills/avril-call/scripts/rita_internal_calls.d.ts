// AI-NOTICE:Schema-Version=0.1
// AI-NOTICE:License=AGPL-3.0-or-later
// AI-NOTICE:Project=rita
// AI-NOTICE:Network-Service=AGPL-3.0-or-later section 13 applies

export interface OriginateRequest {
  request_id: string;
  target: string;
  purpose: string;
  opening_kind?: string | null;
  opening_text?: string | null;
}

export interface StatusRequest {
  request_id: string;
}
export interface ClientOptions {
  env?: Record<string, string | undefined>;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  /** Trusted-process/test dependency only, never part of model-authored JSON. */
  readManagedEnv?: () => Record<string, string | undefined>;
}

export interface HealthReceipt {
  ok: true;
  control_ready: true;
  ami_actions_advertised: true;
  resolver_readback: true;
  durable_store_writable: true;
  ami_event_read_permissions?: "unverified";
  ami_event_filters?: "unverified";
  ami_event_read_required?: ["call", "dialplan"];
  lifecycle_observation_ready?: boolean | null;
  ext6_auth_observation_ready?: boolean | null;
  observation_readiness_error?: "ami_event_permissions_unverified" | null;
  delivery: "unproven";
  human_acknowledgement: "unproven";
}

/** Narrow PBX receipt: optional observation fields are absent on legacy servers, never inferred. */
export interface CallReceipt {
  ok: boolean;
  request_id: string;
  call_id: string;
  other_channel_id: string;
  target_extension: string;
  control_status: "accepted_indeterminate" | "rejected" | "unknown" | "reserved_unknown";
  pbx_state: "unknown" | "ringing" | "answered" | "active" | "ended";
  terminal: boolean;
  answer_observed: boolean;
  ext6_gate_observed: boolean;
  ext6_auth_pass_observed?: boolean;
  lifecycle_subscription_active?: boolean;
  lifecycle_observation_available?: boolean;
  lifecycle_observation_error?: "ami_lifecycle_gap" | "ami_call_events_unverified" | null;
  ext6_auth_observation_available?: boolean;
  ext6_auth_observation_error?: "ami_lifecycle_gap" | "ami_dialplan_events_unverified" | null;
  observed_at_unix_ms: number | null;
  readback_available: boolean;
  delivery: "unproven";
  human_acknowledgement: "unproven";
  replay: boolean;
  /** Static server code; arbitrary text becomes router_error_unrecognized. Channel lists stay private. */
  error?: string | null;
}

export type ErrorCode =
  | "invalid_request"
  | "invalid_identity"
  | "invalid_target"
  | "invalid_purpose"
  | "invalid_opening_kind"
  | "invalid_opening_text"
  | "configuration_invalid"
  | "managed_config_unavailable"
  | "request_timeout"
  | "redirect_rejected"
  | "router_http_error"
  | "router_not_ok"
  | "response_invalid"
  | "transport_unavailable"
  | "client_error";
export interface Result<T extends HealthReceipt | CallReceipt = HealthReceipt | CallReceipt> {
  ok: boolean;
  http_status: number | null;
  error: ErrorCode | null;
  receipt: T | null;
}
export interface InternalCallsClient {
  health(): Promise<Result<HealthReceipt>>;
  originate(input: OriginateRequest): Promise<Result<CallReceipt>>;
  status(input: StatusRequest): Promise<Result<CallReceipt>>;
}
export function createInternalCallsClient(options?: ClientOptions): InternalCallsClient;
export function runJsonRequest(raw: string, options?: ClientOptions): Promise<Result>;
