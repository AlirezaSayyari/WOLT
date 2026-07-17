export interface SetupStatus {
  database_ready: boolean
  schema_ready: boolean
  setup_required: boolean
  bootstrap_configured: boolean
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
  }
  return messages[error.detail] ?? 'The request could not be completed.'
}
