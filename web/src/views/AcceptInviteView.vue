<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight, CheckCircle2, LoaderCircle } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { api, readableError } from '../api'
import AuthLayout from '../components/AuthLayout.vue'

defineProps<{ theme: 'light' | 'dark' }>(); const emit = defineEmits<{ toggleTheme: [] }>()
const route = useRoute(); const token = String(route.query.token ?? ''); const password = ref(''); const confirm = ref(''); const error = ref(''); const submitting = ref(false); const completed = ref(false)
async function submit() { error.value = ''; if (!token) { error.value = 'The invitation token is missing.'; return } if (password.value !== confirm.value) { error.value = 'Passwords do not match.'; return } submitting.value = true; try { await api.acceptInvitation({ token, password: password.value }); completed.value = true } catch (reason) { error.value = readableError(reason) } finally { submitting.value = false } }
</script>
<template><AuthLayout :theme="theme" eyebrow="SECURE INVITATION" :title="completed ? 'Your account is ready' : 'Set your WOLT password'" description="Invitation links are single-use and expire after 24 hours." @toggle-theme="emit('toggleTheme')"><div v-if="completed" class="recovery-result"><CheckCircle2 :size="34" /><p>Your password is set. You can now sign in.</p><RouterLink class="primary-button full-button button-link" to="/login">Continue to sign in <ArrowRight :size="16" /></RouterLink></div><form v-else class="auth-form" @submit.prevent="submit"><label>New password<input v-model="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required /></label><label>Confirm password<input v-model="confirm" type="password" autocomplete="new-password" required /></label><p v-if="error" class="form-error" role="alert">{{ error }}</p><button class="primary-button full-button" :disabled="submitting" type="submit"><LoaderCircle v-if="submitting" class="spin" :size="16" /><template v-else>Activate account <ArrowRight :size="16" /></template></button></form></AuthLayout></template>
