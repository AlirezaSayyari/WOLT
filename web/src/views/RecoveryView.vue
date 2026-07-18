<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, ArrowRight, Check, Copy, LoaderCircle } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { api, readableError } from '../api'
import AuthLayout from '../components/AuthLayout.vue'
import { session } from '../session'

defineProps<{ theme: 'light' | 'dark' }>()
const emit = defineEmits<{ toggleTheme: [] }>()
const router = useRouter(); const email = ref(''); const code = ref(''); const password = ref(''); const confirm = ref('')
const error = ref(''); const submitting = ref(false); const replacement = ref(''); const copied = ref(false)
const mode = ref<'email' | 'offline'>('email'); const emailAccepted = ref(false)
async function requestEmailReset() { error.value = ''; submitting.value = true; try { await api.requestPasswordReset(email.value); emailAccepted.value = true } catch (reason) { error.value = readableError(reason) } finally { submitting.value = false } }
async function submit() {
  error.value = ''; if (password.value !== confirm.value) { error.value = 'Passwords do not match.'; return }
  submitting.value = true
  try { const result = await api.recover({ email: email.value, recovery_code: code.value, new_password: password.value }); session.user = result.user; replacement.value = result.recovery_code ?? '' }
  catch (reason) { error.value = readableError(reason) } finally { submitting.value = false }
}
async function copyCode() { await navigator.clipboard.writeText(replacement.value); copied.value = true }
</script>

<template>
  <AuthLayout :theme="theme" eyebrow="ACCOUNT RECOVERY" :title="replacement ? 'Recovery complete' : 'Reset your access'" :description="replacement ? 'Your old recovery code and all previous sessions are now invalid.' : 'Use email recovery or the Owner offline recovery code.'" @toggle-theme="emit('toggleTheme')">
    <div v-if="!replacement" class="recovery-mode"><button :class="{ active: mode === 'email' }" type="button" @click="mode = 'email'">Email link</button><button :class="{ active: mode === 'offline' }" type="button" @click="mode = 'offline'">Owner recovery code</button></div>
    <div v-if="mode === 'email' && emailAccepted" class="recovery-result"><Check :size="30" /><p>If an eligible account and SMTP configuration exist, a reset link has been sent. Check your inbox.</p><RouterLink class="form-link" to="/login"><ArrowLeft :size="14" /> Back to sign in</RouterLink></div>
    <form v-else-if="mode === 'email'" class="auth-form" @submit.prevent="requestEmailReset">
      <label>Account email<input v-model.trim="email" type="email" autocomplete="email" required /></label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button full-button" :disabled="submitting" type="submit"><LoaderCircle v-if="submitting" class="spin" :size="16" /><template v-else>Send reset link <ArrowRight :size="16" /></template></button>
      <RouterLink class="form-link" to="/login"><ArrowLeft :size="14" /> Back to sign in</RouterLink>
    </form>
    <form v-else-if="!replacement" class="auth-form" @submit.prevent="submit">
      <label>Owner email<input v-model.trim="email" type="email" autocomplete="email" required /></label>
      <label>Recovery code<input v-model.trim="code" class="mono-input" autocomplete="off" minlength="20" required /></label>
      <label>New password<input v-model="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required /></label>
      <label>Confirm new password<input v-model="confirm" type="password" autocomplete="new-password" required /></label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button full-button" :disabled="submitting" type="submit"><LoaderCircle v-if="submitting" class="spin" :size="16" /><template v-else>Reset access <ArrowRight :size="16" /></template></button>
      <RouterLink class="form-link" to="/login"><ArrowLeft :size="14" /> Back to sign in</RouterLink>
    </form>
    <div v-else class="recovery-result">
      <p>This replacement recovery code is displayed once:</p>
      <div class="recovery-code"><code>{{ replacement }}</code><button type="button" @click="copyCode"><Check v-if="copied" :size="16" /><Copy v-else :size="16" />{{ copied ? 'Copied' : 'Copy' }}</button></div>
      <button class="primary-button full-button" type="button" @click="router.push('/')">Continue to dashboard <ArrowRight :size="16" /></button>
    </div>
  </AuthLayout>
</template>
