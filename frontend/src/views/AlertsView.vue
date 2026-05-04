<template>
  <div class="alerts-view">
    <div class="page-header">
      <h2 class="page-title">Alerts</h2>
      <div class="tab-bar">
        <button :class="['tab-btn', { active: activeTab === 'alerts' }]" @click="activeTab = 'alerts'">Definitions</button>
        <button :class="['tab-btn', { active: activeTab === 'history' }]" @click="switchToHistory">
          Firing History
          <span v-if="alertsStore.unviewedCount > 0" class="tab-badge">{{ alertsStore.unviewedCount }}</span>
        </button>
      </div>
    </div>

    <!-- ── Definitions tab ───────────────────────────────────────────────────── -->
    <template v-if="activeTab === 'alerts'">
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
                <button v-if="a.status === 'triggered'" @click="alertsStore.rearmAlert(a.id)" title="Rearm">⟳</button>
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
                <button v-if="a.status === 'triggered'" @click="alertsStore.rearmIndicatorAlert(a.id)" title="Rearm">⟳</button>
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

      <!-- Screener alerts -->
      <div class="section-title" style="margin-top: 24px">Screener Alerts</div>
      <div class="alerts-table-wrap">
        <table class="alerts-table">
          <thead>
            <tr>
              <th>Screener</th>
              <th>Trigger on</th>
              <th>Status</th>
              <th>Repeat</th>
              <th>Triggered</th>
              <th>Notes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in filteredScreener" :key="a.id" :class="`row--${a.status}`">
              <td class="td-symbol">
                <router-link :to="`/screener?select=${a.screener_id}`">{{ a.screener_name || '—' }}</router-link>
              </td>
              <td>{{ a.trigger_type.replace(/_/g, ' ') }}</td>
              <td><span :class="`status-badge status-badge--${a.status}`">{{ a.status }}</span></td>
              <td>
                <button class="inline-toggle" @click="screenerAlertsStore.updateAlert(a.id, { repeat: !a.repeat })"
                        :title="a.repeat ? 'Click to disable repeat' : 'Click to enable repeat'">
                  {{ a.repeat ? '↺' : '—' }}
                </button>
              </td>
              <td class="td-mono">{{ a.triggered_at ? new Date(a.triggered_at).toLocaleString() : '—' }}</td>
              <td class="td-notes">
                <input class="inline-edit" :value="a.notes ?? ''" placeholder="Add note…"
                       @change="screenerAlertsStore.updateAlert(a.id, { notes: ($event.target as HTMLInputElement).value })" />
              </td>
              <td class="td-actions">
                <button v-if="a.status === 'triggered'" @click="screenerAlertsStore.rearmAlert(a.id)" title="Rearm">⟳</button>
                <button v-if="a.status === 'active'" @click="screenerAlertsStore.updateAlert(a.id, { status: 'paused' })" title="Pause">⏸</button>
                <button v-if="a.status === 'paused'" @click="screenerAlertsStore.updateAlert(a.id, { status: 'active' })" title="Resume">▶</button>
                <button @click="screenerAlertsStore.deleteAlert(a.id)" title="Delete" class="btn-danger">✕</button>
              </td>
            </tr>
            <tr v-if="!filteredScreener.length">
              <td colspan="7" class="empty-row">No screener alerts</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- ── History tab ───────────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'history'">
      <div class="history-toolbar">
        <span class="history-count">{{ alertsStore.firingHistory.length }} events</span>
        <button
          v-if="alertsStore.unviewedCount > 0"
          class="mark-all-btn"
          @click="alertsStore.markAllViewed()"
        >Mark all as read</button>
      </div>
      <div class="alerts-table-wrap">
        <table class="alerts-table">
          <thead>
            <tr>
              <th></th>
              <th>Fired at</th>
              <th>Type</th>
              <th>Symbol</th>
              <th>Condition</th>
              <th>Value</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="e in alertsStore.firingHistory"
              :key="e.id"
              :class="['history-row', { 'history-row--unread': !e.is_viewed }]"
              @click="handleHistoryRowClick(e)"
            >
              <td class="td-unread">
                <span v-if="!e.is_viewed" class="unread-dot" title="Unread" />
              </td>
              <td class="td-mono td-nowrap">{{ new Date(e.fired_at).toLocaleString() }}</td>
              <td>
                <span :class="`type-badge type-badge--${e.alert_type}`">{{ e.alert_type }}</span>
              </td>
              <td class="td-symbol">
                <router-link
                  v-if="e.instrument_symbol"
                  :to="`/chart/${e.instrument_symbol}`"
                  @click.stop
                >{{ e.instrument_symbol }}</router-link>
                <span v-else class="td-dim">—</span>
              </td>
              <td class="td-mono td-snapshot">{{ fmtSnapshot(e.condition_snapshot) }}</td>
              <td class="td-mono">{{ e.trigger_value != null ? Number(e.trigger_value).toPrecision(6) : '—' }}</td>
              <td class="td-actions" @click.stop>
                <button v-if="!e.is_viewed" @click="alertsStore.markViewed(e.id)" title="Mark as read">✓</button>
                <button @click="alertsStore.deleteFiringEvent(e.id)" title="Delete" class="btn-danger">✕</button>
              </td>
            </tr>
            <tr v-if="!alertsStore.firingHistory.length">
              <td colspan="7" class="empty-row">No firing history yet</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAlertsStore } from '@/stores/alerts'
