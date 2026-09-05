<template>
  <section v-if="visible" class="etf-holdings-panel">
    <header class="holdings-header">
      <button
        class="collapse-toggle"
        :title="collapsed ? 'Expand ETF holdings' : 'Collapse ETF holdings'"
        @click="collapsed = !collapsed"
      >
        <span :class="{ collapsed }">▾</span>
      </button>
      <div class="header-main">
        <strong>Holdings</strong>
        <small>{{ snapshot?.etf_symbol || props.symbol }} · {{ formatDate(snapshot?.composition_date || capability?.composition_date) }}</small>
      </div>
      <div class="header-meta">
        <span v-if="capability" class="capability-pill" :class="capabilityClass(capability)">
          {{ capabilityLabel(capability) }}
        </span>
        <span>{{ snapshot?.source_provider || capability?.source_provider || 'No source' }}</span>
        <span v-if="snapshot">{{ snapshot.source_quality }}</span>
        <span>{{ snapshot ? `${snapshot.resolved_count ?? 0}/${snapshot.row_count ?? 0} ready` : 'No current snapshot' }}</span>
      </div>
    </header>

    <div v-if="!collapsed" class="holdings-body">
      <div v-if="capability && capability.last_canary_at" class="capability-health" data-testid="etf-capability-health">
        <span>Canary {{ canaryStatusLabel(capability.last_canary_status) }} · {{ formatDateTime(capability.last_canary_at) }}</span>
        <span v-if="capability.last_canary_latency_ms != null">{{ capability.last_canary_latency_ms }} ms</span>
        <span>Failures {{ capability.consecutive_failures }}</span>
        <span v-if="capability.last_canary_recovered">Recovered</span>
        <span v-if="capability.circuit_state">Circuit {{ capability.circuit_state }}</span>
        <span v-if="capability.circuit_open_until">until {{ formatDateTime(capability.circuit_open_until) }}</span>
      </div>
      <div v-if="capability && !capability.usable_for_current_analysis" class="capability-notice">
        <strong>{{ capabilityLabel(capability) }}</strong>
        <span>{{ capability.reason || 'Current constituent analysis is not supported for this symbol.' }}</span>
        <small v-if="capability.displayable_last_known">
          A last-known snapshot may be displayed for historical context, but it must not be treated as current.
        </small>
        <small v-if="capability.failure_class" class="capability-failure-class">
          Last check classification: {{ formatSourceFailureClass(capability.failure_class) }}
        </small>
        <small v-if="capability.symbol_audit?.next_action" class="capability-next-action">
          Next source-review action: {{ capability.symbol_audit.next_action }}
        </small>
      </div>

      <template v-if="snapshot">
      <div class="summary-strip">
        <div>
          <span>Provenance</span>
          <b>{{ provenanceLabel }}</b>
        </div>
        <div>
          <span>Known at</span>
          <b>{{ formatDateTime(snapshot?.known_at) }}</b>
        </div>
        <div>
          <span>Needs review</span>
          <b :class="{ warn: (snapshot?.unresolved_count ?? 0) > 0 }">{{ snapshot?.unresolved_count ?? 0 }}</b>
        </div>
        <div>
          <span>Total weight</span>
          <b>{{ formatWeight(snapshot?.total_weight) }}</b>
        </div>
      </div>

      <div class="holdings-tools">
        <input v-model="filter" type="search" placeholder="Filter holdings" />
        <select v-model="sortMode">
          <option value="weight">Weight</option>
          <option value="symbol">Symbol</option>
          <option value="name">Name</option>
          <option value="unresolved">Needs review first</option>
        </select>
        <span class="visible-count">{{ visibleHoldings.length }}/{{ snapshot?.row_count ?? 0 }} visible</span>
      </div>

      <div class="holdings-workspace">
        <div class="holdings-table" role="table" aria-label="ETF holdings">
          <div class="holdings-row header-row" role="row">
            <span>Symbol</span>
            <span>Name</span>
            <span>Weight</span>
            <span>Value</span>
            <span>Shares</span>
            <span>Status</span>
          </div>
          <div
            v-for="holding in visibleHoldings"
            :key="holding.id"
            class="holdings-row"
            :class="{ unresolved: !holding.is_resolved, selected: selectedHolding?.id === holding.id }"
            role="row"
            tabindex="0"
            @click="selectHolding(holding)"
            @keydown.enter.prevent="selectHolding(holding)"
            @dblclick="openHolding(holding)"
          >
            <span>
              <b>{{ holdingSymbol(holding) }}</b>
              <small>{{ holding.holding_type }}</small>
            </span>
            <span>{{ holdingName(holding) }}</span>
            <span>
              <b>{{ formatWeight(holding.weight) }}</b>
              <i class="weight-track">
                <i :style="{ width: weightWidth(holding.weight) }"></i>
              </i>
            </span>
            <span>{{ formatMoney(holding.market_value, holding.currency) }}</span>
            <span>{{ formatQuantity(holding.shares) }}</span>
            <span :class="statusClass(holding)">{{ statusLabel(holding) }}</span>
          </div>
        </div>

        <aside v-if="selectedHolding" class="holding-detail" aria-label="Selected holding details">
          <div class="detail-head">
            <div>
              <small>Selected holding</small>
              <strong>{{ holdingSymbol(selectedHolding) }}</strong>
              <span>{{ holdingName(selectedHolding) }}</span>
            </div>
            <div class="detail-actions">
              <button
                type="button"
                class="nav-button"
                :disabled="!hasPreviousHolding"
                title="Previous holding"
                @click="moveSelection(-1)"
              >
                ‹
              </button>
              <button
                type="button"
                class="nav-button"
                :disabled="!hasNextHolding"
                title="Next holding"
                @click="moveSelection(1)"
              >
                ›
              </button>
              <button
                type="button"
                class="open-holding-button"
                :disabled="!openableSymbol(selectedHolding)"
                @click="openHolding(selectedHolding)"
              >
                Open
              </button>
            </div>
          </div>

          <div class="detail-grid">
            <div>
              <span>Weight</span>
              <b>{{ formatWeight(selectedHolding.weight) }}</b>
            </div>
            <div>
              <span>Market value</span>
              <b>{{ formatMoney(selectedHolding.market_value, selectedHolding.currency) }}</b>
            </div>
            <div>
              <span>Shares</span>
              <b>{{ formatQuantity(selectedHolding.shares) }}</b>
            </div>
            <div>
              <span>Venue</span>
              <b>{{ venueLabel(selectedHolding) }}</b>
            </div>
            <div>
              <span>Row type</span>
              <b>{{ selectedHolding.row_type }}</b>
            </div>
            <div>
              <span>Availability</span>
              <b :class="statusClass(selectedHolding)">{{ statusLabel(selectedHolding) }}</b>
            </div>
          </div>

          <dl class="identifier-list">
            <div>
              <dt>CUSIP</dt>
              <dd>{{ selectedHolding.cusip || '—' }}</dd>
            </div>
            <div>
              <dt>ISIN</dt>
              <dd>{{ selectedHolding.isin || '—' }}</dd>
            </div>
            <div>
              <dt>SEDOL</dt>
              <dd>{{ selectedHolding.sedol || '—' }}</dd>
            </div>
          </dl>
        </aside>

        <div v-else class="empty-state">
          No holdings match this filter.
        </div>
      </div>
      </template>
      <div v-else class="empty-state">
        No current holdings snapshot is available for this ETF.
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { formatSourceFailureClass } from '@/lib/workstation/sourceCapability'
import type { ETFHolding, ETFHoldingsCapability, ETFHoldingsSnapshot } from '@/types'

