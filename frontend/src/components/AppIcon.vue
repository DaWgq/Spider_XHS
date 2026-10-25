<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ name: string }>()
const paths: Record<string, string[]> = {
  overview: ['M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z'],
  create: ['M12 5v14M5 12h14'],
  tasks: ['M9 5H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-4', 'M9 2h6v5H9zM7 12h10M7 17h7'],
  user: ['M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0', 'M4 21v-2a8 8 0 0 1 16 0v2'],
  notes: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6M8 13h8M8 17h6'],
  comments: ['M21 11.5a8.5 8.5 0 0 1-8.5 8.5H3l2-5a8.5 8.5 0 1 1 16-3.5z', 'M8 9h8M8 13h5'],
  settings: ['M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z', 'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0'],
  lock: ['M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4M12 14v3'],
  logout: ['M9 3H4v18h5M10 12h11M17 8l4 4-4 4'],
  arrow: ['M4 12h16M14 6l6 6-6 6'],
  check: ['M5 12l4 4L19 6']
}
const lines = computed(() => paths[props.name] || paths.notes)
</script>
<template><svg class="app-icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(line,i) in lines" :key="i" :d="line" /></svg></template>
