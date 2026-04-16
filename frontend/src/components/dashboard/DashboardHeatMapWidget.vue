<template>
  <div ref="rootEl" class="heatmap-widget">
    <!-- Toolbar -->
    <div class="hm-toolbar">
      <div class="hm-metric-pills">
        <button
          v-for="m in COLOR_METRICS"
          :key="m.value"
          class="pill"
          :class="{ active: colorMetric === m.value }"
          @click="setColorMetric(m.value)"
        >{{ m.label }}</button>
      </div>
      <button class="pill hm-refresh" :class="{ spinning: loading }" title="Refresh" @click="load">↻</button>
    </div>

    <!-- States -->
    <div v-if="loading && !rows.length" class="widget-state">Loading…</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <div v-else-if="!rows.length" class="widget-state muted">No instruments available</div>

    <!-- Treemap canvas -->
    <div
      v-else
      ref="canvasEl"
      class="hm-canvas"
      @mousemove="onMouseMove"
      @mouseleave="tooltip = null"
    >
      <!-- Group labels sit behind tiles -->
      <template v-if="props.config.groupBy !== 'none'">
        <div
          v-for="g in layout.groups"
          :key="'gl-' + g.key"
          class="hm-group-label"
          :style="{ left: g.x + 'px', top: g.y + 'px', width: g.w + 'px' }"
        >{{ g.key }}</div>
      </template>

      <!-- Tiles -->
      <router-link
        v-for="tile in layout.tiles"
        :key="tile.symbol"
        class="hm-tile"
        :style="tileStyle(tile)"
        :to="`/chart/${encodeURIComponent(tile.symbol)}`"
        @click.stop
      >
        <!-- Alert badge -->
        <span v-if="tile.alertCount" class="hm-alert-badge">{{ tile.alertCount }}</span>

        <span class="hm-sym">{{ tile.symbol }}</span>
        <svg v-if="tile.sparkline.length > 1 && tile.h > 52" class="hm-spark" :viewBox="`0 0 ${tile.sparkline.length - 1} 20`" preserveAspectRatio="none">
          <polyline :points="sparkPoints(tile.sparkline)" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="1.5" />
        </svg>
        <span v-if="tile.h > 44" class="hm-val">{{ formatMetricValue(tile.metricValue) }}</span>
      </router-link>

      <!-- Tooltip -->
      <div
        v-if="tooltip"
        class="hm-tooltip"
        :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
      >
        <div class="tt-header">
          <strong>{{ tooltip.row.symbol }}</strong>
          <span class="tt-name">{{ tooltip.row.name }}</span>
        </div>
        <div class="tt-grid">
          <template v-for="entry in tooltipEntries(tooltip.row)" :key="entry.label">
            <span class="tt-label">{{ entry.label }}</span>
            <span class="tt-val" :class="entry.cls">{{ entry.value }}</span>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { useAlertsStore } from '@/stores/alerts'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Watchlist } from '@/types'

// ── Props / emits ─────────────────────────────────────────────────────────────
const props = defineProps<{
  config: Record<string, any>
}>()
const emit = defineEmits<{
  (e: 'patchConfig', patch: Record<string, any>): void
}>()

// ── Metric definitions ────────────────────────────────────────────────────────
const COLOR_METRICS = [
  { value: 'perf_1d',       label: '1D'   },
  { value: 'perf_1w',       label: '1W'   },
  { value: 'perf_1m',       label: '1M'   },
  { value: 'perf_mtd',      label: 'MTD'  },
  { value: 'perf_ytd',      label: 'YTD'  },
  { value: 'perf_1y',       label: '1Y'   },
  { value: 'rsi_14',        label: 'RSI'  },
  { value: 'rel_volume',    label: 'Rvol' },
  { value: 'dist_52w_high', label: '52H'  },
  { value: 'dist_52w_low',  label: '52L'  },
]

// ── Stores ────────────────────────────────────────────────────────────────────
const watchlistStore = useWatchlistStore()
const alertsStore = useAlertsStore()

