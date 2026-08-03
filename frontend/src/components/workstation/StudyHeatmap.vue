<template>
  <div class="study-heatmap">
    <div class="study-heatmap__grid" :style="{ gridTemplateColumns: `minmax(72px, auto) repeat(${columns.length}, minmax(44px, 1fr))` }">
      <span class="study-heatmap__corner" />
      <strong v-for="column in columns" :key="column">{{ column }}</strong>
      <template v-for="(row, rowIndex) in rows" :key="row">
        <strong>{{ row }}</strong>
        <span v-for="(value, columnIndex) in values[rowIndex]" :key="`${row}-${columnIndex}`" :style="{ background: color(value) }" :title="`${row} / ${columns[columnIndex]}: ${format(value)}`">{{ format(value) }}</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ name: string; rows: string[]; columns: string[]; values: number[][] }>()
const minimum = Math.min(...props.values.flat())
const maximum = Math.max(...props.values.flat())
function color(value: number) {
  const ratio = maximum === minimum ? 0.5 : (value - minimum) / (maximum - minimum)
  return `hsl(${Math.round(215 - ratio * 170)} 65% ${Math.round(24 + ratio * 28)}%)`
}
function format(value: number) { return Number.isInteger(value) ? String(value) : value.toFixed(2) }
</script>

<style scoped>
.study-heatmap { overflow:auto; min-height:100px; margin-top:4px; background:#101419; }
.study-heatmap__grid { display:grid; gap:1px; min-width:max-content; padding:4px; color:#dce6ed; font:9px "Segoe UI",Arial,sans-serif; }
.study-heatmap__grid > * { display:grid; min-height:24px; place-items:center; padding:3px 5px; border:1px solid #293640; }
.study-heatmap__grid strong { background:#1b252d; color:#a9bbc7; }
.study-heatmap__grid span:not(.study-heatmap__corner) { color:#f3f8fa; }
</style>
