<script setup lang="ts">
import { Moon, Sun } from '@lucide/vue'
import BrandMark from './BrandMark.vue'

defineProps<{ theme: 'light' | 'dark'; eyebrow: string; title: string; description: string }>()
const emit = defineEmits<{ toggleTheme: [] }>()
</script>

<template>
  <div class="auth-layout">
    <section class="auth-story">
      <div class="auth-brand"><BrandMark /><div><strong>WOLT</strong><small>Wake orchestration layer</small></div></div>
      <div class="story-content">
        <p>SECURE CONTROL PLANE</p>
        <h1>One request in.<br><span>One native command out.</span></h1>
        <div class="mini-flow">
          <div><b>01</b><span><strong>PAM / Guacamole</strong><small>UDP magic packet</small></span></div><i></i>
          <div><b>02</b><span><strong>WOLT</strong><small>Validate · map · audit</small></span></div><i></i>
          <div><b>03</b><span><strong>Edge device</strong><small>Native driver command</small></span></div>
        </div>
      </div>
      <small>Credentials stay server-side. Sessions use HttpOnly cookies.</small>
    </section>
    <section class="auth-workspace">
      <button class="icon-button auth-theme" type="button" aria-label="Toggle color theme" @click="emit('toggleTheme')"><Sun v-if="theme === 'dark'" :size="18" /><Moon v-else :size="18" /></button>
      <div class="auth-card">
        <p class="eyebrow">{{ eyebrow }}</p><h2>{{ title }}</h2><p class="auth-description">{{ description }}</p>
        <slot />
      </div>
    </section>
  </div>
</template>