// ── State ─────────────────────────────────────────────────────────────────────
interface HeatRow {
  instrument_id: number
  symbol: string
  name: string
  sector: string | null
  industry: string | null
  market_cap: number | null
  avg_volume_30d: number | null
  current_price: number | null
  perf_1d: number | null
  perf_1w: number | null
  perf_1m: number | null
  perf_mtd: number | null
  perf_ytd: number | null
  perf_1y: number | null
  rsi_14: number | null
  rel_volume: number | null
  dist_52w_high: number | null
  dist_52w_low: number | null
  sparkline: number[]
}

interface Tile {
  symbol: string
  name: string
  x: number; y: number; w: number; h: number
  metricValue: number | null
  sparkline: number[]
  alertCount: number
  row: HeatRow
}

interface GroupLabel {
  key: string
  x: number; y: number; w: number
}

const rootEl = ref<HTMLElement | null>(null)
const canvasEl = ref<HTMLElement | null>(null)
const rows = ref<HeatRow[]>([])
const loading = ref(false)
const error = ref('')
const canvasW = ref(0)
const canvasH = ref(0)
let loadSeq = 0
let refreshTimer: ReturnType<typeof setInterval> | null = null
let resizeObserver: ResizeObserver | null = null

interface TooltipState {
  x: number; y: number
  row: HeatRow
}
const tooltip = ref<TooltipState | null>(null)

// ── Derived config ────────────────────────────────────────────────────────────
const colorMetric = computed<string>(() => props.config.colorMetric ?? 'perf_1d')
const sizeMetric  = computed<string>(() => props.config.sizeMetric  ?? 'market_cap')
const groupBy     = computed<string>(() => props.config.groupBy     ?? 'sector')
const showAlertBadges = computed<boolean>(() => props.config.showAlertBadges !== false)

function setColorMetric(value: string) {
  emit('patchConfig', { colorMetric: value })
}

// ── Universe resolution ───────────────────────────────────────────────────────
async function resolveInstrumentIds(): Promise<number[]> {
  const type: string = props.config.universeType ?? 'watchlist'

  if (type === 'screener') {
    const scId = props.config.screenerId
    if (!scId) return []
    try {
      const results = await api.get<Array<{ matched_ids: number[] }>>(
        `/screeners/${scId}/results`,
        { limit: 1 },
      )
      return results[0]?.matched_ids ?? []
    } catch {
      return []
    }
  }

  // watchlist (default)
  if (!watchlistStore.watchlists.length) await watchlistStore.loadWatchlists()
  const wlId = Number(props.config.watchlistId) || null
  const wl: Watchlist | undefined =
    (wlId ? watchlistStore.watchlists.find(w => w.id === wlId) : null)
    ?? watchlistStore.watchlists[0]
  return wl?.items.map(i => i.instrument_id).filter(Boolean) ?? []
}

