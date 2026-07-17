<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterView } from 'vue-router'

type Theme = 'light' | 'dark'
const saved = localStorage.getItem('wolt-theme')
const theme = ref<Theme>(saved === 'light' ? 'light' : 'dark')

function applyTheme(value: Theme) {
  theme.value = value
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value
  localStorage.setItem('wolt-theme', value)
}

onMounted(() => applyTheme(theme.value))
</script>

<template>
  <RouterView :theme="theme" @toggle-theme="applyTheme(theme === 'dark' ? 'light' : 'dark')" />
</template>