const props = defineProps<{ symbol: string | null }>()
const emit = defineEmits<{
  availability: [available: boolean]
  openSymbol: [symbol: string]
}>()

const snapshot = ref<ETFHoldingsSnapshot | null>(null)
const capability = ref<ETFHoldingsCapability | null>(null)
const filter = ref('')
const sortMode = ref<'weight' | 'symbol' | 'name' | 'unresolved'>('weight')
const collapsed = ref(false)
const selectedHoldingId = ref<number | null>(null)
let loadSeq = 0

const visible = computed(() => !!snapshot.value || !!capability.value)
const capabilityLabel = (value: ETFHoldingsCapability) =>
  String(value.availability || 'unknown').replace(/_/g, ' ')
const capabilityClass = (value: ETFHoldingsCapability) => `capability--${value.availability || 'unknown'}`
const canaryStatusLabel = (value?: string | null) => String(value || 'unknown').replace(/_/g, ' ')
const provenanceLabel = computed(() =>
  String(snapshot.value?.provenance || '').replace(/_/g, ' ') || '—'
)

const visibleHoldings = computed(() => {
  const term = filter.value.trim().toLowerCase()
  const rows = [...(snapshot.value?.holdings ?? [])]
    .filter(row => {
      if (!term) return true
      return [
        row.constituent_symbol,
        row.reported_symbol,
        row.constituent_name,
        row.reported_name,
        row.cusip,
        row.isin,
      ].some(value => String(value ?? '').toLowerCase().includes(term))
    })

  rows.sort((a, b) => {
    if (sortMode.value === 'symbol') {
      return labelFor(a, 'symbol').localeCompare(labelFor(b, 'symbol'))
    }
    if (sortMode.value === 'name') {
      return labelFor(a, 'name').localeCompare(labelFor(b, 'name'))
    }
    if (sortMode.value === 'unresolved') {
      return Number(a.is_resolved) - Number(b.is_resolved)
    }
    return numeric(b.weight) - numeric(a.weight)
  })
  return rows
})

