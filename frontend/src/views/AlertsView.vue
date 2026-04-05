<template>
  <div class="alerts-view">
    <h2 class="page-title">All Alerts</h2>
    <div class="filter-bar">
      <select v-model="statusFilter" class="filter-select">
        <option value="">All statuses</option>
        <option value="active">Active</option>
        <option value="triggered">Triggered</option>
        <option value="paused">Paused</option>
      </select>
    </div>

    <!-- Price alerts -->
    <div class="section-title">Price Alerts</div>
    <div class="alerts-table-wrap">
      <table class="alerts-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Field</th>
            <th>Condition</th>
            <th>Threshold</th>
            <th>Last price</th>
            <th>Status</th>
            <th>Repeat</th>
            <th>Triggered</th>
            <th>Notes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filteredPrice" :key="a.id" :class="`row--${a.status}`">
            <td class="td-symbol">
              <router-link :to="`/chart/${a.instrument_symbol}`">{{ a.instrument_symbol || '—' }}</router-link>
            </td>
            <td class="td-mono">{{ (a as any).price_field ?? 'close' }}</td>
            <td>{{ a.condition.replace(/_/g, ' ') }}</td>
            <td class="td-mono">{{ formatMoney(Number(a.threshold_price), a.instrument_currency) }}</td>
            <td class="td-mono">{{ a.last_known_price != null ? formatMoney(Number(a.last_known_price), a.instrument_currency) : '—' }}</td>
            <td><span :class="`status-badge status-badge--${a.status}`">{{ a.status }}</span></td>
            <td>
              <button class="inline-toggle" @click="alertsStore.updateAlert(a.id, { repeat: !a.repeat })"
                      :title="a.repeat ? 'Click to disable repeat' : 'Click to enable repeat'">
                {{ a.repeat ? '↺' : '—' }}
              </button>
            </td>
            <td class="td-mono">{{ a.triggered_at ? new Date(a.triggered_at).toLocaleString() : '—' }}</td>
            <td class="td-notes">
              <input class="inline-edit" :value="a.notes ?? ''" placeholder="Add note…"
                     @change="alertsStore.updateAlert(a.id, { notes: ($event.target as HTMLInputElement).value })" />
            </td>
            <td class="td-actions">
              <button v-if="a.status === 'triggered'" @click="alertsStore.rearmAlert(a.id)" title="Rearm">↺</button>
              <button v-if="a.status === 'active'" @click="alertsStore.updateAlert(a.id, { status: 'paused' })" title="Pause">⏸</button>
              <button v-if="a.status === 'paused'" @click="alertsStore.updateAlert(a.id, { status: 'active' })" title="Resume">▶</button>
              <button @click="alertsStore.deleteAlert(a.id)" title="Delete" class="btn-danger">✕</button>
            </td>
          </tr>
          <tr v-if="!filteredPrice.length">
            <td colspan="10" class="empty-row">No price alerts</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Indicator alerts -->
    <div class="section-title" style="margin-top: 24px">Indicator Alerts</div>
    <div class="alerts-table-wrap">
      <table class="alerts-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>TF</th>
            <th>Expression</th>
            <th>Last value A</th>
            <th>Last value B</th>
            <th>Status</th>
            <th>Repeat</th>
            <th>Triggered</th>
            <th>Notes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filteredIndicator" :key="a.id" :class="`row--${a.status}`">
            <td class="td-symbol">
              <router-link :to="`/chart/${a.instrument_symbol}`">{{ a.instrument_symbol || '—' }}</router-link>
            </td>
            <td class="td-mono">{{ a.timeframe }}</td>
            <td class="td-mono td-expr" :title="indAlertExpr(a)">{{ indAlertExpr(a) }}</td>
            <td class="td-mono">{{ fmtIndValue(a.last_value_a, a.indicator_a_type, a.instrument_currency) }}</td>
            <td class="td-mono">{{ fmtIndValue(a.last_value_b, a.indicator_b_type, a.instrument_currency) }}</td>
            <td><span :class="`status-badge status-badge--${a.status}`">{{ a.status }}</span></td>
            <td>
              <button class="inline-toggle" @click="alertsStore.updateIndicatorAlert(a.id, { repeat: !a.repeat })"
                      :title="a.repeat ? 'Click to disable repeat' : 'Click to enable repeat'">
                {{ a.repeat ? '↺' : '—' }}
              </button>
            </td>
            <td class="td-mono">{{ a.triggered_at ? new Date(a.triggered_at).toLocaleString() : '—' }}</td>
            <td class="td-notes">
              <input class="inline-edit" :value="a.notes ?? ''" placeholder="Add note…"
                     @change="alertsStore.updateIndicatorAlert(a.id, { notes: ($event.target as HTMLInputElement).value })" />
            </td>
            <td class="td-actions">
              <button v-if="a.status === 'triggered'" @click="alertsStore.rearmIndicatorAlert(a.id)" title="Rearm">↺</button>
              <button v-if="a.status === 'active'" @click="alertsStore.updateIndicatorAlert(a.id, { status: 'paused' })" title="Pause">⏸</button>
              <button v-if="a.status === 'paused'" @click="alertsStore.updateIndicatorAlert(a.id, { status: 'active' })" title="Resume">▶</button>
              <button @click="alertsStore.deleteIndicatorAlert(a.id)" title="Delete" class="btn-danger">✕</button>
            </td>
          </tr>
          <tr v-if="!filteredIndicator.length">
            <td colspan="10" class="empty-row">No indicator alerts</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import { formatMoney } from '@/lib/format'
