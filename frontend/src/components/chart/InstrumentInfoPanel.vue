<template>
  <div v-if="instrument" class="info-section" :class="{ collapsed: !isOpen }">
    <div class="section-header" @click="isOpen = !isOpen">
      <span class="section-title">{{ instrument.name }}</span>
      <span v-if="instrument.currency" class="info-currency">{{ instrument.currency }}</span>
      <span class="section-chevron">{{ isOpen ? '▾' : '▸' }}</span>
    </div>

    <Transition name="slide">
      <div v-if="isOpen" class="info-body">

        <!-- Synthetic expression + constituents -->
        <template v-if="instrument.is_synthetic">
          <div class="info-expr">{{ instrument.expression }}</div>
          <div v-if="instrument.synthetic_constituents?.length" class="info-constituents">
            <span
              v-for="c in instrument.synthetic_constituents"
              :key="c.ticker_alias"
              class="constituent-chip"
              @click="emit('select', c.ticker_alias)"
              :title="`Open ${c.ticker_alias}`"
            >{{ c.ticker_alias }}</span>
          </div>
        </template>

        <!-- Description (shown when present, e.g. for ETFs) -->
        <template v-if="instrument.description">
          <div class="info-description" :class="{ 'info-description--expanded': descExpanded }">{{ instrument.description }}</div>
          <button v-if="instrument.description.length > 160" class="desc-more" @click="descExpanded = !descExpanded">
            {{ descExpanded ? 'less ▴' : 'more ▾' }}
          </button>
        </template>

        <!-- Day range -->
        <template v-if="sessionHigh != null && sessionLow != null">
          <div class="info-label">Day Range</div>
          <div class="range-row">
            <HoverTooltip v-if="rangeOccurrenceTitle('Day low', sessionLowTime, true)" :text="rangeOccurrenceTitle('Day low', sessionLowTime, true)">
              <span class="range-lo range-val--hint">{{ fmt(sessionLow) }}</span>
            </HoverTooltip>
            <span v-else class="range-lo">{{ fmt(sessionLow) }}</span>
            <div class="range-bar-wrap">
              <div class="range-bar-fill" :style="{ width: sessionRangePercent + '%' }" />
            </div>
            <HoverTooltip v-if="rangeOccurrenceTitle('Day high', sessionHighTime, true)" :text="rangeOccurrenceTitle('Day high', sessionHighTime, true)">
              <span class="range-hi range-val--hint">{{ fmt(sessionHigh) }}</span>
            </HoverTooltip>
            <span v-else class="range-hi">{{ fmt(sessionHigh) }}</span>
          </div>
        </template>

        <!-- 52-week range -->
        <template v-if="stats?.week52_high != null && stats?.week52_low != null">
          <div class="info-label">52-Week Range</div>
          <div class="range-row">
            <HoverTooltip v-if="rangeOccurrenceTitle('52-week low', stats?.field_provenance?.week52_low?.observed_at)" :text="rangeOccurrenceTitle('52-week low', stats?.field_provenance?.week52_low?.observed_at)">
              <span class="range-lo range-val--hint">{{ fmt(stats.week52_low) }}</span>
            </HoverTooltip>
            <span v-else class="range-lo">{{ fmt(stats.week52_low) }}</span>
            <div class="range-bar-wrap">
              <div class="range-bar-fill" :style="{ width: rangePercent + '%' }" />
            </div>
            <HoverTooltip v-if="rangeOccurrenceTitle('52-week high', stats?.field_provenance?.week52_high?.observed_at)" :text="rangeOccurrenceTitle('52-week high', stats?.field_provenance?.week52_high?.observed_at)">
              <span class="range-hi range-val--hint">{{ fmt(stats.week52_high) }}</span>
            </HoverTooltip>
            <span v-else class="range-hi">{{ fmt(stats.week52_high) }}</span>
          </div>
        </template>

        <!-- Stats grid -->
          <div class="stats-grid">
          <div v-if="stats?.avg_volume_30d != null" class="stat-item">
            <span class="stat-label">Avg Vol <ProvenanceHint :provenance="stats?.field_provenance?.avg_volume_30d" label="Avg Vol" /></span>
            <span class="stat-val">{{ fmtVol(stats.avg_volume_30d) }}</span>
          </div>
          <div v-if="stats?.market_cap != null" class="stat-item">
            <span class="stat-label">Mkt Cap <ProvenanceHint :provenance="stats?.field_provenance?.market_cap" label="Market Cap" /></span>
            <span class="stat-val">{{ fmtCap(stats.market_cap) }}</span>
          </div>
          <div v-if="stats?.pe_ratio != null" class="stat-item">
            <span class="stat-label">P/E <ProvenanceHint :provenance="stats?.field_provenance?.pe_ratio" label="P/E" /></span>
            <span class="stat-val">{{ fmt(stats.pe_ratio) }}</span>
          </div>
          <div v-if="stats?.beta != null" class="stat-item">
            <span class="stat-label">Beta <ProvenanceHint :provenance="stats?.field_provenance?.beta" label="Beta" /></span>
            <span class="stat-val">{{ fmt(stats.beta) }}</span>
          </div>
          <div v-if="stats?.dividend_yield != null" class="stat-item">
            <span class="stat-label">Div Yield <ProvenanceHint :provenance="stats?.field_provenance?.dividend_yield" label="Dividend Yield" /></span>
            <span class="stat-val">{{ fmtPct(stats.dividend_yield) }}</span>
          </div>
        </div>

        <!-- Equity fundamentals -->
        <template v-if="eq">
          <div class="info-fund-row" v-if="eq.sector">
            <span class="fund-label">Sector <ProvenanceHint :provenance="eq.field_provenance?.sector" label="Sector" /></span>
            <span class="fund-val">{{ eq.sector }}</span>
          </div>
          <div class="info-fund-row" v-if="eq.industry">
            <span class="fund-label">Industry <ProvenanceHint :provenance="eq.field_provenance?.industry" label="Industry" /></span>
            <span class="fund-val">{{ eq.industry }}</span>
          </div>
          <div class="info-fund-row" v-if="eq.country">
            <span class="fund-label">Country <ProvenanceHint :provenance="eq.field_provenance?.country" label="Country" /></span>
            <span class="fund-val">{{ eq.country }}</span>
          </div>
          <div class="info-fund-row" v-if="eq.market_cap_tier">
            <span class="fund-label">Cap Tier</span>
            <span class="fund-val">{{ formatCapTier(eq.market_cap_tier) }}</span>
          </div>
          <div class="info-fund-row" v-if="eq.ipo_date">
            <span class="fund-label">IPO Date</span>
            <span class="fund-val">{{ eq.ipo_date }}</span>
          </div>
          <div class="info-fund-row" v-if="eq.employees">
            <span class="fund-label">Employees</span>
            <span class="fund-val">{{ eq.employees.toLocaleString() }}</span>
          </div>
          <div class="info-fund-row" v-if="eq.website">
            <span class="fund-label">Website</span>
            <a :href="eq.website" target="_blank" rel="noopener" class="fund-link">
              {{ websiteHost(eq.website) }}
            </a>
          </div>
        </template>

      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import HoverTooltip from '@/components/common/HoverTooltip.vue'
