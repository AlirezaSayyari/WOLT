<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { loadPlatformStatus, type SetupStatus } from './api'

type Theme = 'light' | 'dark'

const storedTheme = localStorage.getItem('wolt-theme') as Theme | null
const theme = ref<Theme>(storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : 'dark')
const setup = ref<SetupStatus | null>(null)
const platformState = ref<'loading' | 'ready' | 'degraded'>('loading')
const sidebarOpen = ref(false)

const statusLabel = computed(() => {
  if (platformState.value === 'loading') return 'Checking platform'
  if (platformState.value === 'ready') return 'Platform ready'
  return 'Setup required'
})

function applyTheme(nextTheme: Theme) {
  theme.value = nextTheme
  document.documentElement.dataset.theme = nextTheme
  document.documentElement.style.colorScheme = nextTheme
  localStorage.setItem('wolt-theme', nextTheme)
}

function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark')
}

onMounted(async () => {
  applyTheme(theme.value)
  try {
    const result = await loadPlatformStatus()
    setup.value = result.setup
    platformState.value = result.health.status === 'ready' && !result.setup.setup_required
      ? 'ready'
      : 'degraded'
  } catch {
    platformState.value = 'degraded'
  }
})

const navigation = [
  { group: 'Overview', items: ['Overview', 'Architecture'] },
  { group: 'Wake engine', items: ['Listeners', 'Devices', 'Engine control'] },
  { group: 'Observe', items: ['Events', 'Audit trail'] },
  { group: 'Administration', items: ['Settings'] },
]
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-open': sidebarOpen }">
    <aside class="sidebar" aria-label="Primary navigation">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
        <div><strong>WOLT</strong><small>Network control plane</small></div>
      </div>

      <nav>
        <section v-for="section in navigation" :key="section.group" class="nav-section">
          <p>{{ section.group }}</p>
          <button
            v-for="item in section.items"
            :key="item"
            class="nav-item"
            :class="{ active: item === 'Overview' }"
            type="button"
            @click="sidebarOpen = false"
          >
            <span class="nav-icon" aria-hidden="true"></span>{{ item }}
          </button>
        </section>
      </nav>

      <div class="sidebar-foot">
        <div class="connection-dot"></div>
        <div><strong>WOLT v0.2</strong><small>Foundation preview</small></div>
      </div>
    </aside>

    <button class="scrim" aria-label="Close navigation" @click="sidebarOpen = false"></button>

    <div class="workspace">
      <header class="topbar">
        <button class="menu-button" aria-label="Open navigation" @click="sidebarOpen = true">☰</button>
        <label class="search">
          <span aria-hidden="true">⌕</span>
          <input type="search" placeholder="Search mappings, devices, MAC addresses…" disabled />
          <kbd>⌘ K</kbd>
        </label>
        <div class="topbar-actions">
          <div class="platform-status" :data-state="platformState">
            <span></span>{{ statusLabel }}
          </div>
          <button class="icon-button" type="button" :aria-label="`Use ${theme === 'dark' ? 'light' : 'dark'} theme`" @click="toggleTheme">
            {{ theme === 'dark' ? '☀' : '◐' }}
          </button>
          <button class="avatar" type="button" aria-label="Account menu">AS</button>
        </div>
      </header>

      <main>
        <div v-if="setup?.setup_required" class="setup-banner" role="status">
          <div class="banner-icon">01</div>
          <div>
            <strong>Complete first-run setup</strong>
            <p>The database is ready. Create the initial Owner before activating the wake engine.</p>
          </div>
          <button type="button" disabled>Start setup <span>→</span></button>
        </div>

        <section class="page-heading">
          <div>
            <p class="eyebrow">OPERATIONS / OVERVIEW</p>
            <h1>Wake orchestration</h1>
            <p>Control and observe wake requests across segmented networks.</p>
          </div>
          <div class="heading-actions">
            <button class="secondary-button" type="button" disabled>Send test wake</button>
            <button class="primary-button" type="button" disabled>Resume engine</button>
          </div>
        </section>

        <section class="metric-grid" aria-label="Platform metrics">
          <article class="metric-card">
            <div class="metric-title"><span class="metric-glyph">⌁</span><span>Engine</span><span class="tag paused">PAUSED</span></div>
            <strong>Awaiting setup</strong>
            <p>Web control plane is available</p>
          </article>
          <article class="metric-card">
            <div class="metric-title"><span class="metric-glyph">⇄</span><span>Active listeners</span></div>
            <strong>0 <small>/ 0</small></strong>
            <p>UDP range <code>40000–40099</code></p>
          </article>
          <article class="metric-card">
            <div class="metric-title"><span class="metric-glyph">✓</span><span>Wake success</span></div>
            <strong>—</strong>
            <p>No requests in this period</p>
          </article>
          <article class="metric-card">
            <div class="metric-title"><span class="metric-glyph">◇</span><span>Device health</span></div>
            <strong>0</strong>
            <p>No edge devices configured</p>
          </article>
        </section>

        <section class="dashboard-grid">
          <article class="panel chart-panel">
            <div class="panel-heading"><div><h2>Requests over time</h2><p>Wake outcomes for the last 24 hours</p></div><button type="button" disabled>24 hours⌄</button></div>
            <div class="empty-chart" aria-label="No wake request data">
              <div class="chart-grid-lines"></div>
              <svg viewBox="0 0 640 120" role="img" aria-label="Empty request chart">
                <path d="M5 104 C105 98 160 92 245 95 S390 78 470 84 S560 66 635 72" />
              </svg>
              <div><strong>No wake activity yet</strong><span>Events will appear here after the engine starts.</span></div>
            </div>
          </article>

          <article class="panel flow-panel">
            <div class="panel-heading"><div><h2>Live architecture</h2><p>Current request path</p></div><span class="live-chip">IDLE</span></div>
            <div class="flow">
              <div class="flow-node"><span>01</span><div><strong>Guacamole / PAM</strong><small>UDP magic packet</small></div></div>
              <i></i>
              <div class="flow-node"><span>02</span><div><strong>UDP listener</strong><small>Source + packet validation</small></div></div>
              <i></i>
              <div class="flow-node"><span>03</span><div><strong>Edge device</strong><small>Native wake command</small></div></div>
            </div>
            <button class="text-button" type="button" disabled>Explore architecture <span>→</span></button>
          </article>
        </section>

        <section class="panel events-panel">
          <div class="panel-heading"><div><h2>Recent wake events</h2><p>Latest translated requests and outcomes</p></div><button class="text-button" type="button" disabled>View all events →</button></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Outcome</th><th>MAC address</th><th>Mapping</th><th>Edge device</th><th>Latency</th><th>Occurred</th></tr></thead>
              <tbody><tr><td colspan="6"><div class="empty-table"><span>⌁</span><strong>No events recorded</strong><small>Validated wake requests will be listed here.</small></div></td></tr></tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>
