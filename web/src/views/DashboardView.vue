<script setup lang="ts">
import { Activity, ArrowRight, CheckCircle2, CircleGauge, Cpu, ListTree } from '@lucide/vue'
import AppShell from '../components/AppShell.vue'

defineProps<{ theme: 'light' | 'dark' }>()
const emit = defineEmits<{ toggleTheme: [] }>()
</script>

<template>
  <AppShell :theme="theme" @toggle-theme="emit('toggleTheme')">
    <section class="page-heading"><div><p class="eyebrow">OPERATIONS / OVERVIEW</p><h1>Wake orchestration</h1><p>Control and observe wake requests across segmented networks.</p></div><div class="heading-actions"><RouterLink class="secondary-button button-link" to="/listeners">Configure listeners</RouterLink><RouterLink class="primary-button button-link" to="/devices">Add edge device</RouterLink></div></section>
    <section class="metric-grid" aria-label="Platform metrics">
      <article class="metric-card"><div class="metric-title"><span class="metric-glyph"><CircleGauge :size="14" /></span><span>Engine</span><span class="tag paused">PAUSED</span></div><strong>Not configured</strong><p>Configure a device and listener to continue</p></article>
      <article class="metric-card"><div class="metric-title"><span class="metric-glyph"><ListTree :size="14" /></span><span>Active listeners</span></div><strong>0 <small>/ 0</small></strong><p>UDP range <code>40000–40099</code></p></article>
      <article class="metric-card"><div class="metric-title"><span class="metric-glyph"><CheckCircle2 :size="14" /></span><span>Wake success</span></div><strong>—</strong><p>No requests in this period</p></article>
      <article class="metric-card"><div class="metric-title"><span class="metric-glyph"><Cpu :size="14" /></span><span>Device health</span></div><strong>0</strong><p>No edge devices configured</p></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel chart-panel"><div class="panel-heading"><div><h2>Requests over time</h2><p>Wake outcomes for the last 24 hours</p></div><span class="live-chip">24 HOURS</span></div><div class="empty-chart"><div class="chart-grid-lines"></div><svg viewBox="0 0 640 120" aria-hidden="true"><path d="M5 104 C105 98 160 92 245 95 S390 78 470 84 S560 66 635 72" /></svg><div><Activity :size="20" /><strong>No wake activity yet</strong><span>Events will appear after the engine starts.</span></div></div></article>
      <article class="panel flow-panel"><div class="panel-heading"><div><h2>Live architecture</h2><p>Current request path</p></div><span class="live-chip">IDLE</span></div><div class="flow"><div class="flow-node"><span>01</span><div><strong>Guacamole / PAM</strong><small>UDP magic packet</small></div></div><i></i><div class="flow-node"><span>02</span><div><strong>WOLT listener</strong><small>Source + packet validation</small></div></div><i></i><div class="flow-node"><span>03</span><div><strong>Edge device</strong><small>Native wake command</small></div></div></div><RouterLink class="text-button" to="/architecture">Explore architecture <ArrowRight :size="13" /></RouterLink></article>
    </section>
    <section class="panel events-panel"><div class="panel-heading"><div><h2>Recent wake events</h2><p>Latest translated requests and outcomes</p></div><RouterLink class="text-button" to="/events">View all events <ArrowRight :size="13" /></RouterLink></div><div class="table-wrap"><table><thead><tr><th>Outcome</th><th>MAC address</th><th>Mapping</th><th>Edge device</th><th>Latency</th><th>Occurred</th></tr></thead><tbody><tr><td colspan="6"><div class="empty-table"><Activity :size="20" /><strong>No events recorded</strong><small>Validated wake requests will be listed here.</small></div></td></tr></tbody></table></div></section>
  </AppShell>
</template>
