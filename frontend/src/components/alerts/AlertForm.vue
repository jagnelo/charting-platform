<template>
  <div class="alert-form">
    <h4 class="form-title">New Alert — {{ symbol }}</h4>

    <!-- Alert type tabs -->
    <div class="alert-tabs">
      <button :class="{ active: alertType === 'price' }" @click="alertType = 'price'">Price</button>
      <button :class="{ active: alertType === 'indicator' }" @click="alertType = 'indicator'">Indicator</button>
    </div>

    <!-- ── Price alert ──────────────────────────────────── -->
    <template v-if="alertType === 'price'">
      <div class="form-row">
        <label>Condition</label>
        <select v-model="price.condition" class="form-select">
          <option value="crosses_above">Crosses Above</option>
          <option value="crosses_below">Crosses Below</option>
          <option value="touches">Touches</option>
        </select>
      </div>
      <div class="form-row">
        <label>Price</label>
        <input v-model.number="price.threshold" type="number" step="0.0001" class="form-input" placeholder="0.0000" />
      </div>
    </template>

    <!-- ── Indicator alert ──────────────────────────────── -->
    <template v-else>
      <div class="form-row">
        <label>Timeframe</label>
        <select v-model="ind.timeframe" class="form-select">
          <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
        </select>
      </div>

      <!-- Indicator A -->
      <div class="form-section-label">Indicator</div>
      <div class="form-row">
        <label>Type</label>
        <select v-model="ind.indAType" class="form-select" @change="onIndATypeChange">
          <option v-for="t in indicatorTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </div>
      <div class="form-row" v-for="(val, key) in indAParamDefs" :key="key">
        <label>{{ paramLabel(key) }}</label>
        <input v-model.number="ind.indAParams[key]" type="number" min="1" class="form-input form-input--sm" />
      </div>

      <!-- Condition -->
      <div class="form-row">
        <label>Condition</label>
        <select v-model="ind.condition" class="form-select">
          <option value="crosses_above">Crosses Above</option>
          <option value="crosses_below">Crosses Below</option>
          <option value="gt">&gt; (greater than)</option>
          <option value="lt">&lt; (less than)</option>
          <option value="gte">≥ (greater or equal)</option>
          <option value="lte">≤ (less or equal)</option>
        </select>
      </div>

      <!-- Compare against: value or indicator B -->
      <div class="form-row">
        <label>Compare to</label>
        <select v-model="ind.compareMode" class="form-select">
          <option value="value">Fixed value</option>
          <option value="indicator">Another indicator</option>
        </select>
      </div>

      <div class="form-row" v-if="ind.compareMode === 'value'">
        <label>Value</label>
        <input v-model.number="ind.threshold" type="number" step="0.0001" class="form-input" />
      </div>

      <template v-else>
        <div class="form-section-label">Compare indicator</div>
        <div class="form-row">
          <label>Type</label>
          <select v-model="ind.indBType" class="form-select" @change="onIndBTypeChange">
            <option v-for="t in indicatorTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </div>
        <div class="form-row" v-for="(val, key) in indBParamDefs" :key="key">
          <label>{{ paramLabel(key) }}</label>
          <input v-model.number="ind.indBParams[key]" type="number" min="1" class="form-input form-input--sm" />
        </div>
      </template>

      <!-- Example hint -->
      <div class="alert-hint">{{ alertHint }}</div>
    </template>

    <!-- Shared fields -->
    <div class="form-row form-row-check">
      <label><input type="checkbox" v-model="shared.repeat" /> Repeat after trigger</label>
    </div>
    <div class="form-row">
      <label>Notes</label>
      <input v-model="shared.notes" type="text" class="form-input" placeholder="Optional note…" />
    </div>
    <div class="form-actions">
      <button class="btn-cancel" @click="$emit('close')">Cancel</button>
      <button class="btn-create" :disabled="!isValid" @click="submit">Create Alert</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import type { Timeframe } from '@/types'

const props = defineProps<{ instrumentId: number; symbol: string; currentTf?: Timeframe }>()
const emit  = defineEmits<{ close: [] }>()

const alertsStore = useAlertsStore()
const alertType = ref<'price' | 'indicator'>('price')

// ── Price alert state ──────────────────────────────────────────────────────────
const price = reactive({ condition: 'crosses_above' as string, threshold: 0 })

// ── Indicator alert state ─────────────────────────────────────────────────────
const timeframes: Timeframe[] = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN']

const indicatorTypes = [
  { value: 'sma',   label: 'SMA'   },
  { value: 'ema',   label: 'EMA'   },
  { value: 'rsi',   label: 'RSI'   },
  { value: 'vwap',  label: 'VWAP'  },
  { value: 'macd',  label: 'MACD'  },
  { value: 'bb',    label: 'Bollinger Bands' },
  { value: 'close', label: 'Close price' },
]