import ProvenanceHint from '@/components/common/ProvenanceHint.vue'
import type { Instrument } from '@/types'

const props = defineProps<{
  instrument: Instrument | null
  currentPrice?: number | null
  sessionHigh?: number | null
  sessionLow?: number | null
  sessionHighTime?: string | null
  sessionLowTime?: string | null
}>()
const emit = defineEmits<{ select: [symbol: string] }>()

const isOpen      = ref(true)
const descExpanded = ref(false)

const stats = computed(() => props.instrument?.stats ?? null)
const eq    = computed(() => props.instrument?.equity_detail ?? null)

const rangePercent = computed(() => {
  const s = stats.value
  if (!s || s.week52_high == null || s.week52_low == null) return 50
  const range = s.week52_high - s.week52_low
  if (range <= 0) return 50
  const price = props.currentPrice ?? ((s.week52_high + s.week52_low) / 2)
  return Math.min(100, Math.max(0, ((price - s.week52_low) / range) * 100))
})

const sessionRangePercent = computed(() => {
  const hi = props.sessionHigh, lo = props.sessionLow
  if (hi == null || lo == null) return 50
  const range = hi - lo
  if (range <= 0) return 50
  const price = props.currentPrice ?? ((hi + lo) / 2)
  return Math.min(100, Math.max(0, ((price - lo) / range) * 100))
})

function formatCapTier(tier: string): string {
  return tier.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function fmt(v: number | undefined | null): string {
  if (v == null) return '—'
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number | undefined | null): string {
  if (v == null) return '—'
  return `${(Number(v) * 100).toFixed(2)}%`
}

function fmtVol(v: number | undefined | null): string {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000)     return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000)         return `${(n / 1_000).toFixed(1)}K`
  return n.toFixed(0)
}

