export interface SetupStatus {
  database_ready: boolean
  schema_ready: boolean
  setup_required: boolean
}

export interface HealthStatus {
  status: 'ready' | 'not_ready'
  database: 'ready' | 'unavailable' | 'migration_required'
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  })
  const payload = (await response.json()) as T
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
  return payload
}

export async function loadPlatformStatus(): Promise<{
  setup: SetupStatus
  health: HealthStatus
}> {
  const [setup, health] = await Promise.all([
    getJson<SetupStatus>('/api/v1/setup/status'),
    getJson<HealthStatus>('/api/v1/health/ready'),
  ])
  return { setup, health }
}
