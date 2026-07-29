<template>
  <div class="symbol-list">
    <div class="symbol-list__head">
      <span>{{ label }}</span>
      <span>{{ symbols.length }}</span>
    </div>
    <button
      v-for="symbol in symbols"
      :key="symbol"
      type="button"
      class="symbol-list__row"
      :class="{ 'symbol-list__row--active': symbol === selected }"
      @click="emit('select', symbol)"
    >
      <strong>{{ symbol }}</strong>
      <span>{{ descriptions[symbol] ?? 'Loading canonical metadata…' }}</span>
      <em v-if="metrics?.[symbol] != null">{{ formatMetric(metrics[symbol]) }}</em>
      <b v-if="comparison" class="symbol-list__ratio">{{ symbol }}/{{ comparison }}</b>
    </button>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  label: string
  symbols: string[]
  selected?: string
  comparison?: string
  descriptions?: Record<string, string>
  metrics?: Record<string, number | null>
}>(), {
  selected: '',
  comparison: '',
  descriptions: () => ({}),
  metrics: () => ({}),
})

const emit = defineEmits<{ select: [symbol: string] }>()
const formatMetric = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(2)}%`
</script>

<style scoped>
.symbol-list { height: 100%; overflow: auto; color: #c7d0d8; font: 11px/1.2 "Segoe UI", Arial, sans-serif; background: #11161b; }
.symbol-list__head { height: 23px; display: flex; justify-content: space-between; align-items: center; padding: 0 7px; color: #83929e; background: #181f25; border-bottom: 1px solid #2b343c; text-transform: uppercase; font-size: 10px; letter-spacing: .04em; }
.symbol-list__row { width: 100%; min-height: 31px; display: grid; grid-template-columns: 46px minmax(0, 1fr) auto auto; gap: 5px; align-items: center; padding: 4px 7px; color: inherit; border: 0; border-bottom: 1px solid #20282f; background: transparent; text-align: left; cursor: pointer; }
.symbol-list__row:hover { background: #202a33; }
.symbol-list__row--active { background: #1d4057; box-shadow: inset 2px 0 #66b4e8; }
.symbol-list__row strong { color: #dce9f2; font-size: 11px; }
.symbol-list__row span { overflow: hidden; color: #82909c; white-space: nowrap; text-overflow: ellipsis; }
.symbol-list__ratio { color: #77bde9; font-size: 9px; font-weight: 500; }
.symbol-list__row em { color: #b7d49a; font-size: 10px; font-style: normal; }
</style>