const selectedHolding = computed(() => {
  const rows = visibleHoldings.value
  return rows.find(row => row.id === selectedHoldingId.value) ?? rows[0] ?? null
})
const selectedIndex = computed(() => {
  const selected = selectedHolding.value
  if (!selected) return -1
  return visibleHoldings.value.findIndex(row => row.id === selected.id)
})
const hasPreviousHolding = computed(() => selectedIndex.value > 0)
const hasNextHolding = computed(() =>
  selectedIndex.value >= 0 && selectedIndex.value < visibleHoldings.value.length - 1
)

function labelFor(row: ETFHolding, mode: 'symbol' | 'name') {
  if (mode === 'symbol') return preferredHoldingSymbol(row)
  return row.constituent_name || row.reported_name || ''
}

function numeric(value: number | string | null | undefined) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function formatWeight(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  const n = numeric(value)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(2)}%`
}

function formatQuantity(value: number | string | null | undefined) {
  if (value == null || value === '') return '—'
  const n = numeric(value)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function formatMoney(value: number | string | null | undefined, currency?: string | null) {
  if (value == null || value === '') return '—'
  const n = numeric(value)
  if (!Number.isFinite(n)) return '—'
  const amount = n.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return currency ? `${currency} ${amount}` : amount
}

function isSyntheticHoldingSymbol(value: string | null | undefined) {
  return String(value || '').toUpperCase().startsWith('HOLDING-')
}

function preferredHoldingSymbol(row: ETFHolding) {
  const constituent = isSyntheticHoldingSymbol(row.constituent_symbol) ? '' : row.constituent_symbol
  return constituent || row.reported_symbol || ''
}

function holdingSymbol(row: ETFHolding) {
  return preferredHoldingSymbol(row) || '—'
}

function holdingName(row: ETFHolding) {
  return row.constituent_name || row.reported_name || '—'
}

function openableSymbol(row: ETFHolding) {
  if (!capability.value?.usable_for_current_analysis || capability.value.availability !== 'current') {
    return ''
  }
  if (!isTradableHolding(row)) return ''
  return preferredHoldingSymbol(row)
}

function isReferenceHolding(row: ETFHolding) {
  return row.row_type !== 'security' || ['cash', 'currency', 'collateral'].includes(row.holding_type)
}

function isTradableHolding(row: ETFHolding) {
  return row.is_resolved && !isReferenceHolding(row)
}

function weightWidth(value: number | string | null | undefined) {
  const percentage = Math.max(0, Math.min(100, numeric(value) * 100))
  return `${percentage}%`
}

function statusLabel(row: ETFHolding) {
  if (isTradableHolding(row)) return 'ready'
  if (isReferenceHolding(row)) return 'reference'
  return 'needs match'
}

function statusClass(row: ETFHolding) {
  return {
    'status-ok': isTradableHolding(row),
    'status-warn': !isTradableHolding(row) && !isReferenceHolding(row),
    'status-muted': isReferenceHolding(row),
  }
}

function venueLabel(row: ETFHolding) {
  return [row.exchange, row.country].filter(Boolean).join(' · ') || '—'
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00Z`).toLocaleDateString()
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function openHolding(row: ETFHolding) {
  const target = openableSymbol(row)
  if (target) emit('openSymbol', target)
}