const DEFAULT_PARAMS: Record<string, Record<string, number>> = {
  sma:   { period: 20 },
  ema:   { period: 50 },
  rsi:   { period: 14 },
  vwap:  {},
  macd:  { fast: 12, slow: 26, signal: 9 },
  bb:    { period: 20, stdDev: 2 },
  close: {},
}

const ind = reactive({
  timeframe:   props.currentTf ?? 'D1' as Timeframe,
  indAType:    'rsi',
  indAParams:  { period: 14 } as Record<string, number>,
  condition:   'crosses_below',
  compareMode: 'value' as 'value' | 'indicator',
  threshold:   30,
  indBType:    'ema',
  indBParams:  { period: 200 } as Record<string, number>,
})

const indAParamDefs = computed(() => DEFAULT_PARAMS[ind.indAType] ?? {})
const indBParamDefs = computed(() => DEFAULT_PARAMS[ind.indBType] ?? {})

function onIndATypeChange() {
  ind.indAParams = { ...DEFAULT_PARAMS[ind.indAType] }
}
function onIndBTypeChange() {
  ind.indBParams = { ...DEFAULT_PARAMS[ind.indBType] }
}

const alertHint = computed(() => {
  const a = `${ind.indAType.toUpperCase()}(${Object.values(ind.indAParams).join(',')})`
  const cond = ind.condition.replace(/_/g, ' ')
  if (ind.compareMode === 'value') {
    return `Alert when ${a} ${cond} ${ind.threshold}`
  }
  const b = `${ind.indBType.toUpperCase()}(${Object.values(ind.indBParams).join(',')})`
  return `Alert when ${a} ${cond} ${b}`
})

// ── Shared ────────────────────────────────────────────────────────────────────
const shared = reactive({ repeat: false, notes: '' })

const isValid = computed(() => {
  if (alertType.value === 'price') return price.threshold > 0
  return true  // indicator alerts have sensible defaults
})

function paramLabel(key: string): string {
  const m: Record<string, string> = { period: 'Period', fast: 'Fast', slow: 'Slow', signal: 'Signal', stdDev: 'Std dev' }
  return m[key] ?? key
}

// ── Submit ────────────────────────────────────────────────────────────────────
async function submit() {
  if (alertType.value === 'price') {
    await alertsStore.createAlert(
      props.instrumentId,
      price.condition as any,
      price.threshold,
      shared.repeat,
      shared.notes || undefined,
    )
  } else {
    await alertsStore.createIndicatorAlert({
      instrument_id:      props.instrumentId,
      timeframe:          ind.timeframe,
      indicator_a_type:   ind.indAType,
      indicator_a_params: { ...ind.indAParams },
      condition:          ind.condition,
      threshold_value:    ind.compareMode === 'value' ? ind.threshold : undefined,
      indicator_b_type:   ind.compareMode === 'indicator' ? ind.indBType : undefined,
      indicator_b_params: ind.compareMode === 'indicator' ? { ...ind.indBParams } : undefined,
      repeat:             shared.repeat,
      notes:              shared.notes || undefined,
    })
  }
  emit('close')
}
</script>

<style scoped>
.alert-form {
  background: #111;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 16px;
  width: 300px;
  font-size: 12px;
  color: #aaa;
  max-height: 80vh;
  overflow-y: auto;
}

.form-title { color: #64b5f6; margin: 0 0 12px; font-size: 13px; }

.alert-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 14px;
  border: 1px solid #333;
  border-radius: 4px;
  overflow: hidden;
}
.alert-tabs button {
  flex: 1;
  background: none;
  border: none;
  color: #666;
  padding: 5px;
  cursor: pointer;
  font-size: 11px;
  font-family: monospace;
}
.alert-tabs button.active { background: #1a3a5c; color: #64b5f6; }

.form-section-label {
  font-size: 10px;
  text-transform: uppercase;
  color: #444;
  letter-spacing: 0.06em;
  margin: 10px 0 6px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.form-row-check { flex-direction: row; align-items: center; gap: 6px; }

.form-select, .form-input {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #ccc;
  border-radius: 3px;
  padding: 5px 8px;
  font-size: 12px;
}
.form-input--sm { max-width: 80px; }

.alert-hint {
  background: #0d0d0d;
  border: 1px solid #222;
  border-radius: 3px;
  padding: 6px 8px;
  font-size: 11px;
  color: #555;
  font-family: monospace;
  margin: 8px 0;
}

.form-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
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
