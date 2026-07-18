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
import UsersView from './views/UsersView.vue'
import SmtpView from './views/SmtpView.vue'
import AcceptInviteView from './views/AcceptInviteView.vue'
import ResetPasswordView from './views/ResetPasswordView.vue'
import HostOperationsView from './views/HostOperationsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: DashboardView, meta: { protected: true, title: 'Overview' } },
    { path: '/architecture', name: 'architecture', component: ArchitectureView, meta: { protected: true, title: 'Architecture' } },
    { path: '/listeners', name: 'listeners', component: ListenersView, meta: { protected: true, title: 'Listeners' } },
    { path: '/devices', name: 'devices', component: DevicesView, meta: { protected: true, title: 'Edge Devices' } },
    { path: '/engine', name: 'engine', component: EngineView, meta: { protected: true, title: 'Engine Control' } },
    { path: '/events', name: 'events', component: EventsView, meta: { protected: true, title: 'Wake Events' } },
    { path: '/audit', name: 'audit', component: AuditView, meta: { protected: true, roles: ['owner', 'administrator'], title: 'Audit Trail' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { protected: true, roles: ['owner', 'administrator'], title: 'Settings' } },
    { path: '/users', name: 'users', component: UsersView, meta: { protected: true, roles: ['owner'], title: 'Users & Sessions' } },
    { path: '/smtp', name: 'smtp', component: SmtpView, meta: { protected: true, roles: ['owner'], title: 'SMTP' } },
    { path: '/host', name: 'host', component: HostOperationsView, meta: { protected: true, roles: ['owner'], title: 'Host Operations' } },
    { path: '/setup', name: 'setup', component: SetupView, meta: { title: 'First-run Setup' } },
    { path: '/login', name: 'login', component: LoginView, meta: { title: 'Sign In' } },
    { path: '/recover', name: 'recover', component: RecoveryView, meta: { title: 'Account Recovery' } },
    { path: '/accept-invite', name: 'accept-invite', component: AcceptInviteView, meta: { title: 'Accept Invitation' } },
    { path: '/reset-password', name: 'reset-password', component: ResetPasswordView, meta: { title: 'Reset Password' } },
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
  if (session.user && Array.isArray(to.meta.roles) && !to.meta.roles.includes(session.user.role)) return { name: 'overview' }
  if (session.user && (to.name === 'login' || to.name === 'recover')) return { name: 'overview' }
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? 'Network Control Plane')} · WOLT`
})

export default router
