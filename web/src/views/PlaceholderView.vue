<script setup lang="ts">
import { ArrowLeft, Construction } from '@lucide/vue'
import AppShell from '../components/AppShell.vue'
defineProps<{ theme: 'light' | 'dark'; title: string; area: string; description: string; phase: string }>(); const emit = defineEmits<{ toggleTheme: [] }>()
</script>
<template><AppShell :theme="theme" @toggle-theme="emit('toggleTheme')"><section class="page-heading"><div><p class="eyebrow">{{ area }} / {{ title }}</p><h1>{{ title }}</h1><p>{{ description }}</p></div></section><article class="panel placeholder-panel"><div class="placeholder-icon"><Construction :size="28" /></div><span class="tag roadmap">{{ phase }}</span><h2>The navigation is ready; the operational API comes next.</h2><p>This page is intentionally explicit instead of exposing controls that do not yet have a safe backend implementation.</p><RouterLink class="secondary-button button-link" to="/"><ArrowLeft :size="15" /> Back to overview</RouterLink></article></AppShell></template>
