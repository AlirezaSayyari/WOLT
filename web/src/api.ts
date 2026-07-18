export interface SetupStatus {
  database_ready: boolean
  schema_ready: boolean
  setup_required: boolean
  bootstrap_configured: boolean
  master_key_configured: boolean
}

export interface HealthStatus {
  status: 'ready' | 'not_ready'
  database: 'ready' | 'unavailable' | 'migration_required'
}

export interface User {
  id: string
  username: string
  email: string
  role: string
}

export interface AuthResponse {
  user: User
  recovery_code?: string | null
}

export interface Device {
  id: string
  name: string
  driver_type: string
  configuration: { host: string; port: number; host_key: string; connect_timeout: number; command_timeout: number }
  enabled: boolean
  health_status: string
  last_checked_at: string | null
  listener_count: number
  credential_configured: boolean
  created_at: string
}

export interface Listener {
  id: string
  device_id: string
  device_name: string
  driver_type: string
  name: string
  description: string | null
  udp_port: number
  allowed_source_ip: string
  driver_parameters: { interface: string; gateway_ip: string }
  enabled: boolean
  status: string
  last_error: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface EngineState {
  desired_state: string
  observed_state: string
  heartbeat_at: string | null
  last_transition_at: string | null
  last_error: string | null
  active_listeners: number
  enabled_listeners: number
}

export interface WakeEvent {
  id: string
  mapping_id: string
  mapping_name: string
  device_id: string
  device_name: string
  event_type: string
  mac_address: string
  source_ip: string
  source_port: number
  result_code: string
  duration_ms: number | null
  correlation_id: string
  occurred_at: string
}

export interface AuditEvent {
  id: string
  actor: string
  action: string
  object_type: string
  object_id: string | null
  safe_changes: Record<string, unknown>
  client_ip: string
  occurred_at: string
}

export interface Page<T> { items: T[]; page: number; page_size: number; total: number; pages: number }
export interface DashboardData {
  period_hours: number
  total_requests: number
  success: number
  failed: number
  rate_limited: number
  success_rate: number | null
  healthy_devices: number
  total_devices: number
  series: Array<{ start: string; success: number; failed: number; rate_limited: number; total: number }>
  recent_events: WakeEvent[]
}
export interface ApplicationSettings {
  udp_port_start: number; udp_port_end: number; rate_limit_seconds: number
  wake_event_retention_days: number; audit_event_retention_days: number
  locale: string; timezone: string; updated_at: string
}

function queryString(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)) })
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail)
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => ({})) as { detail?: string } & T
  if (!response.ok) throw new ApiError(response.status, payload.detail ?? 'request_failed')
  return payload
}

export const api = {
  setupStatus: () => request<SetupStatus>('/api/v1/setup/status'),
  health: () => request<HealthStatus>('/api/v1/health/ready'),
  me: () => request<User>('/api/v1/auth/me'),
  createOwner: (body: { bootstrap_token: string; username: string; email: string; password: string }) =>
    request<AuthResponse>('/api/v1/setup/owner', { method: 'POST', body: JSON.stringify(body) }),
  login: (body: { identifier: string; password: string }) =>
    request<AuthResponse>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),
  recover: (body: { email: string; recovery_code: string; new_password: string }) =>
    request<AuthResponse>('/api/v1/auth/recover', { method: 'POST', body: JSON.stringify(body) }),
  devices: () => request<Device[]>('/api/v1/devices'),
  createDevice: (body: Record<string, unknown>) => request<Device>('/api/v1/devices', { method: 'POST', body: JSON.stringify(body) }),
  updateDevice: (id: string, body: Record<string, unknown>) => request<Device>(`/api/v1/devices/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteDevice: (id: string) => request<void>(`/api/v1/devices/${id}`, { method: 'DELETE' }),
  testDevice: (id: string) => request<{ status: string; latency_ms: number | null; reason: string | null }>(`/api/v1/devices/${id}/test`, { method: 'POST' }),
  listeners: () => request<Listener[]>('/api/v1/listeners'),
  createListener: (body: Record<string, unknown>) => request<Listener>('/api/v1/listeners', { method: 'POST', body: JSON.stringify(body) }),
  updateListener: (id: string, body: Record<string, unknown>) => request<Listener>(`/api/v1/listeners/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteListener: (id: string) => request<void>(`/api/v1/listeners/${id}`, { method: 'DELETE' }),
  engine: () => request<EngineState>('/api/v1/engine'),
  resumeEngine: () => request<EngineState>('/api/v1/engine/resume', { method: 'POST' }),
  pauseEngine: () => request<EngineState>('/api/v1/engine/pause', { method: 'POST' }),
  dashboard: (hours = 24) => request<DashboardData>(`/api/v1/dashboard?hours=${hours}`),
  events: (values: Record<string, string | number | undefined>) => request<Page<WakeEvent>>(`/api/v1/events${queryString(values)}`),
  audit: (values: Record<string, string | number | undefined>) => request<Page<AuditEvent>>(`/api/v1/audit${queryString(values)}`),
  settings: () => request<ApplicationSettings>('/api/v1/settings'),
  updateRetention: (body: { wake_event_retention_days: number; audit_event_retention_days: number; rate_limit_seconds: number }) => request<ApplicationSettings>('/api/v1/settings/retention', { method: 'PUT', body: JSON.stringify(body) }),
  runRetention: () => request<{ acquired: boolean; wake_events: number; audit_events: number; sessions: number }>('/api/v1/settings/retention/run', { method: 'POST' }),
}

export async function downloadEventsCsv(values: Record<string, string | number | undefined>): Promise<void> {
  const response = await fetch(`/api/v1/events/export.csv${queryString(values)}`, { credentials: 'same-origin' })
  if (!response.ok) throw new ApiError(response.status, 'export_failed')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a'); link.href = url; link.download = 'wolt-events.csv'; link.click()
  URL.revokeObjectURL(url)
}

export function readableError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'The service could not be reached. Try again.'
  const messages: Record<string, string> = {
    bootstrap_token_not_configured: 'A bootstrap token has not been configured on the server.',
    invalid_bootstrap_token: 'The bootstrap token is not valid.',
    setup_already_completed: 'The Owner account has already been created.',
    invalid_credentials: 'The username, email, or password is not valid.',
    invalid_recovery_credentials: 'The email or recovery code is not valid.',
    too_many_login_attempts: 'Too many attempts. Wait five minutes and try again.',
    too_many_recovery_attempts: 'Too many attempts. Wait five minutes and try again.',
    too_many_setup_attempts: 'Too many setup attempts. Wait five minutes and try again.',
    master_key_not_configured: 'The external encryption master key is not configured.',
    resource_conflict: 'The name or UDP port is already in use, or the requested resource is unavailable.',
    resource_in_use: 'This item is still referenced and cannot be deleted.',
    stale_listener_version: 'This listener changed in another session. Reload it and try again.',
    invalid_or_missing_host_key: 'Provide a valid pinned OpenSSH host-key line.',
    udp_port_outside_allowed_range: 'The UDP port must be inside the configured range.',
    invalid_allowed_source_ip: 'Enter a valid allowed source IP address.',
    invalid_fortigate_interface: 'Enter a valid FortiGate interface name.',
    invalid_gateway_ip: 'Enter a valid gateway or broadcast IP address.',
  }
  return messages[error.detail] ?? 'The request could not be completed.'
}