function selectHolding(row: ETFHolding) {
  selectedHoldingId.value = row.id
}

function moveSelection(delta: number) {
  const next = visibleHoldings.value[selectedIndex.value + delta]
  if (next) selectHolding(next)
}

async function load() {
  const symbol = props.symbol?.trim()
  const seq = ++loadSeq
  filter.value = ''
  selectedHoldingId.value = null
  if (!symbol) {
    snapshot.value = null
    capability.value = null
    emit('availability', false)
    return
  }
  try {
    const [loaded, capabilityResult] = await Promise.all([
      api.get<ETFHoldingsSnapshot>(`/etf-holdings/${encodeURIComponent(symbol)}/latest`).catch(() => null),
      api.get<ETFHoldingsCapability>(`/etf-holdings/${encodeURIComponent(symbol)}/capability`).catch(() => null),
    ])
    if (seq !== loadSeq) return
    snapshot.value = loaded
    capability.value = capabilityResult
    emit('availability', Boolean(capabilityResult?.usable_for_current_analysis && capabilityResult.availability === 'current'))
  } catch {
    if (seq !== loadSeq) return
    snapshot.value = null
    capability.value = null
    emit('availability', false)
  }
}

watch(() => props.symbol, load, { immediate: true })
watch(visibleHoldings, rows => {
  if (!rows.length) {
    selectedHoldingId.value = null
    return
  }
  if (!rows.some(row => row.id === selectedHoldingId.value)) {
    selectedHoldingId.value = rows[0].id
  }
})
</script>

