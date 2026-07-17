import { createRouter, createWebHistory } from 'vue-router'
import { initializeSession, session } from './session'
import ArchitectureView from './views/ArchitectureView.vue'
import DashboardView from './views/DashboardView.vue'
import LoginView from './views/LoginView.vue'
import PlaceholderView from './views/PlaceholderView.vue'
import RecoveryView from './views/RecoveryView.vue'
import SetupView from './views/SetupView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: DashboardView, meta: { protected: true } },
    { path: '/architecture', name: 'architecture', component: ArchitectureView, meta: { protected: true } },
    { path: '/listeners', name: 'listeners', component: PlaceholderView, props: { title: 'Listeners', area: 'Wake engine', description: 'Manage UDP port mappings and their edge-device targets.', phase: 'Phase 4' }, meta: { protected: true } },
    { path: '/devices', name: 'devices', component: PlaceholderView, props: { title: 'Devices', area: 'Wake engine', description: 'Configure FortiGate and future pluggable edge-device drivers.', phase: 'Phase 4' }, meta: { protected: true } },
    { path: '/engine', name: 'engine', component: PlaceholderView, props: { title: 'Engine control', area: 'Wake engine', description: 'Start, pause, and inspect the runtime wake engine.', phase: 'Phase 4' }, meta: { protected: true } },
    { path: '/events', name: 'events', component: PlaceholderView, props: { title: 'Events', area: 'Observe', description: 'Search wake requests, results, latency, and correlation IDs.', phase: 'Phase 5' }, meta: { protected: true } },
    { path: '/audit', name: 'audit', component: PlaceholderView, props: { title: 'Audit trail', area: 'Observe', description: 'Review security-sensitive configuration and authentication actions.', phase: 'Phase 5' }, meta: { protected: true } },
    { path: '/settings', name: 'settings', component: PlaceholderView, props: { title: 'Settings', area: 'Administration', description: 'Manage ports, retention, email, database, and account settings.', phase: 'Phase 5' }, meta: { protected: true } },
    { path: '/setup', name: 'setup', component: SetupView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/recover', name: 'recover', component: RecoveryView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  try {
    await initializeSession()
  } catch {
    if (to.name !== 'login') return { name: 'login', query: { unavailable: '1' } }
    return true
  }
  if (session.setup?.setup_required && to.name !== 'setup') return { name: 'setup' }
  if (!session.setup?.setup_required && to.name === 'setup') return session.user ? { name: 'overview' } : { name: 'login' }
  if (to.meta.protected && !session.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (session.user && (to.name === 'login' || to.name === 'recover')) return { name: 'overview' }
  return true
})

export default router