import { useScreenerAlertsStore } from '@/stores/screener_alerts'
import { formatMoney } from '@/lib/format'
import type { AlertFiringEvent, IndicatorAlert } from '@/types'

const alertsStore         = useAlertsStore()
const screenerAlertsStore = useScreenerAlertsStore()
const router              = useRouter()
const activeTab  = ref<'alerts' | 'history'>('alerts')
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

const filteredScreener = computed(() =>
  statusFilter.value
    ? screenerAlertsStore.alerts.filter(a => a.status === statusFilter.value)
    : screenerAlertsStore.alerts
)

async function switchToHistory() {
  activeTab.value = 'history'
  await alertsStore.loadHistory()
}

function handleHistoryRowClick(e: AlertFiringEvent) {
  if (!e.is_viewed) alertsStore.markViewed(e.id).catch(console.error)
  if (e.instrument_symbol) router.push(`/chart/${e.instrument_symbol}`)
}

function fmtSnapshot(snap: Record<string, unknown>): string {
  const cond = (snap.condition as string | undefined)?.replace(/_/g, ' ') ?? ''
  const threshold = snap.threshold != null ? ` ${Number(snap.threshold).toPrecision(6)}` : ''
  const indicator = snap.indicator ? ` ${snap.indicator}` : ''
  return `${indicator}${cond}${threshold}`.trim()
}

// Indicators that share the price axis — their values are formatted as currency.
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
  await Promise.all([
    alertsStore.loadAlerts(),
    screenerAlertsStore.loadAlerts(),
    alertsStore.loadHistory(),
  ])
})
</script>

<style scoped>
.alerts-view { padding: 24px; color: #ccc; font-size: 13px; height: 100%; overflow-y: auto; box-sizing: border-box; }

.page-header { display: flex; align-items: baseline; gap: 24px; margin-bottom: 16px; }
.page-title  { color: #fff; font-size: 20px; }

.tab-bar { display: flex; gap: 2px; }
.tab-btn {
  background: none; border: 1px solid #222; color: #666;
  padding: 5px 14px; border-radius: 4px; cursor: pointer; font-size: 12px;
  font-family: inherit; position: relative;
  transition: background 0.1s, color 0.1s;
}
.tab-btn:hover { background: #141414; color: #aaa; }
.tab-btn.active { background: #0f1f2e; border-color: #1e3a5c; color: #64b5f6; }
.tab-badge {
  display: inline-flex; align-items: center; justify-content: center;
  background: #ef5350; color: #fff; border-radius: 8px;
  font-size: 9px; min-width: 14px; height: 14px; padding: 0 3px;
  font-weight: 700; margin-left: 6px; vertical-align: middle;
}

.filter-bar  { margin-bottom: 12px; }
.filter-select { background: #1a1a1a; border: 1px solid #333; color: #aaa; padding: 4px 8px; border-radius: 3px; }

.section-title { color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px; }

.alerts-table-wrap { overflow-x: auto; }
.alerts-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; }
.alerts-table th { background: #111; color: #666; text-align: left; padding: 8px 12px; border-bottom: 1px solid #222; font-weight: 600; }
.alerts-table td { padding: 7px 12px; border-bottom: 1px solid #1a1a1a; }
.alerts-table tr:hover td { background: #111; }

.row--triggered td { color: #555; }

/* History tab */
.history-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.history-count { color: #555; font-size: 12px; }
.mark-all-btn {
  background: none; border: 1px solid #333; color: #888; padding: 3px 10px;
  border-radius: 3px; cursor: pointer; font-size: 11px; font-family: inherit;
}
.mark-all-btn:hover { color: #aaa; border-color: #555; }

.history-row { cursor: pointer; }
.history-row--unread td { color: #ccc; }
.history-row--unread td:not(.td-unread) { }

.td-unread { width: 20px; padding: 7px 4px 7px 12px; }
.unread-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #64b5f6; }

.td-nowrap { white-space: nowrap; }
.td-snapshot { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td-dim { color: #444; }

.type-badge { padding: 2px 7px; border-radius: 10px; font-size: 10px; text-transform: uppercase; font-family: monospace; }
.type-badge--price     { background: #1a2a1a; color: #66bb6a; border: 1px solid #2a4a2a; }
.type-badge--indicator { background: #1a1a2a; color: #7986cb; border: 1px solid #2a2a4a; }
.type-badge--screener  { background: #2a1a1a; color: #ef9a9a; border: 1px solid #4a2a2a; }

.td-symbol a { color: #64b5f6; text-decoration: none; }
.td-mono  { font-family: monospace; }
.td-notes { max-width: 160px; }
.td-expr  { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.status-badge { padding: 2px 7px; border-radius: 10px; font-size: 10px; text-transform: uppercase; }
.status-badge--active    { background: #1a3a1a; color: #66bb6a; border: 1px solid #2e6b2e; }
.status-badge--triggered { background: #1a1a1a; color: #555;    border: 1px solid #333; }
.status-badge--paused    { background: #2a2a1a; color: #ffd54f; border: 1px solid #4a4a1a; }

.inline-toggle {
  background: none; border: none; color: #666; cursor: pointer;
  font-size: 12px; padding: 0;
}
.inline-toggle:hover { color: #aaa; }

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
