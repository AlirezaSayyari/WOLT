<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Activity, Boxes, CircleGauge, Cpu, FileClock, LayoutDashboard, ListTree,
  LogOut, Menu, Moon, Network, Search, Settings, ShieldCheck, Sun, X,
} from '@lucide/vue'
import { api } from '../api'
import { session } from '../session'
import BrandMark from './BrandMark.vue'

defineProps<{ theme: 'light' | 'dark' }>()
const emit = defineEmits<{ toggleTheme: [] }>()
const router = useRouter()
const sidebarOpen = ref(false)
const accountOpen = ref(false)

const initials = computed(() => session.user?.username.slice(0, 2).toUpperCase() ?? 'WO')
const navigation = [
  { group: 'Overview', items: [
    { label: 'Overview', to: '/', icon: LayoutDashboard },
    { label: 'Architecture', to: '/architecture', icon: Network },
  ]},
  { group: 'Wake engine', items: [
    { label: 'Listeners', to: '/listeners', icon: ListTree },
    { label: 'Devices', to: '/devices', icon: Cpu },
    { label: 'Engine control', to: '/engine', icon: CircleGauge },
  ]},
  { group: 'Observe', items: [
    { label: 'Events', to: '/events', icon: Activity },
    { label: 'Audit trail', to: '/audit', icon: FileClock },
  ]},
  { group: 'Administration', items: [
    { label: 'Settings', to: '/settings', icon: Settings },
  ]},
]

async function logout() {
  await api.logout().catch(() => undefined)
  session.user = null
  accountOpen.value = false
  await router.push('/login')
}
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-open': sidebarOpen }">
    <aside class="sidebar" aria-label="Primary navigation">
      <RouterLink class="brand" to="/" @click="sidebarOpen = false">
        <BrandMark /><div><strong>WOLT</strong><small>Network control plane</small></div>
      </RouterLink>
      <nav>
        <section v-for="section in navigation" :key="section.group" class="nav-section">
          <p>{{ section.group }}</p>
          <RouterLink v-for="item in section.items" :key="item.to" :to="item.to" class="nav-item" @click="sidebarOpen = false">
            <component :is="item.icon" :size="17" aria-hidden="true" />{{ item.label }}
          </RouterLink>
        </section>
      </nav>
      <div class="sidebar-foot"><span class="connection-dot"></span><div><strong>WOLT v0.2</strong><small>Authenticated preview</small></div></div>
    </aside>

    <button class="scrim" aria-label="Close navigation" @click="sidebarOpen = false"><X /></button>
    <div class="workspace">
      <header class="topbar">
        <button class="menu-button" aria-label="Open navigation" @click="sidebarOpen = true"><Menu /></button>
        <label class="search" title="Global search arrives with event and mapping APIs">
          <Search :size="16" aria-hidden="true" /><input type="search" placeholder="Search becomes available with mappings" disabled /><kbd>⌘ K</kbd>
        </label>
        <div class="topbar-actions">
          <div class="platform-status" data-state="ready"><span></span>Platform ready</div>
          <button class="icon-button" type="button" :aria-label="`Use ${theme === 'dark' ? 'light' : 'dark'} theme`" @click="emit('toggleTheme')">
            <Sun v-if="theme === 'dark'" :size="17" /><Moon v-else :size="17" />
          </button>
          <div class="account">
            <button class="avatar" type="button" :aria-expanded="accountOpen" aria-label="Account menu" @click="accountOpen = !accountOpen">{{ initials }}</button>
            <div v-if="accountOpen" class="account-menu">
              <div><strong>{{ session.user?.username }}</strong><small>{{ session.user?.email }}</small></div>
              <span><ShieldCheck :size="14" /> {{ session.user?.role }}</span>
              <button type="button" @click="logout"><LogOut :size="15" /> Sign out</button>
            </div>
          </div>
        </div>
      </header>
      <main><slot /></main>
    </div>
  </div>
</template>
