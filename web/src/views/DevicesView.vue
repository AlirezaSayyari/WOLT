<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { BookOpenCheck, CheckCircle2, Cpu, Fingerprint, KeyRound, LoaderCircle, Pencil, Plus, RefreshCw, ScanSearch, ShieldCheck, Trash2, X } from '@lucide/vue'
import { api, readableError, type Device, type HostKeyDiscovery } from '../api'
import AppShell from '../components/AppShell.vue'

defineProps<{ theme: 'light' | 'dark' }>(); const emit = defineEmits<{ toggleTheme: [] }>()
const devices = ref<Device[]>([]); const loading = ref(true); const error = ref(''); const panelOpen = ref(false); const editingId = ref<string | null>(null); const saving = ref(false); const testingId = ref<string | null>(null); const testResult = ref<Record<string, string>>({})
const form = reactive({ name: '', host: '', port: 22, hostKey: '', username: '', password: '', enabled: true })
const isEditing = computed(() => editingId.value !== null)
const discovering = ref(false); const discovery = ref<HostKeyDiscovery | null>(null); const fingerprintConfirmed = ref(false)
const createReady = computed(() => isEditing.value || Boolean(discovery.value?.status === 'healthy' && fingerprintConfirmed.value && form.hostKey === discovery.value.host_key))

async function load() { loading.value = true; error.value = ''; try { devices.value = await api.devices() } catch (reason) { error.value = readableError(reason) } finally { loading.value = false } }
function resetDiscovery() { discovery.value = null; fingerprintConfirmed.value = false }
function openCreate() { editingId.value = null; resetDiscovery(); Object.assign(form, { name: '', host: '', port: 22, hostKey: '', username: '', password: '', enabled: true }); panelOpen.value = true }
function openEdit(device: Device) { editingId.value = device.id; resetDiscovery(); Object.assign(form, { name: device.name, host: device.configuration.host, port: device.configuration.port, hostKey: device.configuration.host_key, username: '', password: '', enabled: device.enabled }); panelOpen.value = true }
watch(() => [form.host, form.port, form.username, form.password], () => { if (panelOpen.value && discovery.value) { form.hostKey = ''; resetDiscovery() } })
watch(() => form.hostKey, value => { if (discovery.value && value !== discovery.value.host_key) fingerprintConfirmed.value = false })
async function discoverAndTest() {
  error.value = ''
  if (!form.host || !form.port || !form.username || !form.password) { error.value = 'Enter the host, SSH port, username, and password before discovery.'; return }
  discovering.value = true; resetDiscovery(); form.hostKey = ''
  try {
    const result = await api.discoverDeviceHostKey({ driver_type: 'fortigate_ssh', configuration: { host: form.host, port: Number(form.port), connect_timeout: 5, command_timeout: 10 }, credentials: { username: form.username, password: form.password } })
    discovery.value = result; form.hostKey = result.host_key
  } catch (reason) { error.value = readableError(reason) } finally { discovering.value = false }
}
function discoveryReason(reason: string | null) {
  const messages: Record<string, string> = { ssh_authentication_failed: 'SSH connected and returned this key, but the username or password was rejected.', ssh_timeout: 'The SSH handshake timed out.', ssh_connection_failed: 'WOLT could not establish the SSH connection.' }
  return reason ? (messages[reason] ?? reason) : ''
}
async function save() {
  if (!createReady.value) { error.value = 'Discover, test, and confirm the SSH fingerprint before creating the device.'; return }
  error.value = ''; saving.value = true
  const configuration = { host: form.host, port: Number(form.port), host_key: form.hostKey, connect_timeout: 5, command_timeout: 10 }
  try {
    if (editingId.value) {
      const credentials = form.username || form.password ? { username: form.username, password: form.password } : null
      await api.updateDevice(editingId.value, { name: form.name, configuration, credentials, enabled: form.enabled })
    } else {
      await api.createDevice({ name: form.name, driver_type: 'fortigate_ssh', configuration, credentials: { username: form.username, password: form.password }, enabled: form.enabled })
    }
    panelOpen.value = false; await load()
  } catch (reason) { error.value = readableError(reason) } finally { saving.value = false }
}
async function test(device: Device) { testingId.value = device.id; testResult.value[device.id] = ''; try { const result = await api.testDevice(device.id); testResult.value[device.id] = result.status === 'healthy' ? `Healthy · ${result.latency_ms} ms` : `Failed · ${result.reason}`; await load() } catch (reason) { testResult.value[device.id] = readableError(reason) } finally { testingId.value = null } }
async function remove(device: Device) { if (!window.confirm(`Delete edge device “${device.name}”?`)) return; try { await api.deleteDevice(device.id); await load() } catch (reason) { error.value = readableError(reason) } }
onMounted(load)
</script>

