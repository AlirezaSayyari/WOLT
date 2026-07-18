<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight, LoaderCircle } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api, readableError } from '../api'
import AuthLayout from '../components/AuthLayout.vue'
import { session } from '../session'

defineProps<{ theme: 'light' | 'dark' }>()
const emit = defineEmits<{ toggleTheme: [] }>()
const route = useRoute(); const router = useRouter()
const identifier = ref(''); const password = ref(''); const error = ref(''); const submitting = ref(false)

async function submit() {
  error.value = ''; submitting.value = true
  try {
    const result = await api.login({ identifier: identifier.value, password: password.value })
    session.user = result.user
    await router.push(typeof route.query.redirect === 'string' ? route.query.redirect : '/')
  } catch (reason) { error.value = readableError(reason) }
  finally { submitting.value = false }
}
</script>

<template>
  <AuthLayout :theme="theme" eyebrow="OWNER ACCESS" title="Welcome back" description="Sign in with the Owner username or email." @toggle-theme="emit('toggleTheme')">
    <div v-if="route.query.unavailable" class="form-alert">The API is not ready. Check the database and migrations.</div>
    <form class="auth-form" @submit.prevent="submit">
      <label>Username or email<input v-model.trim="identifier" autocomplete="username" required autofocus /></label>
      <label>Password<input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button full-button" :disabled="submitting" type="submit"><LoaderCircle v-if="submitting" class="spin" :size="16" /><template v-else>Sign in <ArrowRight :size="16" /></template></button>
      <RouterLink class="form-link" to="/recover">Use the offline recovery code</RouterLink>
    </form>
  </AuthLayout>
</template>