// ── Data loading ──────────────────────────────────────────────────────────────
async function load() {
  const seq = ++loadSeq
  loading.value = true
  error.value = ''

  try {
    const ids = await resolveInstrumentIds()
    if (seq !== loadSeq) return
    if (!ids.length) { rows.value = []; return }

    const data = await api.post<HeatRow[]>('/instruments/heatmap-data', {
      instrument_ids: ids,
    })
    if (seq !== loadSeq) return

    // Apply live 1D price from watchlistStore if available and metric is perf_1d
    const symbols = data.map(r => r.symbol).filter(Boolean)
    if (symbols.length) await watchlistStore.fetchPrices(symbols, false)

    for (const row of data) {
      const live = watchlistStore.priceMap[row.symbol]
      if (live) {
        row.current_price = live.close
        row.perf_1d = live.pct
      }
    }

    rows.value = data
  } catch (e: any) {
    if (seq === loadSeq) {
      error.value = e?.message ?? 'Heat map unavailable'
      rows.value = []
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

// ── Layout: squarify treemap ──────────────────────────────────────────────────
interface SquarifyRect { x: number; y: number; w: number; h: number }
interface SquarifyItem { value: number; index: number }

function squarify(
  items: SquarifyItem[],
  rect: SquarifyRect,
): Array<SquarifyRect & { index: number }> {
  if (!items.length) return []

  const totalValue = items.reduce((s, i) => s + i.value, 0)
  if (totalValue <= 0 || rect.w <= 0 || rect.h <= 0) return []

  const results: Array<SquarifyRect & { index: number }> = []
  _squarifyRecurse(items, rect, totalValue, results)
  return results
}

function _worstAspect(row: SquarifyItem[], length: number, totalArea: number): number {
  const rowSum = row.reduce((s, i) => s + i.value, 0)
  if (rowSum === 0 || length === 0) return Infinity
  const rowArea = (rowSum / totalArea) * totalArea
  let worst = 0
  for (const item of row) {
    const area = (item.value / totalArea) * totalArea
    const w = (rowArea / length) || 1
    const h = area / w || 1
    const aspect = Math.max(w / h, h / w)
    if (aspect > worst) worst = aspect
  }
  return worst
}

function _squarifyRecurse(
  items: SquarifyItem[],
  rect: SquarifyRect,
  totalValue: number,
  out: Array<SquarifyRect & { index: number }>,
) {
  if (!items.length) return
  if (items.length === 1) {
    out.push({ ...rect, index: items[0].index })
    return
  }

  const sorted = [...items].sort((a, b) => b.value - a.value)
  const totalArea = rect.w * rect.h
  const isHoriz = rect.w >= rect.h
  const length = isHoriz ? rect.h : rect.w

  let row: SquarifyItem[] = []
  let i = 0

  while (i < sorted.length) {
    const candidate = sorted[i]
    const next = [...row, candidate]
    const scaledItems = next.map(it => ({
      ...it,
      value: (it.value / totalValue) * totalArea,
    }))

    if (row.length > 0 && _worstAspect(scaledItems, length, totalArea) > _worstAspect(
      row.map(it => ({ ...it, value: (it.value / totalValue) * totalArea })),
      length,
      totalArea,
    )) {
      break
    }

    row = next
    i++
  }

  // Flush current row
  const rowSum = row.reduce((s, it) => s + it.value, 0)
  const rowFraction = rowSum / totalValue
  let cursor = 0

  for (const it of row) {
    const fraction = rowSum > 0 ? it.value / rowSum : 1 / row.length
    if (isHoriz) {
      const tileW = rowFraction * rect.w
      out.push({
        x: rect.x,
        y: rect.y + cursor,
        w: tileW,
        h: fraction * rect.h,
        index: it.index,
      })
      cursor += fraction * rect.h
    } else {
      const tileH = rowFraction * rect.h
      out.push({
        x: rect.x + cursor,
        y: rect.y,
        w: fraction * rect.w,
        h: tileH,
        index: it.index,
      })
      cursor += fraction * rect.w
    }
  }

  // Recurse with remaining items in remaining rect
  const remaining = sorted.slice(i)
  if (!remaining.length) return

  const remainFraction = 1 - rowFraction
  const nextRect: SquarifyRect = isHoriz
    ? { x: rect.x + rowFraction * rect.w, y: rect.y, w: remainFraction * rect.w, h: rect.h }
    : { x: rect.x, y: rect.y + rowFraction * rect.h, w: rect.w, h: remainFraction * rect.h }

  const remainValue = remaining.reduce((s, it) => s + it.value, 0)
  _squarifyRecurse(remaining, nextRect, remainValue, out)
}

// ── Metric value extraction ───────────────────────────────────────────────────
function getMetricValue(row: HeatRow, metric: string): number | null {
  return (row as any)[metric] ?? null
}

function getSizeWeight(row: HeatRow): number {
  const sm = sizeMetric.value
  if (sm === 'equal') return 1
  if (sm === 'avg_volume_30d') return Math.max(1, row.avg_volume_30d ?? 1)
  // market_cap (default)
  return Math.max(1, row.market_cap ?? 1)
}

// ── Computed layout ───────────────────────────────────────────────────────────
const layout = computed<{ tiles: Tile[]; groups: GroupLabel[] }>(() => {
  if (!rows.value.length || canvasW.value <= 0 || canvasH.value <= 0) {
    return { tiles: [], groups: [] }
  }

  const W = canvasW.value
  const H = canvasH.value
  const GROUP_HEADER = 18 // px reserved for group label
  const PADDING = 2

  if (groupBy.value === 'none') {
    return buildTiles(rows.value, { x: 0, y: 0, w: W, h: H }, PADDING)
  }

  // Group rows
  const groupKey = (row: HeatRow) =>
    groupBy.value === 'industry' ? (row.industry ?? 'Unclassified') : (row.sector ?? 'Unclassified')

  const groupMap = new Map<string, HeatRow[]>()
  for (const row of rows.value) {
    const key = groupKey(row)
    if (!groupMap.has(key)) groupMap.set(key, [])
    groupMap.get(key)!.push(row)
  }

  // Sort groups by total size weight, descending
  const groups = [...groupMap.entries()]
    .map(([key, groupRows]) => ({
      key,
      rows: groupRows,
      totalWeight: groupRows.reduce((s, r) => s + getSizeWeight(r), 0),
    }))
    .sort((a, b) => b.totalWeight - a.totalWeight)

  // Lay out groups themselves as a treemap
  const groupItems: SquarifyItem[] = groups.map((g, i) => ({ value: g.totalWeight, index: i }))
  const groupRects = squarify(groupItems, { x: 0, y: 0, w: W, h: H })

  const tiles: Tile[] = []
  const groupLabels: GroupLabel[] = []

  for (const gr of groupRects) {
    const group = groups[gr.index]
    // Reserve header row for label
    const innerRect = {
      x: gr.x + PADDING,
      y: gr.y + PADDING + GROUP_HEADER,
      w: gr.w - PADDING * 2,
      h: gr.h - PADDING * 2 - GROUP_HEADER,
    }
    groupLabels.push({ key: group.key, x: gr.x + PADDING, y: gr.y + PADDING, w: gr.w - PADDING * 2 })

    const { tiles: innerTiles } = buildTiles(group.rows, innerRect, PADDING)
    tiles.push(...innerTiles)
  }

  return { tiles, groups: groupLabels }
})

function buildTiles(
  rowSet: HeatRow[],
  rect: SquarifyRect,
  padding: number,
): { tiles: Tile[]; groups: GroupLabel[] } {
  const items: SquarifyItem[] = rowSet.map((r, i) => ({
    value: getSizeWeight(r),
    index: i,
  }))

  const rects = squarify(items, rect)
  const tiles: Tile[] = rects.map(r => {
    const row = rowSet[r.index]
    const mv = getMetricValue(row, colorMetric.value)
    return {
      symbol: row.symbol,
      name: row.name,
      x: r.x + padding,
      y: r.y + padding,
      w: Math.max(0, r.w - padding * 2),
      h: Math.max(0, r.h - padding * 2),
      metricValue: mv,
      sparkline: row.sparkline,
      alertCount: showAlertBadges.value
        ? alertsStore.activeCountForInstrument(row.instrument_id)
        : 0,
      row,
    }
  })
  return { tiles, groups: [] }
}

// ── Color scale ───────────────────────────────────────────────────────────────
function tileColor(value: number | null, metric: string): string {
  if (value === null) return 'rgba(40,40,44,0.9)'

  if (metric === 'rsi_14') {
    // RSI: green = oversold (<30), red = overbought (>70), grey = neutral
    if (value <= 30) {
      const intensity = 0.3 + 0.5 * (1 - value / 30)
      return `rgba(38,166,154,${intensity.toFixed(2)})`
    }
    if (value >= 70) {
      const intensity = 0.3 + 0.5 * ((value - 70) / 30)
      return `rgba(239,83,80,${intensity.toFixed(2)})`
    }
    return 'rgba(55,55,60,0.9)'
  }

  if (metric === 'rel_volume') {
    // rel_volume: > 2 is high, < 0.5 is low
    const clamped = Math.max(0, Math.min(4, value))
    const intensity = 0.15 + 0.7 * (clamped / 4)
    if (value >= 1) return `rgba(100,181,246,${intensity.toFixed(2)})`  // blue for high vol
    return `rgba(55,55,60,0.9)`
  }

  if (metric === 'dist_52w_high') {
    // negative = below high (normal), near 0 = near high (bullish)
    const clamped = Math.max(-0.5, Math.min(0, value))
    const intensity = 0.2 + 0.7 * (1 + clamped / 0.5)
    return `rgba(38,166,154,${intensity.toFixed(2)})`
  }

  if (metric === 'dist_52w_low') {
    // positive = above low, large positive = far from low (bullish)
    const clamped = Math.max(0, Math.min(2, value))
    const intensity = 0.2 + 0.7 * (clamped / 2)
    return `rgba(38,166,154,${intensity.toFixed(2)})`
  }

  // Performance metrics (perf_*): symmetric green/red around 0
  const cap = metric === 'perf_1y' ? 0.5 : metric.startsWith('perf_1') || metric === 'perf_ytd' || metric === 'perf_mtd' ? 0.15 : 0.05
  const intensity = Math.min(0.85, Math.max(0.18, Math.abs(value) / cap * 0.67 + 0.18))
  return value >= 0
    ? `rgba(38,166,154,${intensity.toFixed(2)})`
    : `rgba(239,83,80,${intensity.toFixed(2)})`
}

function tileStyle(tile: Tile): Record<string, string> {
  return {
    left:       `${tile.x}px`,
    top:        `${tile.y}px`,
    width:      `${tile.w}px`,
    height:     `${tile.h}px`,
    background: tileColor(tile.metricValue, colorMetric.value),
  }
}

// ── Sparkline helpers ─────────────────────────────────────────────────────────
function sparkPoints(data: number[]): string {
  const h = 20
  return data
    .map((v, i) => `${i},${((1 - v) * (h - 2) + 1).toFixed(1)}`)
    .join(' ')
}

// ── Metric formatting ─────────────────────────────────────────────────────────
function formatMetricValue(value: number | null): string {
  if (value === null) return '—'
  const cm = colorMetric.value
  if (cm === 'rsi_14') return value.toFixed(1)
  if (cm === 'rel_volume') return `${value.toFixed(1)}x`
  if (cm === 'dist_52w_high' || cm === 'dist_52w_low') {
    return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
  }
  // performance
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function fmtPct(v: number | null) {
  if (v === null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

function fmtNum(v: number | null, dec = 2) {
  if (v === null) return '—'
  return v.toFixed(dec)
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function onMouseMove(e: MouseEvent) {
  const canvas = canvasEl.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  // Find tile under cursor
  const hit = layout.value.tiles.find(t =>
    mx >= t.x && mx <= t.x + t.w && my >= t.y && my <= t.y + t.h,
  )
  if (!hit) { tooltip.value = null; return }

  // Position tooltip avoiding right edge
  const TW = 220
  const tx = mx + 12 + TW > canvasW.value ? mx - TW - 8 : mx + 12
  const ty = Math.max(0, Math.min(my - 10, canvasH.value - 200))
  tooltip.value = { x: tx, y: ty, row: hit.row }
}

function tooltipEntries(row: HeatRow) {
  const signed = (v: number | null) => ({
    value: fmtPct(v),
    cls: v === null ? '' : v >= 0 ? 'pos' : 'neg',
  })
  return [
    { label: 'Price',  ...{ value: row.current_price != null ? row.current_price.toFixed(2) : '—', cls: '' } },
    { label: '1D',     ...signed(row.perf_1d) },
    { label: '1W',     ...signed(row.perf_1w) },
    { label: '1M',     ...signed(row.perf_1m) },
    { label: 'MTD',    ...signed(row.perf_mtd) },
    { label: 'YTD',    ...signed(row.perf_ytd) },
    { label: '1Y',     ...signed(row.perf_1y) },
    { label: 'RSI',    ...{ value: fmtNum(row.rsi_14, 1), cls: '' } },
    { label: 'Rvol',   ...{ value: row.rel_volume != null ? `${row.rel_volume.toFixed(2)}x` : '—', cls: '' } },
    { label: '52H Δ',  ...signed(row.dist_52w_high) },
    { label: '52L Δ',  ...signed(row.dist_52w_low) },
  ]
}

// ── Resize observer ───────────────────────────────────────────────────────────
function measureCanvas() {
  const el = canvasEl.value ?? rootEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  canvasW.value = r.width
  canvasH.value = r.height
}

// ── Watchers / lifecycle ──────────────────────────────────────────────────────
watch(() => [props.config.universeType, props.config.watchlistId, props.config.screenerId], load)
watch(() => watchlistStore.priceMap, () => {
  // refresh live 1D pct values reactively
  if (!rows.value.length) return
  for (const row of rows.value) {
    const live = watchlistStore.priceMap[row.symbol]
    if (live) {
      row.current_price = live.close
      row.perf_1d = live.pct
    }
  }
}, { deep: false })

onMounted(() => {
  load()
  resizeObserver = new ResizeObserver(measureCanvas)
  const target = canvasEl.value ?? rootEl.value
  if (target) resizeObserver.observe(target)
  // auto-refresh every 5 min
  refreshTimer = setInterval(load, 5 * 60 * 1000)
})

// measure after layout renders (canvas may not exist until rows arrive)
watch(canvasEl, (el) => {
  if (el) {
    measureCanvas()
    resizeObserver?.disconnect()
    resizeObserver = new ResizeObserver(measureCanvas)
    resizeObserver.observe(el)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.heatmap-widget {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  font-family: 'JetBrains Mono', monospace;
}

/* ── Toolbar ── */
.hm-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  flex-shrink: 0;
  border-bottom: 1px solid #1e1e22;
  overflow-x: auto;
  scrollbar-width: none;
}
.hm-toolbar::-webkit-scrollbar { display: none; }
.hm-metric-pills {
  display: flex;
  gap: 3px;
  flex: 1;
  flex-wrap: nowrap;
}
.pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #333;
  background: #1a1a1e;
  color: #888;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.1s, color 0.1s;
}
.pill:hover  { background: #252528; color: #bbb; }
.pill.active { background: #2a2d32; color: #c8cfd8; border-color: #4a5568; }
.hm-refresh {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.hm-refresh.spinning { animation: spin 0.8s linear infinite; }

/* ── Canvas ── */
.hm-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── Group labels ── */
.hm-group-label {
  position: absolute;
  font-size: 9px;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  pointer-events: none;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  line-height: 18px;
}

/* ── Tiles ── */
.hm-tile {
  position: absolute;
  border: 1px solid rgba(0,0,0,0.35);
  border-radius: 3px;
  overflow: hidden;
  color: #f0f0f0;
  text-decoration: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  cursor: pointer;
  transition: filter 0.1s;
}
.hm-tile:hover { filter: brightness(1.25); z-index: 1; }

.hm-alert-badge {
  position: absolute;
  top: 2px;
  right: 3px;
  font-size: 8px;
  background: #e53935;
  color: #fff;
  border-radius: 8px;
  padding: 0 3px;
  line-height: 13px;
  pointer-events: none;
}

.hm-sym {
  font-size: 11px;
  font-weight: 700;
  line-height: 1.1;
  text-align: center;
}
.hm-val {
  font-size: 9px;
  line-height: 1.1;
  color: rgba(255,255,255,0.8);
}
.hm-spark {
  width: 80%;
  height: 20px;
  overflow: visible;
}

/* ── Tooltip ── */
.hm-tooltip {
  position: absolute;
  z-index: 100;
  background: #18181c;
  border: 1px solid #333;
  border-radius: 5px;
  padding: 8px 10px;
  pointer-events: none;
  min-width: 180px;
  max-width: 220px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
}
.tt-header {
  display: flex;
  flex-direction: column;
  margin-bottom: 6px;
  border-bottom: 1px solid #2a2a2e;
  padding-bottom: 5px;
}
.tt-header strong { font-size: 12px; color: #e0e0e0; }
.tt-name { font-size: 9px; color: #666; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tt-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 8px;
}
.tt-label { font-size: 9px; color: #666; }
.tt-val   { font-size: 9px; color: #aaa; text-align: right; }
.tt-val.pos { color: #26a69a; }
.tt-val.neg { color: #ef5350; }

/* ── States ── */
.widget-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: #444;
}
.widget-state.error  { color: #ef5350; font-size: 10px; }
.widget-state.muted  { color: #444; }
</style>
