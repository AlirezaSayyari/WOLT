import { createRouter, createWebHistory } from 'vue-router'
import { initializeSession, session } from './session'
import ArchitectureView from './views/ArchitectureView.vue'
import DashboardView from './views/DashboardView.vue'
import LoginView from './views/LoginView.vue'
import DevicesView from './views/DevicesView.vue'
import EngineView from './views/EngineView.vue'
import ListenersView from './views/ListenersView.vue'
import EventsView from './views/EventsView.vue'
import AuditView from './views/AuditView.vue'
import SettingsView from './views/SettingsView.vue'
import RecoveryView from './views/RecoveryView.vue'
import SetupView from './views/SetupView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: DashboardView, meta: { protected: true } },
    { path: '/architecture', name: 'architecture', component: ArchitectureView, meta: { protected: true } },
    { path: '/listeners', name: 'listeners', component: ListenersView, meta: { protected: true } },
    { path: '/devices', name: 'devices', component: DevicesView, meta: { protected: true } },
    { path: '/engine', name: 'engine', component: EngineView, meta: { protected: true } },
    { path: '/events', name: 'events', component: EventsView, meta: { protected: true } },
    { path: '/audit', name: 'audit', component: AuditView, meta: { protected: true } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { protected: true } },
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
