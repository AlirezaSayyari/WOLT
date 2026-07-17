import { reactive } from 'vue'
import { ApiError, api, type SetupStatus, type User } from './api'

export const session = reactive<{
  initialized: boolean
  setup: SetupStatus | null
  user: User | null
}>({ initialized: false, setup: null, user: null })

let initialization: Promise<void> | null = null

export function initializeSession(force = false): Promise<void> {
  if (force) initialization = null
  if (initialization) return initialization
  initialization = (async () => {
    session.setup = await api.setupStatus()
    session.user = null
    if (!session.setup.setup_required) {
      try {
        session.user = await api.me()
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error
      }
    }
    session.initialized = true
  })()
  return initialization
}