<style scoped>
.etf-holdings-panel {
  border-top: 1px solid #171717;
  background: #0c0c0c;
  flex-shrink: 0;
  max-height: 420px;
  min-height: 44px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.holdings-header {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid #171717;
}
.collapse-toggle {
  border: 0;
  background: transparent;
  color: #8abff0;
  cursor: pointer;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  font-family: 'JetBrains Mono', monospace;
}
.collapse-toggle span {
  display: inline-block;
  transition: transform 0.12s ease;
}
.collapse-toggle span.collapsed { transform: rotate(-90deg); }
.header-main {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.header-main strong {
  color: #eee;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
}
.header-main small,
.header-meta {
  color: #777;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}
.header-meta {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  white-space: nowrap;
}
.capability-pill {
  display: inline-flex;
  align-items: center;
  border: 1px solid #27323d;
  border-radius: 999px;
  padding: 3px 7px;
  text-transform: capitalize;
}
.capability--current { color: #7bdc9a; border-color: #28583a; }
.capability--degraded,
.capability--stale { color: #f3c969; border-color: #625025; }
.capability--unavailable,
.capability--unknown { color: #f09a9a; border-color: #613535; }
.capability--not_applicable { color: #9ca3af; border-color: #3b4148; }
.holdings-body {
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 8px;
  padding: 10px 12px 12px;
}
.capability-notice {
  display: grid;
  gap: 4px;
  border: 1px solid #5a4820;
  border-radius: 8px;
  background: #17130a;
  color: #f3d98a;
  padding: 9px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  line-height: 1.4;
}
.capability-notice strong { text-transform: capitalize; }
.capability-notice span { color: #d7c17d; }
.capability-notice small { color: #aa9862; }
.capability-notice .capability-failure-class { color: #f0c66a; }
.capability-notice .capability-next-action { color: #b9c6d8; }
.capability-health {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  color: #8f9bab;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  line-height: 1.4;
}
.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.summary-strip div {
  border: 1px solid #1f1f1f;
  border-radius: 8px;
  padding: 7px 9px;
  background: #101010;
}
.summary-strip span {
  display: block;
  color: #777;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.summary-strip b {
  display: block;
  color: #d6d6d6;
  margin-top: 3px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-strip b.warn { color: #f3c969; }
.holdings-tools {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 160px auto;
  gap: 8px;
  align-items: center;
}
.holdings-tools input,
.holdings-tools select {
  background: #0d0d0d;
  border: 1px solid #242424;
  border-radius: 7px;
  color: #ccc;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  padding: 7px 9px;
  min-height: 32px;
}
.visible-count {
  color: #777;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  white-space: nowrap;
}
.holdings-workspace {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.85fr);
  gap: 10px;
}
.holdings-table {
  min-height: 0;
  overflow: auto;
  border: 1px solid #181818;
  border-radius: 8px;
}
.holdings-row {
  width: 100%;
  display: grid;
  grid-template-columns: 110px minmax(180px, 1fr) 98px 120px 100px 92px;
  gap: 12px;
  align-items: center;
  border: 0;
  border-bottom: 1px solid #171717;
  background: transparent;
  color: #aaa;
  text-align: left;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  padding: 8px 10px;
}
.holdings-row:not(.header-row) {
  cursor: pointer;
}
.holdings-row:not(.header-row):hover,
.holdings-row.selected {
  background: #121a21;
}
.holdings-row.selected {
  box-shadow: inset 3px 0 0 #58a9ee;
}
.header-row {
  position: sticky;
  top: 0;
  z-index: 1;
  color: #777;
  background: #101010;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.holdings-row b {
  color: #e2e2e2;
  font-weight: 800;
}
.holdings-row small {
  display: block;
  color: #777;
  font-size: 9px;
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.holdings-row.unresolved {
  color: #888;
}
.weight-track {
  display: block;
  margin-top: 4px;
  height: 4px;
  border-radius: 999px;
  background: #111923;
  overflow: hidden;
}
.weight-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #4a79a0, #71c5f7);
}
.status-ok { color: #7bdc9a; }
.status-warn { color: #f3c969; }
.status-muted { color: #888; }
.holding-detail {
  min-width: 0;
  border: 1px solid #1d2934;
  border-radius: 10px;
  background: #0b1016;
  padding: 12px;
  overflow: auto;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  border-bottom: 1px solid #1d2934;
  padding-bottom: 10px;
}
.detail-head small,
.detail-grid span,
.identifier-list dt {
  color: #7f8996;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.detail-head strong {
  display: block;
  margin-top: 4px;
  color: #f1f5f9;
  font-family: 'JetBrains Mono', monospace;
  font-size: 18px;
}
.detail-head span {
  display: block;
  margin-top: 3px;
  color: #9ca3af;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
.detail-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}
.detail-actions button {
  border: 1px solid #26384a;
  background: #111923;
  color: #9bd1ff;
  border-radius: 7px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  min-height: 30px;
}
.detail-actions button:disabled {
  opacity: 0.38;
  cursor: default;
}
.nav-button {
  width: 30px;
  font-size: 18px;
}
.open-holding-button {
  padding: 0 10px;
  font-size: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.detail-grid div {
  border: 1px solid #17212c;
  border-radius: 8px;
  background: #0d1219;
  padding: 8px;
}
.detail-grid b {
  display: block;
  margin-top: 4px;
  color: #d9e1ea;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.identifier-list {
  margin: 10px 0 0;
  display: grid;
  gap: 6px;
}
.identifier-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.identifier-list dd {
  margin: 0;
  color: #cfd6df;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}
.resolution-note {
  margin: 10px 0 0;
  border-top: 1px solid #1d2934;
  padding-top: 10px;
  color: #aab2be;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.45;
}
.empty-state {
  color: #777;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  padding: 12px;
  border: 1px solid #181818;
  border-radius: 8px;
}
@media (max-width: 900px) {
  .header-meta { display: none; }
  .summary-strip { grid-template-columns: 1fr 1fr; }
  .holdings-tools { grid-template-columns: 1fr; }
  .holdings-workspace { grid-template-columns: 1fr; }
  .holdings-row {
    grid-template-columns: 90px minmax(120px, 1fr) 80px;
  }
  .holdings-row span:nth-child(n + 4) { display: none; }
}
</style>