import type { IndicatorAlert } from '@/types'

const alertsStore = useAlertsStore()
const statusFilter = ref('')

const filteredPrice = computed(() =>
  statusFilter.value
    ? alertsStore.alerts.filter(a => a.status === statusFilter.value)
    : alertsStore.alerts
)

const filteredIndicator = computed(() =>
  statusFilter.value
    ? alertsStore.indicatorAlerts.filter(a => a.status === statusFilter.value)
    : alertsStore.indicatorAlerts
)

// Indicators that share the price axis — their values are formatted as currency.
// Oscillators on a separate scale (RSI, MACD, ATR, etc.) are plain numbers.
const PRICE_AXIS_TYPES = new Set(['sma','ema','wma','bb','vwap','avwap','close','open','high','low'])

function fmtIndValue(value: number | null, type: string | null | undefined, currency: string | null | undefined): string {
  if (value == null) return '—'
  if (type && PRICE_AXIS_TYPES.has(type)) return formatMoney(Number(value), currency)
  return Number(value).toFixed(4)
}

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`
}

function fmtIndicatorParams(type: string, params: Record<string, unknown>): string {
  if (!params || !Object.keys(params).length) return type.toUpperCase()
  if (type === 'avwap' && params.anchorTime) {
    return `AVWAP(${fmtTs(params.anchorTime as number)})`
  }
  return `${type.toUpperCase()}(${Object.values(params).join(',')})`
}

function indAlertExpr(a: IndicatorAlert): string {
  const indA = fmtIndicatorParams(a.indicator_a_type, a.indicator_a_params ?? {})
  const cond = a.condition.replace(/_/g, ' ')
  const expr = a.indicator_b_type
    ? `${indA} ${cond} ${fmtIndicatorParams(a.indicator_b_type, a.indicator_b_params ?? {})}`
    : `${indA} ${cond} ${a.threshold_value ?? ''}`
  return `${expr} · ${a.timeframe}`
}

onMounted(async () => {
  await alertsStore.loadAlerts()
})
</script>

<style scoped>
.alerts-view { padding: 24px; color: #ccc; font-size: 13px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-title  { color: #fff; font-size: 20px; margin-bottom: 16px; }
.filter-bar  { margin-bottom: 12px; }
.filter-select { background: #1a1a1a; border: 1px solid #333; color: #aaa; padding: 4px 8px; border-radius: 3px; }

.section-title { color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px; }

.alerts-table-wrap { overflow-x: auto; }
.alerts-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; }
.alerts-table th { background: #111; color: #666; text-align: left; padding: 8px 12px; border-bottom: 1px solid #222; font-weight: 600; }
.alerts-table td { padding: 7px 12px; border-bottom: 1px solid #1a1a1a; }
.alerts-table tr:hover td { background: #111; }

.row--triggered td { color: #555; }

.td-symbol a { color: #64b5f6; text-decoration: none; }
.td-mono  { font-family: monospace; }
.td-notes { max-width: 160px; }
.td-expr  { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.status-badge { padding: 2px 7px; border-radius: 10px; font-size: 10px; text-transform: uppercase; }
.status-badge--active    { background: #1a3a1a; color: #66bb6a; border: 1px solid #2e6b2e; }
.status-badge--triggered { background: #1a1a1a; color: #555;    border: 1px solid #333; }
.status-badge--paused    { background: #2a2a1a; color: #ffd54f; border: 1px solid #4a4a1a; }

/* Inline editable repeat toggle */
.inline-toggle {
  background: none; border: none; color: #666; cursor: pointer;
  font-size: 12px; padding: 0;
}
.inline-toggle:hover { color: #aaa; }

/* Inline editable notes input */
.inline-edit {
  background: none; border: none; border-bottom: 1px solid transparent;
  color: #666; font-family: monospace; font-size: 11px; width: 100%; padding: 0;
}
.inline-edit:hover { border-bottom-color: #333; }
.inline-edit:focus { outline: none; border-bottom-color: #64b5f6; color: #aaa; }

.td-actions { display: flex; gap: 4px; }
.td-actions button { background: none; border: 1px solid #333; color: #777; border-radius: 3px; padding: 2px 6px; cursor: pointer; font-size: 11px; }
.td-actions button:hover { color: #aaa; border-color: #555; }
.td-actions .btn-danger:hover { border-color: #ef5350; color: #ef5350; }

.empty-row { text-align: center; color: #444; padding: 32px; }
</style>
