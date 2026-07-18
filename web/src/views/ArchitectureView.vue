<script setup lang="ts">
import { ArrowDown, CheckCircle2, Cpu, RadioTower, Router, Send, ShieldCheck } from '@lucide/vue'
import AppShell from '../components/AppShell.vue'
defineProps<{ theme: 'light' | 'dark' }>(); const emit = defineEmits<{ toggleTheme: [] }>()
const stages = [
  { icon: Send, number: '01', title: 'PAM / Guacamole', text: 'Sends a standard Wake-on-LAN magic packet to a dedicated WOLT UDP port.', note: 'No vendor-specific integration required' },
  { icon: ShieldCheck, number: '02', title: 'WOLT validation', text: 'Checks the source address, packet shape, destination MAC, rate limit, and port mapping.', note: 'Invalid traffic is rejected and audited' },
  { icon: Router, number: '03', title: 'Driver translation', text: 'Resolves the port to an edge device and converts the request to its native command.', note: 'FortiGate first; extensible driver contract' },
  { icon: Cpu, number: '04', title: 'Target network', text: 'The edge device broadcasts the wake request inside the destination network.', note: 'No routed broadcast dependency' },
]
</script>

<template><AppShell :theme="theme" @toggle-theme="emit('toggleTheme')">
  <section class="page-heading"><div><p class="eyebrow">OVERVIEW / ARCHITECTURE</p><h1>From standard packet to native command</h1><p>WOLT is a translation and control layer between a PAM platform and segmented networks.</p></div></section>
  <section class="architecture-layout"><article class="panel architecture-main"><div class="architecture-stage" v-for="(stage, index) in stages" :key="stage.number"><div class="stage-icon"><component :is="stage.icon" :size="22" /></div><div><span>{{ stage.number }}</span><h2>{{ stage.title }}</h2><p>{{ stage.text }}</p><small><CheckCircle2 :size="13" />{{ stage.note }}</small></div><ArrowDown v-if="index < stages.length - 1" class="stage-arrow" :size="18" /></div></article>
  <aside class="architecture-aside"><article class="panel"><RadioTower :size="22" /><h2>The port is the routing key</h2><p>A standard magic packet contains a MAC address, but it does not identify a routed VLAN or a FortiGate interface. WOLT therefore uses the UDP destination port as an explicit network selector.</p><div class="port-example"><code>WOLT :40016</code><span>→</span><code>FortiGate / VLAN 16</code></div><p class="architecture-callout">The number <code>40016</code> is never sent to FortiGate. It only selects the listener record that stores the Device, interface, broadcast IP, and allowed PAM source.</p></article><article class="panel"><ShieldCheck :size="22" /><h2>Three ports, three jobs</h2><ul><li><strong>40016/UDP:</strong> example PAM → WOLT listener and mapping key</li><li><strong>22/TCP:</strong> WOLT → FortiGate management connection</li><li><strong>9/UDP:</strong> FortiGate → target LAN native wake datagram</li></ul><p class="architecture-callout">Changing the WOLT listener port does not change SSH port 22 or native Wake-on-LAN UDP port 9.</p></article><article class="panel"><ShieldCheck :size="22" /><h2>Security boundary</h2><ul><li>Allow each listener only from its PAM / guacd source</li><li>Publish the same listener range in Docker and the host firewall</li><li>Keep device credentials encrypted and server-side</li><li>Audit configuration and wake outcomes</li></ul></article></aside></section>
</AppShell></template>
