<template>
  <div ref="root" class="study-bars">
    <div v-if="!valid" class="study-bars__state">Bars have no finite observations.</div>
    <div v-else ref="host" class="study-bars__host" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; labels: string[]; values: number[] }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null

function data(): uPlot.AlignedData { return [props.labels.map((_, index) => index), props.values] }
function drawBars(instance: uPlot) {
  const context = instance.ctx
  const zero = instance.valToPos(0, 'y', true)
  context.save()
  props.values.forEach((value, index) => {
    const left = instance.valToPos(index - 0.42, 'x', true)
    const right = instance.valToPos(index + 0.42, 'x', true)
    const top = instance.valToPos(value, 'y', true)
    context.fillStyle = value >= 0 ? '#77c3ee' : '#e58b83'
    context.fillRect(Math.floor(left), Math.min(top, zero), Math.max(1, Math.floor(right - left)), Math.max(1, Math.abs(zero - top)))
  })
  context.restore()
}
function draw() {
  valid.value = props.labels.length > 0 && props.labels.length === props.values.length && props.values.every(value => Number.isFinite(value))
  if (!valid.value || !host.value) return
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(120, host.value.clientHeight)
  if (chart) {
    chart.setData(data())
    chart.setSize({ width, height })
    return
  }
  chart = new uPlot({
    width,
    height,
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: false }, y: { auto: true } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI', values: (_u, values) => values.map(value => props.labels[Math.round(value)] ?? '') },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    ],
    series: [{}, { label: props.name, stroke: 'transparent', width: 0 }],
    plugins: [{ hooks: { draw: [drawBars] } }],
  }, data(), host.value)
}
watch(() => [props.labels, props.values, props.name], async () => { await nextTick(); draw() }, { deep: true })
onMounted(() => { observer = new ResizeObserver(draw); if (root.value) observer.observe(root.value); draw() })
onBeforeUnmount(() => { observer?.disconnect(); chart?.destroy(); chart = null })
</script>

<style scoped>
.study-bars { height:190px; min-height:120px; margin-top:4px; background:#101419; }.study-bars__host { height:100%; }.study-bars__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