<template><AppShell :theme="theme" @toggle-theme="emit('toggleTheme')">
  <section class="page-heading"><div><p class="eyebrow">WAKE ENGINE / DEVICES</p><h1>Edge devices</h1><p>Configure pinned, encrypted connections used to execute native wake commands.</p></div><button class="primary-button button-link" type="button" @click="openCreate"><Plus :size="16" /> Add device</button></section>
  <p v-if="error" class="form-error page-error" role="alert">{{ error }}</p>
  <section id="fortigate-permissions" class="panel permission-guide"><div class="permission-guide-icon"><BookOpenCheck :size="22" /></div><div><p class="eyebrow">FORTIGATE COMPATIBILITY & PERMISSIONS</p><h2>Prepare and verify a least-privilege service account</h2><p>WOLT v1.0 supports the system-interface Wake-on-LAN command documented for FortiOS <strong>7.2, 7.4, and 7.6</strong>. Other releases and FortiSwitch-style command variants are not claimed as compatible.</p><p>The administrator profile used by this device requires the following tested permissions:</p><ul><li><span>CLI Execute</span><strong>Enabled</strong></li><li><span>Network Group</span><strong>Custom</strong></li><li><span>Packet Capture</span><strong>Read/Write</strong></li></ul><small>This requirement was verified experimentally. Permission labels can vary by FortiOS version. Restrict the account to its working VDOM and do not assign <code>super_admin</code>.</small><div class="command-verification"><strong>Verify the account in FortiGate CLI before adding it</strong><code>execute wake-on-lan &lt;interface&gt; 02:00:00:00:00:01 2 9 &lt;broadcast-ip&gt;</code><p>Replace the interface and broadcast IP with safe values from the account's VDOM. The locally administered example MAC avoids targeting a real host. A permission, parse, or unknown-command error means the account or FortiOS command is not ready for WOLT.</p></div><div class="vdom-guidance"><ShieldCheck :size="18" /><p><strong>Multi-VDOM FortiGate:</strong> if the required interfaces are distributed across VDOMs, create one WOLT Device and one separate VDOM-restricted FortiGate user for each VDOM. WOLT does not switch VDOM context with a global account.</p></div></div></section>
  <section v-if="loading" class="panel loading-panel"><LoaderCircle class="spin" /> Loading devices…</section>
  <section v-else-if="!devices.length" class="panel placeholder-panel"><div class="placeholder-icon"><Cpu :size="28" /></div><h2>No edge devices configured</h2><p>Add the FortiGate connection that can execute Wake-on-LAN inside the destination VDOM.</p><button class="primary-button" type="button" @click="openCreate"><Plus :size="15" /> Add first device</button></section>
  <section v-else class="device-grid">
    <article v-for="device in devices" :key="device.id" class="panel device-card">
      <div class="device-head"><div class="device-icon"><Cpu :size="21" /></div><span class="status-pill" :data-state="device.health_status">{{ device.health_status }}</span></div>
      <h2>{{ device.name }}</h2><p class="mono-line">{{ device.configuration.host }}:{{ device.configuration.port }}</p>
      <dl><div><dt>Driver</dt><dd>FortiGate SSH</dd></div><div><dt>Credential</dt><dd><ShieldCheck :size="13" /> {{ device.credential_configured ? 'Encrypted' : 'Missing' }}</dd></div><div><dt>Listeners</dt><dd>{{ device.listener_count }}</dd></div></dl>
      <p v-if="testResult[device.id]" class="inline-result">{{ testResult[device.id] }}</p>
      <div class="card-actions"><button type="button" :disabled="testingId === device.id" @click="test(device)"><RefreshCw :class="{ spin: testingId === device.id }" :size="14" /> Test</button><button type="button" @click="openEdit(device)"><Pencil :size="14" /> Edit</button><button class="danger-action" type="button" @click="remove(device)"><Trash2 :size="14" /></button></div>
    </article>
  </section>
  <div v-if="panelOpen" class="modal-backdrop" @click.self="panelOpen = false"><section class="side-panel" role="dialog" aria-modal="true" aria-label="Edge device form"><header><div><p class="eyebrow">FORTIGATE SSH</p><h2>{{ isEditing ? 'Edit edge device' : 'Add edge device' }}</h2></div><button class="icon-button" type="button" @click="panelOpen = false"><X :size="17" /></button></header><form class="operations-form" @submit.prevent="save">
    <label>Device name<input v-model.trim="form.name" required maxlength="120" placeholder="Core FortiGate" /></label><div class="form-row"><label>Host or IP<input v-model.trim="form.host" required placeholder="192.0.2.30" /></label><label>SSH port<input v-model.number="form.port" type="number" min="1" max="65535" required /></label></div>
    <div class="permission-reminder"><BookOpenCheck :size="17" /><p>Supported target: FortiOS <strong>7.2 / 7.4 / 7.6</strong> system-interface syntax. Before testing, enable <strong>CLI Execute</strong> and grant <strong>Packet Capture: Read/Write</strong> in a Custom Network profile. Keep the account limited to its working VDOM; use a separate user and WOLT Device for every VDOM.</p></div>
    <div class="secret-block"><div><KeyRound :size="16" /><strong>{{ isEditing ? 'Replace credential (optional)' : 'Device credential' }}</strong></div><p v-if="isEditing">Leave both fields empty to keep the existing encrypted credential.</p><div class="form-row"><label>Username<input v-model.trim="form.username" :required="!isEditing" autocomplete="off" /></label><label>Password<input v-model="form.password" type="password" :required="!isEditing" autocomplete="new-password" /></label></div></div>
    <section v-if="!isEditing" class="discovery-block"><header><div><ScanSearch :size="18" /><strong>Discover and verify SSH identity</strong></div><p>WOLT connects from this server, reads the device key, and tests the supplied credential.</p></header><button class="secondary-button button-link" :disabled="discovering" type="button" @click="discoverAndTest"><LoaderCircle v-if="discovering" class="spin" :size="15" /><ScanSearch v-else :size="15" /> {{ discovery ? 'Run discovery again' : 'Discover key & test connection' }}</button><div v-if="discovery" class="discovery-result" :data-state="discovery.status"><div class="discovery-result-title"><CheckCircle2 v-if="discovery.status === 'healthy'" :size="18" /><Fingerprint v-else :size="18" /><strong>{{ discovery.status === 'healthy' ? `Connection authenticated · ${discovery.latency_ms} ms` : `Key found · authentication failed` }}</strong></div><dl><div><dt>Fingerprint</dt><dd><code>{{ discovery.fingerprint }}</code></dd></div><div><dt>Algorithm</dt><dd>{{ discovery.algorithm }} · {{ discovery.bits }} bits</dd></div></dl><p v-if="discovery.reason" class="form-error">{{ discoveryReason(discovery.reason) }}</p><label v-if="discovery.status === 'healthy'" class="check-label"><input v-model="fingerprintConfirmed" type="checkbox" /><span>I recognize this target and accept this SSH fingerprint. Verify it with the network administrator when possible.</span></label></div></section>
    <label>Pinned SSH host-key line<textarea v-model.trim="form.hostKey" required rows="4" :readonly="!isEditing && Boolean(discovery)" placeholder="Use Discover key & test connection"></textarea><small>{{ isEditing ? 'The saved key remains pinned. Rediscover it only after an approved device key rotation.' : 'Filled automatically after discovery and stored only when you create the device.' }}</small></label>
    <label class="toggle-label"><input v-model="form.enabled" type="checkbox" /><span>{{ form.enabled ? 'Device enabled' : 'Device disabled' }}</span></label>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p><footer><button class="secondary-button" type="button" @click="panelOpen = false">Cancel</button><button class="primary-button" :disabled="saving || !createReady" type="submit"><LoaderCircle v-if="saving" class="spin" :size="15" /><CheckCircle2 v-else :size="15" /> {{ isEditing ? 'Save changes' : 'Create verified device' }}</button></footer>
  </form></section></div>
</AppShell></template>
