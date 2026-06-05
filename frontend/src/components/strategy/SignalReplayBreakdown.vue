<template>
  <div v-if="rows.length || normalizedSignalCount > 0" class="signal-replay">
    <div class="signal-replay__summary">
      <span class="signal-replay__summary-chip">{{ normalizedSignalCount }} signals</span>
      <span class="signal-replay__summary-chip">{{ normalizedReplayedSignalCount }} replayed</span>
      <span class="signal-replay__summary-chip">{{ replayRateLabel }}</span>
      <span v-if="dominantRow" class="signal-replay__summary-chip">
        Top {{ dominantRow.label }} {{ dominantRow.count }}
      </span>
    </div>

    <div v-if="rows.length" class="signal-replay__rows">
      <button
        v-for="row in rows"
        :key="row.key"
        type="button"
        class="signal-replay__row"
        :class="{ 'signal-replay__row--active': activeKey === row.key }"
        @mouseenter="hoveredKey = row.key"
        @mouseleave="hoveredKey = null"
        @focus="hoveredKey = row.key"
        @blur="hoveredKey = null"
        @click="togglePinned(row.key)"
      >
        <div class="signal-replay__row-meta">
          <strong>{{ row.label }}</strong>
          <span>{{ row.count }}</span>
        </div>
        <div class="signal-replay__row-submeta">
          <span>{{ row.shareLabel }}</span>
        </div>
        <div class="signal-replay__track">
          <div class="signal-replay__bar" :style="{ width: `${row.width}%` }" />
        </div>
      </button>
    </div>

    <div v-if="activeRow" class="signal-replay__detail">
      <div class="signal-replay__detail-head">
        <strong>{{ activeRow.label }}</strong>
        <span>{{ activeRow.count }} signal{{ activeRow.count === 1 ? '' : 's' }}</span>
      </div>
      <div class="signal-replay__detail-metrics">
        <span>{{ activeRow.shareLabel }}</span>
        <span>{{ replayRateLabel }}</span>
      </div>
      <p class="signal-replay__detail-note">
        {{ activeRow.label }} made up {{ activeRow.shareLabel.toLowerCase() }} of the signal set.
      </p>
    </div>
  </div>
  <div v-else class="signal-replay__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  signalCount?: number | null
  replayedSignalCount?: number | null
  setupTypeBreakdown?: Record<string, number> | null
  emptyLabel?: string
}>(), {
  signalCount: 0,
  replayedSignalCount: 0,
  setupTypeBreakdown: () => ({}),
  emptyLabel: 'No signal replay summary yet.',
})

const rows = computed(() => {
  const total = Math.max(1, normalizedSignalCount.value)
  const values = Object.entries(props.setupTypeBreakdown ?? {})
    .map(([key, count]) => {
      const numericCount = Number(count ?? 0)
      return {
        key,
        label: humanizeToken(key),
        count: numericCount,
        share: total > 0 ? (numericCount / total) * 100 : 0,
      }
    })
    .filter(row => Number.isFinite(row.count) && row.count > 0)
    .sort((left, right) => right.count - left.count)

  const maxCount = Math.max(1, ...values.map(row => row.count))
  return values.map(row => ({
    ...row,
    shareLabel: `${row.share.toFixed(1)}% of signals`,
    width: Math.max(12, Math.min(100, (row.count / maxCount) * 100)),
  }))
})

const normalizedSignalCount = computed(() => Number(props.signalCount ?? 0))
const normalizedReplayedSignalCount = computed(() => Number(props.replayedSignalCount ?? 0))

const replayRateLabel = computed(() => {
  const total = normalizedSignalCount.value
  const replayed = normalizedReplayedSignalCount.value
  if (!Number.isFinite(total) || total <= 0) return '0.0% replayed'
  return `${((replayed / total) * 100).toFixed(1)}% replayed`
})

const dominantRow = computed(() => rows.value[0] ?? null)

const hoveredKey = ref<string | null>(null)
const pinnedKey = ref<string | null>(null)
const activeKey = computed(() => pinnedKey.value || hoveredKey.value)
const activeRow = computed(() => rows.value.find(row => row.key === activeKey.value) ?? null)

function togglePinned(key: string) {
  pinnedKey.value = pinnedKey.value === key ? null : key
}

function humanizeToken(value: string | undefined | null) {
  return String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}
</script>

<style scoped>
.signal-replay {
  display: grid;
  gap: 12px;
}

.signal-replay__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.signal-replay__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.signal-replay__rows {
  display: grid;
  gap: 8px;
}

.signal-replay__row {
  width: 100%;
  display: grid;
  gap: 6px;
  padding: 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.signal-replay__row:hover,
.signal-replay__row:focus-visible,
.signal-replay__row--active {
  background: #10141a;
  border-color: #1f252c;
  outline: none;
}

.signal-replay__row-meta,
.signal-replay__detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #d7d7d7;
  font-size: 11px;
}

.signal-replay__row-submeta,
.signal-replay__detail-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #8a92a0;
  font-size: 10px;
}

.signal-replay__track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: #111317;
  border: 1px solid #1d2837;
  overflow: hidden;
}

.signal-replay__bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #3f79b5, #63b0f0);
}

.signal-replay__detail {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #1f252c;
  border-radius: 8px;
  background: #0f141b;
}

.signal-replay__detail-note {
  color: #9aa3b2;
  font-size: 11px;
  line-height: 1.5;
  margin: 0;
}

.signal-replay__empty {
  color: #737373;
  font-size: 12px;
}
</style>