function fmtCap(v: number | undefined | null): string {
  if (v == null) return '—'
  const n = Number(v)
  if (n >= 1_000_000_000_000) return `$${(n / 1_000_000_000_000).toFixed(2)}T`
  if (n >= 1_000_000_000)     return `$${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000)         return `$${(n / 1_000_000).toFixed(2)}M`
  return `$${n.toFixed(0)}`
}

function websiteHost(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') }
  catch { return url }
}

function formatCalendarDate(value?: string | null): string | undefined {
  if (!value) return undefined
  const match = value.match(/^\d{4}-\d{2}-\d{2}/)
  if (match) return match[0]

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return undefined
  return `${parsed.getUTCFullYear()}-${String(parsed.getUTCMonth() + 1).padStart(2, '0')}-${String(parsed.getUTCDate()).padStart(2, '0')}`
}

function formatRawTimeOfDay(value?: string | null): string | undefined {
  if (!value) return undefined
  const match = value.match(/T(\d{2}):(\d{2})/)
  if (match) return `${match[1]}:${match[2]}`

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return undefined
  return `${String(parsed.getUTCHours()).padStart(2, '0')}:${String(parsed.getUTCMinutes()).padStart(2, '0')}`
}

function rangeOccurrenceTitle(
  label: string,
  observedAt?: string | null,
  includeTime = false,
): string | undefined {
  const observedDate = formatCalendarDate(observedAt)
  if (!observedDate) return undefined
  if (includeTime) {
    const observedTime = formatRawTimeOfDay(observedAt)
    if (observedTime) return `${label} occurred on ${observedDate} at ${observedTime} UTC`
  }
  return `${label} occurred on ${observedDate}`
}
</script>

<style scoped>
.info-section {
  border-bottom: 1px solid #1a1a1a;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s;
}
.section-header:hover { background: #111; }

.section-title {
  flex: 1;
  font-size: 11px;
  font-weight: 700;
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-currency {
  font-size: 10px;
  color: #555;
  background: #1a1a1a;
  padding: 1px 5px;
  border-radius: 8px;
  flex-shrink: 0;
}

.section-chevron { font-size: 10px; color: #444; flex-shrink: 0; }

.info-body {
  padding: 4px 10px 8px;
}

/* Expression */
.info-expr {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #64b5f6;
  margin-bottom: 6px;
  word-break: break-all;
}

.info-description {
  font-size: 10px;
  color: #555;
  line-height: 1.5;
  margin-bottom: 2px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
}
.info-description--expanded {
  display: block;
  overflow: visible;
}
.desc-more {
  display: block;
  background: none;
  border: none;
  color: #444;
  font-size: 9px;
  font-family: inherit;
  cursor: pointer;
  padding: 0;
  margin-bottom: 6px;
  letter-spacing: 0.03em;
}
.desc-more:hover { color: #888; }

.info-constituents {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.constituent-chip {
  font-size: 10px;
  background: #1a2a3a;
  color: #64b5f6;
  padding: 2px 7px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.1s;
}
.constituent-chip:hover { background: #1e3a5a; }

/* Range */
.info-label {
  font-size: 9px;
  color: #444;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 6px;
  margin-bottom: 3px;
}

.range-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.range-lo, .range-hi {
  font-size: 10px;
  color: #888;
  flex-shrink: 0;
  min-width: 44px;
}
.range-hi { text-align: right; }
.range-val--hint {
  cursor: help;
  text-decoration: underline dotted rgba(120, 120, 120, 0.55);
  text-underline-offset: 2px;
}

.range-bar-wrap {
  flex: 1;
  height: 3px;
  background: #222;
  border-radius: 2px;
  overflow: hidden;
}

.range-bar-fill {
  height: 100%;
  background: #64b5f6;
  border-radius: 2px;
}

/* Stats */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
  margin-bottom: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.stat-label {
  font-size: 9px;
  color: #444;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.stat-val {
  font-size: 11px;
  color: #bbb;
  font-family: 'JetBrains Mono', monospace;
}

/* Equity fundamentals */
.info-fund-row {
  display: flex;
  gap: 6px;
  padding: 2px 0;
  border-bottom: 1px solid #111;
  align-items: baseline;
}

.fund-label {
  font-size: 9px;
  color: #444;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  min-width: 56px;
  flex-shrink: 0;
}

.fund-val {
  font-size: 10px;
  color: #aaa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fund-link {
  font-size: 10px;
  color: #64b5f6;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fund-link:hover { text-decoration: underline; }

/* Slide transition */
.slide-enter-active,
.slide-leave-active { transition: opacity 0.15s, max-height 0.15s; max-height: 500px; overflow: hidden; }
.slide-enter-from,
.slide-leave-to { opacity: 0; max-height: 0; }
</style>
