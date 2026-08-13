<template>
  <div
    ref="host"
    class="sparkline"
    :style="{ width: `${width}px`, height: `${height}px` }"
    :class="{ 'sparkline--loading': loading, 'sparkline--empty': !rawPts && !loading }"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, computed, nextTick } from 'vue'
import uPlot from 'uplot'
import { sparkTf, useSparklines } from '@/composables/useSparklines'

const props = withDefaults(defineProps<{
  symbol?: string
  /** Optional already-materialized series for dense tile/watchlist contexts. */
  points?: number[] | null
  width?: number
  height?: number
}>(), {
  symbol: '',
  width: 80,
  height: 32,
})

const { load } = useSparklines()

const host = ref<HTMLElement | null>(null)
const rawPts  = ref<number[] | null>(null)
const loading = ref(false)
let chart: uPlot | null = null

const color = computed(() => {
  if (!rawPts.value || rawPts.value.length < 2) return '#555'
  return rawPts.value[rawPts.value.length - 1] >= rawPts.value[0] ? '#26a69a' : '#ef5350'
})

async function fetch() {
  if (props.points !== undefined) {
    rawPts.value = props.points
    loading.value = false
    return
  }
  if (!props.symbol) {
    rawPts.value = null
    loading.value = false
    return
  }
  loading.value = true
  rawPts.value = await load(props.symbol)
  loading.value = false
}

function destroyChart() {
  if (chart && typeof chart.destroy === 'function') chart.destroy()
  chart = null
}

async function renderChart() {
  await nextTick()
  destroyChart()
  const values = rawPts.value?.filter(Number.isFinite) ?? []
  if (!host.value || values.length < 2) return

  const x = values.map((_, index) => index)
  chart = new uPlot({
    width: props.width,
    height: props.height,
    padding: [1, 1, 1, 1],
    scales: { x: { time: false }, y: { auto: true } },
    axes: [],
    legend: { show: false },
    cursor: { show: false },
    series: [
      {},
      { stroke: color.value, width: 1.5, points: { show: false } },
    ],
  }, [x, values], host.value)
}

watch([() => props.symbol, () => props.points, sparkTf], fetch, { immediate: true })
watch([rawPts, color], renderChart, { flush: 'post' })
onMounted(renderChart)
onBeforeUnmount(destroyChart)
</script>

<style scoped>
.sparkline { display: block; flex-shrink: 0; }
.sparkline--loading { opacity: 0.3; }
.sparkline--empty {
  background: repeating-linear-gradient(to right, transparent 0 3px, #333 3px 5px) center / 64px 1px no-repeat;
}
</style>
