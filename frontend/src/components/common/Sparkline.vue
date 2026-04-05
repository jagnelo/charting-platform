<template>
  <svg
    viewBox="0 0 80 32"
    width="80"
    height="32"
    class="sparkline"
    :class="{ 'sparkline--loading': loading }"
  >
    <polyline
      v-if="points"
      :points="points"
      fill="none"
      :stroke="color"
      stroke-width="1.5"
      stroke-linejoin="round"
      stroke-linecap="round"
    />
    <line v-else-if="!loading" x1="8" y1="16" x2="72" y2="16" stroke="#333" stroke-width="1" stroke-dasharray="3 3" />
  </svg>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { sparkTf, useSparklines } from '@/composables/useSparklines'

const props = defineProps<{ symbol: string }>()

const { load, pointsToSvg } = useSparklines()

const rawPts  = ref<number[] | null>(null)
const loading = ref(false)

const points = computed(() => rawPts.value ? pointsToSvg(rawPts.value) : null)

const color = computed(() => {
  if (!rawPts.value || rawPts.value.length < 2) return '#555'
  return rawPts.value[rawPts.value.length - 1] >= rawPts.value[0] ? '#26a69a' : '#ef5350'
})

async function fetch() {
  if (!props.symbol) return
  loading.value = true
  rawPts.value = await load(props.symbol)
  loading.value = false
}

watch([() => props.symbol, sparkTf], fetch, { immediate: true })
</script>

<style scoped>
.sparkline { display: block; flex-shrink: 0; }
.sparkline--loading { opacity: 0.3; }
</style>
