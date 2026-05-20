<template>
  <div v-if="snapshots.length || forwardCurve.length" class="paper-monitor">
    <div class="paper-monitor__summary">
      <span v-if="snapshots.length" class="paper-monitor__summary-chip">{{ snapshots.length }} snapshots</span>
      <span v-if="latestSnapshot?.latest_equity != null" class="paper-monitor__summary-chip">
        Latest {{ formatMoney(latestSnapshot.latest_equity) }}
      </span>
      <span v-if="latestSnapshot?.trade_count != null" class="paper-monitor__summary-chip">
        {{ latestSnapshot.trade_count }} trades
      </span>
      <span v-if="windowBars != null" class="paper-monitor__summary-chip">{{ windowBars }} bars</span>
    </div>

    <StrategyResultChart
      v-if="equitySeries.length"
      :series="equitySeries"
      label="Paper-forward monitor"
      :currency="true"
      :height="124"
      empty-label="No paper-forward timeline yet."
    />

    <div v-if="recentSnapshots.length" class="paper-monitor__table-wrap">
      <table class="paper-monitor__table">
        <thead>
          <tr>
            <th>Snapshot</th>
            <th>Equity</th>
            <th>Trades</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="snapshot in recentSnapshots" :key="snapshot.snapshot_at">
            <td>{{ formatShortDateTime(snapshot.snapshot_at) }}</td>
            <td>{{ formatMoney(snapshot.latest_equity) }}</td>
            <td>{{ snapshot.trade_count ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div v-else class="paper-monitor__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import StrategyResultChart from '@/components/strategy/StrategyResultChart.vue'

const props = withDefaults(defineProps<{
  snapshots: Array<{
    snapshot_at: string
    latest_equity?: number | null
    trade_count?: number | null
  }>
  forwardCurve?: Array<{
    ts: string
    equity?: number | null
  }>
  windowBars?: number | null
  emptyLabel?: string
}>(), {
  snapshots: () => [],
  forwardCurve: () => [],
  windowBars: null,
  emptyLabel: 'No paper-forward monitor yet.',
})

const latestSnapshot = computed(() => props.snapshots[props.snapshots.length - 1] ?? null)

const equitySeries = computed(() => {
  const snapshotPoints = props.snapshots
    .map(snapshot => ({
      ts: String(snapshot.snapshot_at ?? ''),
      value: Number(snapshot.latest_equity),
    }))
    .filter(point => point.ts && Number.isFinite(point.value))

  if (snapshotPoints.length >= 2) {
    return [
      {
        label: 'Monitor equity',
        color: '#69c18c',
        points: snapshotPoints,
      },
    ]
  }

  const forwardPoints = props.forwardCurve
    .map(point => ({
      ts: String(point.ts ?? ''),
      value: Number(point.equity),
    }))
    .filter(point => point.ts && Number.isFinite(point.value))

  if (forwardPoints.length >= 2) {
    return [
      {
        label: 'Forward curve',
        color: '#69c18c',
        points: forwardPoints,
      },
    ]
  }

  return []
})

const recentSnapshots = computed(() =>
  [...props.snapshots]
    .filter(snapshot => snapshot.snapshot_at)
    .slice(-5)
    .reverse(),
)

function formatMoney(value: number | null | undefined) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return numeric.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  })
}

function formatShortDateTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-GB', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.paper-monitor {
  display: grid;
  gap: 12px;
}

.paper-monitor__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.paper-monitor__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.paper-monitor__table-wrap {
  overflow: auto;
  border: 1px solid #1f252c;
  border-radius: 8px;
}

.paper-monitor__table {
  width: 100%;
  border-collapse: collapse;
}

.paper-monitor__table th,
.paper-monitor__table td {
  padding: 8px 10px;
  border-bottom: 1px solid #181c22;
  font-size: 11px;
  text-align: left;
  white-space: nowrap;
}

.paper-monitor__table th {
  position: sticky;
  top: 0;
  background: #0f1217;
  color: #7f8896;
}

.paper-monitor__empty {
  color: #737373;
  font-size: 12px;
}
</style>
