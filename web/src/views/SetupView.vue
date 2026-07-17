<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, Check, Copy, LoaderCircle, ShieldCheck } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { api, readableError } from '../api'
import AuthLayout from '../components/AuthLayout.vue'
import { session } from '../session'

defineProps<{ theme: 'light' | 'dark' }>()
const emit = defineEmits<{ toggleTheme: [] }>()
const router = useRouter()
const bootstrapToken = ref(''); const username = ref(''); const email = ref(''); const password = ref(''); const confirmPassword = ref('')
const error = ref(''); const submitting = ref(false); const recoveryCode = ref(''); const saved = ref(false); const copied = ref(false)
const passwordValid = computed(() => password.value.length >= 12)

async function submit() {
  error.value = ''
  if (password.value !== confirmPassword.value) { error.value = 'Passwords do not match.'; return }
  submitting.value = true
  try {
    const result = await api.createOwner({ bootstrap_token: bootstrapToken.value, username: username.value, email: email.value, password: password.value })
    session.user = result.user; if (session.setup) session.setup.setup_required = false
    recoveryCode.value = result.recovery_code ?? ''
    bootstrapToken.value = ''; password.value = ''; confirmPassword.value = ''
  } catch (reason) { error.value = readableError(reason) }
  finally { submitting.value = false }
}

async function copyCode() {
  await navigator.clipboard.writeText(recoveryCode.value); copied.value = true
  window.setTimeout(() => { copied.value = false }, 1600)
}
</script>

<template>
  <AuthLayout :theme="theme" :eyebrow="recoveryCode ? 'RECOVERY CODE' : 'FIRST-RUN SETUP'" :title="recoveryCode ? 'Store this code safely' : 'Create the Owner'" :description="recoveryCode ? 'This is the only time WOLT displays this code. It can reset the Owner password without email.' : 'Create the single initial administrative account. The bootstrap token is read from your server configuration.'" @toggle-theme="emit('toggleTheme')">
    <div v-if="!session.setup?.bootstrap_configured && !recoveryCode" class="form-alert">Set <code>WOLT_BOOTSTRAP_TOKEN</code> in <code>.env.web</code>, then recreate the app container.</div>
    <form v-if="!recoveryCode" class="auth-form" @submit.prevent="submit">
      <label>Bootstrap token<input v-model="bootstrapToken" type="password" autocomplete="off" required /></label>
      <div class="form-row"><label>Owner username<input v-model.trim="username" minlength="3" maxlength="80" pattern="[A-Za-z0-9_.-]+" autocomplete="username" required /></label><label>Recovery email<input v-model.trim="email" type="email" autocomplete="email" required /></label></div>
      <label>Owner password<input v-model="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required /><small :class="{ valid: passwordValid }">At least 12 characters</small></label>
      <label>Confirm password<input v-model="confirmPassword" type="password" autocomplete="new-password" required /></label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button full-button" :disabled="submitting || !session.setup?.bootstrap_configured" type="submit"><LoaderCircle v-if="submitting" class="spin" :size="16" /><template v-else>Create Owner <ArrowRight :size="16" /></template></button>
    </form>
    <div v-else class="recovery-result">
      <div class="recovery-icon"><ShieldCheck :size="25" /></div>
      <div class="recovery-code"><code>{{ recoveryCode }}</code><button type="button" @click="copyCode"><Check v-if="copied" :size="16" /><Copy v-else :size="16" />{{ copied ? 'Copied' : 'Copy' }}</button></div>
      <p>Keep it in your password manager or offline vault. WOLT stores only a one-way hash.</p>
      <label class="check-label"><input v-model="saved" type="checkbox" /> I have stored the recovery code securely.</label>
      <button class="primary-button full-button" :disabled="!saved" type="button" @click="router.push('/')">Open dashboard <ArrowRight :size="16" /></button>
    </div>
  </AuthLayout>
</template>
