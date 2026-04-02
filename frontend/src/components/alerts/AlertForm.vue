<template>
  <div class="alert-form">
    <div class="form-header">
      <span class="form-title">{{ isEditing ? 'Edit Alert' : 'New Alert' }} — {{ symbol }}</span>
      <button class="form-close" @click="$emit('close')">✕</button>
    </div>

    <!-- Live preview of what the alert will say -->
    <div class="alert-preview">{{ preview }}</div>

    <!-- ── LHS ──────────────────────────────────────────────── -->
    <div class="expr-section">
      <div class="expr-label">When</div>
      <div class="expr-row">
        <select v-model="lhs.sourceType" class="form-select" @change="onLhsTypeChange">
          <optgroup label="Price">
            <option value="close">Close</option>
            <option value="open">Open</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </optgroup>
          <optgroup label="Active indicators" v-if="activeIndicators.length">
            <option v-for="ind in activeIndicators" :key="ind.key" :value="ind.key">
              {{ ind.label }}
            </option>
          </optgroup>
          <optgroup label="Add indicator">
            <option v-for="t in allIndicatorTypes" :key="'add_'+t.value" :value="'new_'+t.value">
              + {{ t.label }}
            </option>
          </optgroup>
        </select>
      </div>

      <!-- Params for LHS if it's a non-active indicator -->
      <template v-if="lhs.isCustomIndicator">
        <div class="param-row" v-for="(_, key) in lhsDefaultParams" :key="key">
          <label>{{ paramLabel(key) }}</label>
          <input v-if="String(key) !== 'anchorTime'" v-model.number="lhs.params[key]" type="number" min="1" class="form-input form-input--sm" />
          <input v-else type="datetime-local" :value="tsToDateInput(lhs.params.anchorTime as number)"
                 @input="e => lhs.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                 class="form-input" />
        </div>
      </template>
      <!-- Timeframe shown for any indicator source (active or new) -->
      <div class="param-row" v-if="lhs.isCustomIndicator || lhs.sourceType.startsWith('active_')">
        <label>Timeframe</label>
        <select v-model="lhs.timeframe" class="form-select">
          <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
        </select>
      </div>
    </div>

    <!-- ── Condition ─────────────────────────────────────────── -->
    <div class="expr-section">
      <div class="expr-label">Condition</div>
      <div class="cond-grid">
        <button
          v-for="c in conditions"
          :key="c.value"
          :class="['cond-btn', { active: condition === c.value }]"
          @click="condition = c.value"
        >{{ c.label }}</button>
      </div>
      <div class="param-row" v-if="condition === 'within_percent'">
        <label>Within %</label>
        <input v-model.number="withinPct" type="number" min="0.01" step="0.1" class="form-input form-input--sm" />
        <span class="param-unit">%</span>
      </div>
    </div>

    <!-- ── RHS ──────────────────────────────────────────────── -->
    <div class="expr-section">
      <div class="expr-label">Target</div>
      <div class="expr-row">
        <select v-model="rhs.sourceType" class="form-select" @change="onRhsTypeChange">
          <option value="value">Fixed value</option>
          <optgroup label="Price">
            <option value="close">Close</option>
            <option value="open">Open</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </optgroup>
          <optgroup label="Active indicators" v-if="activeIndicators.length">
            <option v-for="ind in activeIndicators" :key="ind.key" :value="ind.key">
              {{ ind.label }}
            </option>
          </optgroup>
          <optgroup label="Add indicator">
            <option v-for="t in allIndicatorTypes" :key="'add_'+t.value" :value="'new_'+t.value">
              + {{ t.label }}
            </option>
          </optgroup>
        </select>
      </div>

      <!-- Fixed value input -->
      <div class="param-row" v-if="rhs.sourceType === 'value'">
        <input v-model.number="rhs.fixedValue" type="number" step="0.0001" class="form-input"
               placeholder="0.0000" />
      </div>

      <!-- Params for RHS if it's a non-active indicator -->
      <template v-if="rhs.isCustomIndicator">
        <div class="param-row" v-for="(_, key) in rhsDefaultParams" :key="key">
          <label>{{ paramLabel(key) }}</label>
          <input v-if="String(key) !== 'anchorTime'" v-model.number="rhs.params[key]" type="number" min="1" class="form-input form-input--sm" />
          <input v-else type="datetime-local" :value="tsToDateInput(rhs.params.anchorTime as number)"
                 @input="e => rhs.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                 class="form-input" />
        </div>
      </template>
      <!-- Timeframe shown for any indicator source (active or new) -->
      <div class="param-row" v-if="rhs.isCustomIndicator || rhs.sourceType.startsWith('active_')">
        <label>Timeframe</label>
        <select v-model="rhs.timeframe" class="form-select">
          <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
        </select>
      </div>
    </div>

    <!-- ── Options ───────────────────────────────────────────── -->
    <div class="expr-section">
      <div class="form-row-check">
        <input type="checkbox" v-model="repeat" id="repeat-check" />
        <label for="repeat-check">Repeat after trigger</label>
      </div>
      <div class="param-row" style="margin-top:8px">
        <label>Notes</label>
        <input v-model="notes" type="text" class="form-input" placeholder="Optional…" />
      </div>
    </div>

    <div class="form-actions">
      <button class="btn-cancel" @click="$emit('close')">Cancel</button>
      <button class="btn-create" :disabled="!isValid" @click="submit">{{ isEditing ? 'Save Alert' : 'Create Alert' }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import { useChartStore } from '@/stores/chart'
import type { Timeframe, IndicatorConfig, PriceAlert, IndicatorAlert } from '@/types'

const props = defineProps<{
  instrumentId: number
  symbol: string
  currentTf?: Timeframe
  // Pre-seed from clicking 🔔 on an indicator in the sidebar
  seedIndicator?: IndicatorConfig | null
  // Pre-populate form for editing an existing alert
  editPriceAlert?: PriceAlert | null
  editIndicatorAlert?: IndicatorAlert | null
}>()
const emit = defineEmits<{ close: [] }>()

const isEditing = computed(() => !!(props.editPriceAlert || props.editIndicatorAlert))

const alertsStore = useAlertsStore()
const chartStore  = useChartStore()

// ── Timeframes ────────────────────────────────────────────────────────────────
const timeframes: Timeframe[] = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN']

// ── Indicator type catalogue ──────────────────────────────────────────────────
const allIndicatorTypes = [
  { value: 'sma',   label: 'SMA'   },
  { value: 'ema',   label: 'EMA'   },
  { value: 'rsi',   label: 'RSI'   },
  { value: 'vwap',  label: 'VWAP'  },
  { value: 'avwap', label: 'AVWAP' },
  { value: 'macd',  label: 'MACD'  },
  { value: 'bb',    label: 'Bollinger Bands' },
]

const DEFAULT_PARAMS: Record<string, Record<string, number>> = {
  sma:   { period: 20 },
  ema:   { period: 50 },
  rsi:   { period: 14 },
  vwap:  {},
  avwap: { anchorTime: Math.floor(Date.now() / 1000) - 86400 * 30 },
  macd:  { fast: 12, slow: 26, signal: 9 },
  bb:    { period: 20, stdDev: 2 },
}

// ── Active indicators on the chart (for quick selection) ──────────────────────
const activeIndicators = computed(() =>
  chartStore.indicators
    .filter(i => i.type !== 'volume')
    .map(i => {
      const params = Object.entries(i.params)
        .filter(([k]) => k !== 'anchorTime')
        .map(([, v]) => v)
        .join(',')
      const label = i.type === 'avwap' && i.params.anchorTime
        ? `AVWAP(${new Date((i.params.anchorTime as number)*1000).toLocaleDateString()})`
        : `${i.type.toUpperCase()}${params ? `(${params})` : ''}`
      return { key: `active_${i.type}_${JSON.stringify(i.params)}`, label, config: i }
    })
)

// ── Source descriptor ─────────────────────────────────────────────────────────
interface Source {
  sourceType: string   // 'value' | 'close'|'open'|'high'|'low' | 'active_*' | 'new_*'
  fixedValue: number
  params: Record<string, number>
  timeframe: Timeframe
  isCustomIndicator: boolean
}

function makeSource(tf: Timeframe): Source {
  return { sourceType: 'close', fixedValue: 0, params: {}, timeframe: tf, isCustomIndicator: false }
}

const defaultTf = props.currentTf ?? 'D1'
const lhs = reactive<Source>(makeSource(defaultTf))
const rhs = reactive<Source>(makeSource(defaultTf))
rhs.sourceType = 'value'

// Pre-seed from indicator sidebar button
if (props.seedIndicator) {
  lhs.sourceType = `active_${props.seedIndicator.type}_${JSON.stringify(props.seedIndicator.params)}`
  rhs.sourceType = 'close'
}

function onLhsTypeChange() { updateIsCustom(lhs) }
function onRhsTypeChange() { updateIsCustom(rhs) }

function updateIsCustom(s: Source) {
  s.isCustomIndicator = s.sourceType.startsWith('new_')
  if (s.isCustomIndicator) {
    const type = s.sourceType.replace('new_', '')
    s.params = { ...(DEFAULT_PARAMS[type] ?? {}) }
  }
}

const lhsDefaultParams = computed(() => DEFAULT_PARAMS[lhs.sourceType.replace('new_', '')] ?? {})
const rhsDefaultParams = computed(() => DEFAULT_PARAMS[rhs.sourceType.replace('new_', '')] ?? {})

// ── Conditions ────────────────────────────────────────────────────────────────
const conditions = [
  { value: 'crosses_above', label: '↑ Crosses above' },
  { value: 'crosses_below', label: '↓ Crosses below' },
  { value: 'touches',       label: '⟷ Touches'       },
  { value: 'gt',            label: '> Greater than'  },
  { value: 'lt',            label: '< Less than'     },
  { value: 'gte',           label: '≥ Greater/equal' },
  { value: 'lte',           label: '≤ Less/equal'    },
  { value: 'within_percent', label: '% Within %'     },
]

const condition  = ref('crosses_above')
const withinPct  = ref(1)
const repeat     = ref(false)
const notes      = ref('')

// ── Pre-populate for editing ──────────────────────────────────────────────────
const PRICE_FIELDS_SET = new Set(['close','open','high','low'])

if (props.editPriceAlert) {
  const a = props.editPriceAlert
  lhs.sourceType = (a as any).price_field ?? 'close'
  lhs.isCustomIndicator = false
  rhs.sourceType = 'value'
  rhs.fixedValue = Number(a.threshold_price)
  condition.value = a.condition as string
  if (a.condition === 'within_percent') withinPct.value = Number((a as any).within_percent ?? 1)
  repeat.value = a.repeat
  notes.value = a.notes ?? ''
} else if (props.editIndicatorAlert) {
  const a = props.editIndicatorAlert
  // LHS
  if (PRICE_FIELDS_SET.has(a.indicator_a_type)) {
    lhs.sourceType = a.indicator_a_type
    lhs.isCustomIndicator = false
  } else {
    lhs.sourceType = `new_${a.indicator_a_type}`
    lhs.params = { ...(a.indicator_a_params as Record<string, number>) }
    lhs.isCustomIndicator = true
  }
  lhs.timeframe = a.timeframe as Timeframe
  // RHS
  if (a.indicator_b_type) {
    if (PRICE_FIELDS_SET.has(a.indicator_b_type)) {
      rhs.sourceType = a.indicator_b_type
      rhs.isCustomIndicator = false
    } else {
      rhs.sourceType = `new_${a.indicator_b_type}`
      rhs.params = { ...(a.indicator_b_params as Record<string, number>) }
      rhs.isCustomIndicator = true
    }
  } else {
    rhs.sourceType = 'value'
    rhs.fixedValue = Number(a.threshold_value ?? 0)
  }
  condition.value = a.condition
  if (a.condition === 'within_percent') withinPct.value = Number(a.threshold_value ?? 1)
  repeat.value = a.repeat
  notes.value = a.notes ?? ''
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function sourceLabel(s: Source): string {
  if (s.sourceType === 'value') return String(s.fixedValue)
  if (['close','open','high','low'].includes(s.sourceType)) return s.sourceType.toUpperCase()
  if (s.sourceType.startsWith('active_')) {
    const found = activeIndicators.value.find(i => i.key === s.sourceType)
    return found?.label ?? s.sourceType
  }
  if (s.sourceType.startsWith('new_')) {
    const type = s.sourceType.replace('new_', '')
    if (type === 'avwap' && s.params.anchorTime) {
      return `AVWAP(${tsToDateInput(s.params.anchorTime as number).split('T')[0]})`
    }
    const p = Object.values(s.params).join(',')
    return p ? `${type.toUpperCase()}(${p})` : type.toUpperCase()
  }
  return s.sourceType
}

const preview = computed(() => {
  const l = sourceLabel(lhs)
  const r = sourceLabel(rhs)
  const c = condition.value === 'within_percent'
    ? `within ${withinPct.value}% of`
    : conditions.find(c => c.value === condition.value)?.label.replace(/^[↑↓⟷><≥≤%]\s+/,'') ?? condition.value
  const isIndicator = lhs.isCustomIndicator || lhs.sourceType.startsWith('active_') ||
                      rhs.isCustomIndicator  || rhs.sourceType.startsWith('active_')
  const tf = isIndicator ? ` · ${lhs.isCustomIndicator || lhs.sourceType.startsWith('active_') ? lhs.timeframe : rhs.timeframe}` : ''
  return `${props.symbol}: ${l} ${c} ${r}${tf}`
})

function paramLabel(key: string): string {
  const m: Record<string, string> = { period: 'Period', fast: 'Fast', slow: 'Slow', signal: 'Signal', stdDev: 'Std dev', anchorTime: 'Anchor' }
  return m[key] ?? key
}

function tsToDateInput(ts: number | undefined): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2,'0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
function dateInputToTs(val: string): number {
  return Math.floor(new Date(val).getTime() / 1000)
}

// ── Resolve a source to API params ────────────────────────────────────────────
type PriceField = 'open' | 'high' | 'low' | 'close'
const PRICE_FIELDS: PriceField[] = ['open','high','low','close']

function resolveSource(s: Source): {
  isPriceField: boolean
  priceField?: PriceField
  isFixedValue: boolean
  fixedValue?: number
  isIndicator: boolean
  indicatorType?: string
  indicatorParams?: Record<string, unknown>
  indicatorTf?: Timeframe
} {
  if (s.sourceType === 'value') {
    return { isPriceField: false, isFixedValue: true, fixedValue: s.fixedValue, isIndicator: false }
  }
  if (PRICE_FIELDS.includes(s.sourceType as PriceField)) {
    return { isPriceField: true, priceField: s.sourceType as PriceField, isFixedValue: false, isIndicator: false }
  }
  if (s.sourceType.startsWith('active_')) {
    const found = activeIndicators.value.find(i => i.key === s.sourceType)
    if (found) {
      return { isPriceField: false, isFixedValue: false, isIndicator: true,
        indicatorType: found.config.type, indicatorParams: { ...found.config.params },
        indicatorTf: s.timeframe }
    }
  }
  if (s.sourceType.startsWith('new_')) {
    return { isPriceField: false, isFixedValue: false, isIndicator: true,
      indicatorType: s.sourceType.replace('new_',''), indicatorParams: { ...s.params },
      indicatorTf: s.timeframe }
  }
  return { isPriceField: false, isFixedValue: false, isIndicator: false }
}

// ── Validation ────────────────────────────────────────────────────────────────
const isValid = computed(() => {
  if (rhs.sourceType === 'value' && !rhs.fixedValue) return false
  if (condition.value === 'within_percent' && withinPct.value <= 0) return false
  return true
})

// ── Determine if this is a price alert or indicator alert ─────────────────────
// Price alert: both sides resolve to price fields or fixed values
// Indicator alert: at least one side is an indicator
function isPriceAlert(): boolean {
  const l = resolveSource(lhs)
  const r = resolveSource(rhs)
  return !l.isIndicator && !r.isIndicator
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function submit() {
  const l = resolveSource(lhs)
  const r = resolveSource(rhs)

  if (isPriceAlert()) {
    // Map to a price alert — LHS must be a price field, RHS must be a fixed value
    // (price field vs price field is also supported as an indicator alert)
    const priceField = l.priceField ?? 'close'
    const threshold = r.fixedValue ?? 0

    // within_percent is its own condition on price alerts
    if (condition.value === 'within_percent') {
      await alertsStore.createAlert(
        props.instrumentId,
        'within_percent' as any,
        threshold,
        repeat.value,
        notes.value || undefined,
        priceField,
        withinPct.value,
      )
    } else {
      await alertsStore.createAlert(
        props.instrumentId,
        condition.value as any,
        threshold,
        repeat.value,
        notes.value || undefined,
        priceField,
      )
    }
  } else {
    // Indicator alert
    // LHS must be an indicator or price field (price field = use type 'close' etc.)
    const indAType = l.isIndicator ? l.indicatorType! : (l.priceField ?? 'close')
    const indAParams = l.isIndicator ? (l.indicatorParams ?? {}) : {}
    const tf = l.indicatorTf ?? r.indicatorTf ?? defaultTf

    const body: any = {
      instrument_id:      props.instrumentId,
      timeframe:          tf,
      indicator_a_type:   indAType,
      indicator_a_params: indAParams,
      condition:          condition.value,
      repeat:             repeat.value,
      notes:              notes.value || undefined,
    }

    if (condition.value === 'within_percent') {
      body.threshold_value = r.fixedValue ?? 0
      body.within_percent  = withinPct.value
    } else if (r.isIndicator) {
      body.indicator_b_type   = r.indicatorType
      body.indicator_b_params = r.indicatorParams ?? {}
    } else if (r.isPriceField) {
      body.indicator_b_type   = r.priceField  // backend handles close/open/high/low as valid types
      body.indicator_b_params = {}
    } else {
      body.threshold_value = r.fixedValue ?? 0
    }

    await alertsStore.createIndicatorAlert(body)
  }

  // If editing, delete the original now that the replacement was created successfully
  if (props.editPriceAlert) {
    await alertsStore.deleteAlert(props.editPriceAlert.id)
  } else if (props.editIndicatorAlert) {
    await alertsStore.deleteIndicatorAlert(props.editIndicatorAlert.id)
  }

  emit('close')
}
</script>

<style scoped>
.alert-form {
  background: #111;
  border: 1px solid #333;
  border-radius: 6px;
  width: 320px;
  font-size: 12px;
  color: #aaa;
  max-height: 85vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px 8px;
  border-bottom: 1px solid #1a1a1a;
}
.form-title { color: #64b5f6; font-size: 13px; font-weight: 600; }
.form-close  { background: none; border: none; color: #555; cursor: pointer; font-size: 14px; }
.form-close:hover { color: #aaa; }

.alert-preview {
  background: #0a0a0a;
  border-bottom: 1px solid #1a1a1a;
  padding: 7px 14px;
  font-family: monospace;
  font-size: 11px;
  color: #26a69a;
  min-height: 28px;
}

.expr-section {
  padding: 10px 14px;
  border-bottom: 1px solid #1a1a1a;
}

.expr-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #444;
  margin-bottom: 6px;
}

.expr-row { display: flex; gap: 6px; }

.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.param-row label { color: #555; min-width: 60px; font-size: 11px; }
.param-unit { color: #555; font-size: 11px; }

.cond-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}
.cond-btn {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  color: #666;
  border-radius: 3px;
  padding: 5px 6px;
  cursor: pointer;
  font-size: 10px;
  font-family: monospace;
  text-align: left;
  transition: all 0.1s;
}
.cond-btn:hover { border-color: #444; color: #aaa; }
.cond-btn.active { background: #1a3a5c; border-color: #64b5f6; color: #64b5f6; }

.form-select, .form-input {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #ccc;
  border-radius: 3px;
  padding: 5px 8px;
  font-size: 12px;
  width: 100%;
}
.form-input--sm { width: 70px; }

.form-row-check {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 11px;
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 10px 14px;
}

.btn-cancel {
  background: none; border: 1px solid #444;
  color: #777; border-radius: 3px; padding: 4px 12px; cursor: pointer;
}

.btn-create {
  background: #1a3a5c; border: 1px solid #64b5f6;
  color: #64b5f6; border-radius: 3px; padding: 4px 12px; cursor: pointer;
}

.btn-create:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
