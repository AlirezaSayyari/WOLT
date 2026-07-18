<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { CheckCircle2, CircleOff, Cpu, KeyRound, LoaderCircle, Pencil, Plus, RefreshCw, ShieldCheck, Trash2, X } from '@lucide/vue'
import { api, readableError, type Device } from '../api'
import AppShell from '../components/AppShell.vue'

defineProps<{ theme: 'light' | 'dark' }>(); const emit = defineEmits<{ toggleTheme: [] }>()
const devices = ref<Device[]>([]); const loading = ref(true); const error = ref(''); const panelOpen = ref(false); const editingId = ref<string | null>(null); const saving = ref(false); const testingId = ref<string | null>(null); const testResult = ref<Record<string, string>>({})
const form = reactive({ name: '', host: '', port: 22, hostKey: '', username: '', password: '', enabled: true })
const isEditing = computed(() => editingId.value !== null)

async function load() { loading.value = true; error.value = ''; try { devices.value = await api.devices() } catch (reason) { error.value = readableError(reason) } finally { loading.value = false } }
function openCreate() { editingId.value = null; Object.assign(form, { name: '', host: '', port: 22, hostKey: '', username: '', password: '', enabled: true }); panelOpen.value = true }
function openEdit(device: Device) { editingId.value = device.id; Object.assign(form, { name: device.name, host: device.configuration.host, port: device.configuration.port, hostKey: device.configuration.host_key, username: '', password: '', enabled: device.enabled }); panelOpen.value = true }
async function save() {
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
    <label>Pinned SSH host-key line<textarea v-model.trim="form.hostKey" required rows="4" placeholder="192.0.2.30 ssh-ed25519 AAAA…"></textarea><small>Generate with <code>ssh-keyscan -p 22 HOST</code> and verify the fingerprint out of band.</small></label>
    <div class="secret-block"><div><KeyRound :size="16" /><strong>{{ isEditing ? 'Replace credential (optional)' : 'Device credential' }}</strong></div><p v-if="isEditing">Leave both fields empty to keep the existing encrypted credential.</p><div class="form-row"><label>Username<input v-model.trim="form.username" :required="!isEditing" autocomplete="off" /></label><label>Password<input v-model="form.password" type="password" :required="!isEditing" autocomplete="new-password" /></label></div></div>
    <label class="toggle-label"><input v-model="form.enabled" type="checkbox" /><span>{{ form.enabled ? 'Device enabled' : 'Device disabled' }}</span></label>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p><footer><button class="secondary-button" type="button" @click="panelOpen = false">Cancel</button><button class="primary-button" :disabled="saving" type="submit"><LoaderCircle v-if="saving" class="spin" :size="15" /><CheckCircle2 v-else :size="15" /> {{ isEditing ? 'Save changes' : 'Create device' }}</button></footer>
  </form></section></div>
</AppShell></template>
