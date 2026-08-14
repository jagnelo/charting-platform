<template>
  <section class="alerts-tool" role="region" :aria-label="`${symbol} alerts`" :aria-busy="loading || busy">
    <form class="alerts-tool__create" aria-label="Create instrument alert" @submit.prevent="create">
      <label class="alerts-tool__kind">
        <span>Alert type</span>
        <select v-model="alertKind" :disabled="!instrumentId || busy" aria-label="Alert type">
          <option value="price">Price</option>
          <option value="indicator">Indicator</option>
        </select>
      </label>
      <label>
        <span>{{ alertKind === 'indicator' ? 'Indicator' : `${symbol} alert` }}</span>
        <select v-model="condition" :disabled="!instrumentId || busy" :aria-label="alertKind === 'indicator' ? 'Indicator condition' : 'Price condition'">
          <option v-for="option in conditionOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <label v-if="alertKind === 'indicator'" class="alerts-tool__indicator">
        <span>Study</span>
        <select v-model="indicatorType" :disabled="!instrumentId || busy" aria-label="Alert indicator">
          <option v-for="item in indicatorOptions" :key="item.type" :value="item.type">{{ item.label }}</option>
        </select>
      </label>
      <label v-if="alertKind === 'indicator'" class="alerts-tool__target">
        <span>Compare to</span>
        <select v-model="indicatorTarget" :disabled="!instrumentId || busy" aria-label="Indicator target">
          <option value="threshold">Value</option>
          <option value="indicator">Another study</option>
        </select>
      </label>
      <label v-if="alertKind === 'indicator' && indicatorTarget === 'indicator'" class="alerts-tool__indicator">
        <span>Study B</span>
        <select v-model="indicatorBType" :disabled="!instrumentId || busy" aria-label="Comparison indicator">
          <option v-for="item in indicatorOptions" :key="item.type" :value="item.type">{{ item.label }}</option>
        </select>
      </label>
      <label v-if="alertKind === 'indicator'" class="alerts-tool__timeframe">
        <span>Timeframe</span>
        <select v-model="alertTimeframe" :disabled="!instrumentId || busy" aria-label="Alert timeframe">
          <option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </label>
      <template v-if="alertKind === 'indicator'">
        <label v-for="param in selectedIndicator?.params ?? []" :key="param.key" class="alerts-tool__parameter">
          <span>{{ param.label }}</span>
          <select v-if="param.input === 'select'" v-model="indicatorParams[param.key]" :disabled="!instrumentId || busy" :aria-label="`Alert ${param.label}`">
            <option v-for="option in param.options ?? []" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
          <input v-else v-model="indicatorParams[param.key]" :disabled="!instrumentId || busy" :type="param.input === 'datetime' ? 'date' : 'number'" :step="param.input === 'datetime' ? undefined : 'any'" :aria-label="`Alert ${param.label}`" />
        </label>
      </template>
      <template v-if="alertKind === 'indicator' && indicatorTarget === 'indicator'">
        <label v-for="param in selectedIndicatorB?.params ?? []" :key="`b-${param.key}`" class="alerts-tool__parameter">
          <span>B {{ param.label }}</span>
          <select v-if="param.input === 'select'" v-model="indicatorBParams[param.key]" :disabled="!instrumentId || busy" :aria-label="`Alert comparison ${param.label}`">
            <option v-for="option in param.options ?? []" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
          <input v-else v-model="indicatorBParams[param.key]" :disabled="!instrumentId || busy" :type="param.input === 'datetime' ? 'date' : 'number'" :step="param.input === 'datetime' ? undefined : 'any'" :aria-label="`Alert comparison ${param.label}`" />
        </label>
      </template>
      <input v-if="alertKind === 'price' || indicatorTarget === 'threshold'" v-model="threshold" :disabled="!instrumentId || busy" inputmode="decimal" :placeholder="alertKind === 'indicator' ? 'Value' : 'Price'" :aria-label="alertKind === 'indicator' ? 'Indicator threshold' : 'Alert price'" />
      <label class="alerts-tool__repeat"><input v-model="repeat" type="checkbox" :disabled="!instrumentId || busy" />Repeat</label>
      <button type="submit" :disabled="!instrumentId || busy || !validTarget">Add</button>
    </form>
    <p v-if="error" class="alerts-tool__error" role="alert" aria-live="assertive">{{ error }}</p>
    <p v-else-if="loading" class="alerts-tool__state" role="status" aria-live="polite">Loading alerts…</p>
    <p v-else-if="!instrumentId && !screenerAlerts.length" class="alerts-tool__state" role="status" aria-live="polite" aria-atomic="true">Select a canonical instrument.</p>
    <p v-else-if="!alerts.length && !indicatorAlerts.length && !screenerAlerts.length" class="alerts-tool__state" role="status" aria-live="polite" aria-atomic="true">No alerts for {{ symbol }}.</p>
    <ul v-else class="alerts-tool__list" role="list" aria-label="Saved alerts">
      <li v-for="alert in alerts" :key="`price-${alert.id}`" role="listitem" :aria-label="`Price alert: ${conditionLabel(alert.condition)} ${formatPrice(alert.threshold_price)}, ${alert.status}`">
        <span><b>{{ conditionLabel(alert.condition) }}</b> {{ formatPrice(alert.threshold_price) }}</span>
        <small>{{ alert.status }}{{ alert.repeat ? ' · repeats' : '' }}</small>
        <button type="button" :aria-label="`${alert.repeat ? 'Disable' : 'Enable'} repeat for price alert`" @click="patchPrice(alert.id, { repeat: !alert.repeat })"><WorkstationGlyph kind="repeat" /></button>
        <button v-if="alert.status === 'active'" type="button" aria-label="Pause price alert" @click="patchPrice(alert.id, { status: 'paused' })"><WorkstationGlyph kind="pause" /></button>
        <button v-else-if="alert.status === 'paused'" type="button" aria-label="Resume price alert" @click="patchPrice(alert.id, { status: 'active' })"><WorkstationGlyph kind="resume" /></button>
        <button v-if="alert.status !== 'active'" type="button" @click="rearmPrice(alert.id)">Rearm</button>
        <button type="button" aria-label="Delete price alert" @click="deletePrice(alert.id)"><WorkstationGlyph kind="delete" /></button>
      </li>
      <li v-for="alert in indicatorAlerts" :key="`indicator-${alert.id}`" role="listitem" :aria-label="`Indicator alert: ${alert.indicator_a_type} ${alert.condition}, ${alert.status}`">
        <span><b>{{ indicatorLabel(alert.indicator_a_type) }}</b> {{ alert.condition }} {{ alert.threshold_value ?? (alert.indicator_b_type ? indicatorLabel(alert.indicator_b_type) : '') }}</span>
        <small>{{ alert.status }}{{ alert.repeat ? ' · repeats' : '' }}</small>
        <button type="button" :aria-label="`${alert.repeat ? 'Disable' : 'Enable'} repeat for indicator alert`" @click="patchIndicator(alert.id, { repeat: !alert.repeat })"><WorkstationGlyph kind="repeat" /></button>
        <button v-if="alert.status === 'active'" type="button" aria-label="Pause indicator alert" @click="patchIndicator(alert.id, { status: 'paused' })"><WorkstationGlyph kind="pause" /></button>
        <button v-else-if="alert.status === 'paused'" type="button" aria-label="Resume indicator alert" @click="patchIndicator(alert.id, { status: 'active' })"><WorkstationGlyph kind="resume" /></button>
        <button v-if="alert.status !== 'active'" type="button" @click="rearmIndicator(alert.id)">Rearm</button>
        <button type="button" aria-label="Delete indicator alert" @click="deleteIndicator(alert.id)"><WorkstationGlyph kind="delete" /></button>
      </li>
      <li v-for="alert in screenerAlerts" :key="`screener-${alert.id}`" role="listitem" :aria-label="`Scan alert: ${alert.screener_name || `Scan ${alert.screener_id}`}, ${alert.status}`">
        <span><b>{{ alert.screener_name || `Scan #${alert.screener_id}` }}</b> {{ alert.trigger_type }}</span>
        <small>{{ alert.status }}{{ alert.repeat ? ' · repeats' : '' }}</small>
        <button type="button" :aria-label="`${alert.repeat ? 'Disable' : 'Enable'} repeat for scan alert`" @click="patchScreener(alert.id, { repeat: !alert.repeat })"><WorkstationGlyph kind="repeat" /></button>
        <button v-if="alert.status === 'active'" type="button" aria-label="Pause scan alert" @click="patchScreener(alert.id, { status: 'paused' })"><WorkstationGlyph kind="pause" /></button>
        <button v-else-if="alert.status === 'paused'" type="button" aria-label="Resume scan alert" @click="patchScreener(alert.id, { status: 'active' })"><WorkstationGlyph kind="resume" /></button>
        <button v-if="alert.status !== 'active'" type="button" @click="rearmScreener(alert.id)">Rearm</button>
        <button type="button" aria-label="Delete scan alert" @click="deleteScreener(alert.id)"><WorkstationGlyph kind="delete" /></button>
      </li>
    </ul>
    <section v-if="instrumentId && history.length" class="alerts-tool__history" role="region" aria-label="Alert firing history">
      <header>Recent firing history</header>
      <button v-for="event in history" :key="event.id" type="button" :aria-label="`${event.alert_type} fired ${formatFiredAt(event.fired_at)}`" @click="markViewed(event.id)">
        <span>{{ formatFiredAt(event.fired_at) }}</span><b>{{ event.alert_type }}</b><small>{{ event.trigger_value == null ? 'No trigger value' : formatPrice(event.trigger_value) }}</small>
      </button>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { INDICATOR_CATALOG } from '@/lib/indicators/catalog'
import WorkstationGlyph from './WorkstationGlyph.vue'

type PriceAlert = { id: number; condition: string; threshold_price: number | string; status: string; repeat: boolean }
type IndicatorAlert = { id: number; indicator_a_type: string; condition: string; threshold_value: number | string | null; indicator_b_type: string | null; status: string; repeat: boolean }
type ScreenerAlert = { id: number; screener_id: number; screener_name?: string; trigger_type: string; status: string; repeat: boolean }
type AlertHistory = { id: number; alert_type: string; fired_at: string; trigger_value: number | string | null; is_viewed: boolean }

const props = withDefaults(defineProps<{ instrumentId: number | null | undefined; symbol: string; timeframe?: string }>(), { timeframe: 'D1' })
const queryClient = useQueryClient()
const alertsQueryRoot = ['workstation', 'alerts'] as const
const alerts = ref<PriceAlert[]>([])
const indicatorAlerts = ref<IndicatorAlert[]>([])
// A workspace refresh can remount/reload this tool immediately after the POST
// succeeds. Keep acknowledged creations visible until the invalidated query
// observes the same server row, rather than briefly reverting to "No alerts".
const pendingIndicatorAlerts = ref<IndicatorAlert[]>([])
const screenerAlerts = ref<ScreenerAlert[]>([])
const condition = ref('crosses_above')
const threshold = ref('')
const repeat = ref(false)
const alertKind = ref<'price' | 'indicator'>('price')
const indicatorType = ref('rsi')
const indicatorBType = ref('ema')
const indicatorTarget = ref<'threshold' | 'indicator'>('threshold')
const indicatorOptions = INDICATOR_CATALOG
const indicatorParams = ref<Record<string, string | number>>({})
const indicatorBParams = ref<Record<string, string | number>>({})
const selectedIndicator = computed(() => indicatorOptions.find(item => item.type === indicatorType.value) ?? indicatorOptions[0])
const selectedIndicatorB = computed(() => indicatorOptions.find(item => item.type === indicatorBType.value) ?? indicatorOptions[0])
const conditionOptions = computed(() => alertKind.value === 'indicator'
  ? [
      { value: 'crosses_above', label: 'Crosses above' },
      { value: 'crosses_below', label: 'Crosses below' },
      { value: 'gt', label: 'Greater than' },
      { value: 'gte', label: 'At least' },
      { value: 'lt', label: 'Less than' },
      { value: 'lte', label: 'At most' },
    ]
  : [
      { value: 'crosses_above', label: 'Crosses above' },
      { value: 'crosses_below', label: 'Crosses below' },
      { value: 'touches', label: 'Touches' },
    ])
const timeframeOptions = [
  { value: 'M1', label: '1 minute' }, { value: 'M5', label: '5 minutes' }, { value: 'M15', label: '15 minutes' },
  { value: 'M30', label: '30 minutes' }, { value: 'H1', label: '1 hour' }, { value: 'H4', label: '4 hours' },
  { value: 'D1', label: 'Daily' }, { value: 'W1', label: 'Weekly' }, { value: 'MN', label: 'Monthly' },
]
const alertTimeframe = ref(timeframeOptions.some(option => option.value === props.timeframe) ? props.timeframe : 'D1')
const history = ref<AlertHistory[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
let viewGeneration = 0
const validThreshold = computed(() => Number.isFinite(Number(threshold.value)) && Number(threshold.value) > 0)
const validTarget = computed(() => alertKind.value === 'indicator' && indicatorTarget.value === 'indicator' ? Boolean(indicatorBType.value) : validThreshold.value)

function resetIndicatorParams() {
  const defaults = selectedIndicator.value?.defaultConfig.params ?? {}
  indicatorParams.value = Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, value as string | number]))
}
function indicatorParamsFor(type: string) {
  const defaults = indicatorOptions.find(item => item.type === type)?.defaultConfig.params ?? {}
  return Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, value as string | number])) as Record<string, string | number>
}
function normalizeParams(params: Record<string, string | number>) {
  return Object.fromEntries(Object.entries(params).map(([key, value]) => [key, typeof value === 'string' && value !== '' && Number.isFinite(Number(value)) ? Number(value) : value]))
}

async function load() {
  const generation = ++viewGeneration
  busy.value = false
  alerts.value = []
  indicatorAlerts.value = []
  screenerAlerts.value = []
  history.value = []
  error.value = ''
  if (!props.instrumentId) {
    loading.value = true
    try {
      const scans = await queryClient.fetchQuery<ScreenerAlert[]>({
        queryKey: [...alertsQueryRoot, 'screener'],
        queryFn: () => api.get<ScreenerAlert[]>('/alerts/screener'),
        staleTime: 30_000,
      })
      if (generation === viewGeneration && !props.instrumentId) screenerAlerts.value = scans
    } catch (cause: any) {
      if (generation === viewGeneration) error.value = cause?.message ?? 'Unable to load alerts'
    } finally {
      if (generation === viewGeneration) loading.value = false
    }
    return
  }
  loading.value = true
  try {
    const instrumentId = props.instrumentId
    const params = { instrument_id: instrumentId }
    const [prices, indicators, scans, firingHistory] = await Promise.all([
      queryClient.fetchQuery<PriceAlert[]>({ queryKey: [...alertsQueryRoot, 'price', instrumentId], queryFn: () => api.get<PriceAlert[]>('/alerts/price', params), staleTime: 30_000 }),
      queryClient.fetchQuery<IndicatorAlert[]>({ queryKey: [...alertsQueryRoot, 'indicator', instrumentId], queryFn: () => api.get<IndicatorAlert[]>('/alerts/indicator', params), staleTime: 30_000 }),
      queryClient.fetchQuery<ScreenerAlert[]>({ queryKey: [...alertsQueryRoot, 'screener'], queryFn: () => api.get<ScreenerAlert[]>('/alerts/screener'), staleTime: 30_000 }),
      queryClient.fetchQuery<AlertHistory[]>({ queryKey: [...alertsQueryRoot, 'history', instrumentId], queryFn: () => api.get<AlertHistory[]>(`/alerts/history/instrument/${instrumentId}`), staleTime: 30_000 }),
    ])
    if (generation !== viewGeneration || props.instrumentId !== instrumentId) return
    alerts.value = prices
    const serverIds = new Set(indicators.map(alert => alert.id))
    pendingIndicatorAlerts.value = pendingIndicatorAlerts.value.filter(alert => !serverIds.has(alert.id))
    indicatorAlerts.value = [...pendingIndicatorAlerts.value, ...indicators]
    screenerAlerts.value = scans
    history.value = firingHistory
  } catch (cause: any) {
    if (generation === viewGeneration) error.value = cause?.message ?? 'Unable to load alerts'
  } finally {
    if (generation === viewGeneration) loading.value = false
  }
}

async function create() {
  if (!props.instrumentId || !validTarget.value) return
  busy.value = true
  error.value = ''
  try {
    if (alertKind.value === 'indicator') {
      const alert = await api.post<IndicatorAlert>('/alerts/indicator', {
        instrument_id: props.instrumentId,
        timeframe: alertTimeframe.value,
        indicator_a_type: indicatorType.value,
        indicator_a_params: normalizeParams(indicatorParams.value),
        condition: condition.value,
        ...(indicatorTarget.value === 'indicator'
          ? { indicator_b_type: indicatorBType.value, indicator_b_params: normalizeParams(indicatorBParams.value) }
          : { threshold_value: Number(threshold.value) }),
        repeat: repeat.value,
      })
      pendingIndicatorAlerts.value = [alert, ...pendingIndicatorAlerts.value.filter(item => item.id !== alert.id)]
      indicatorAlerts.value = [alert, ...indicatorAlerts.value.filter(item => item.id !== alert.id)]
    } else {
      const alert = await api.post<PriceAlert>('/alerts/price', {
        instrument_id: props.instrumentId,
        condition: condition.value,
        threshold_price: Number(threshold.value),
        price_field: 'close',
        repeat: repeat.value,
      })
      alerts.value.unshift(alert)
    }
    threshold.value = ''
    repeat.value = false
    void queryClient.invalidateQueries({ queryKey: alertsQueryRoot })
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to create alert'
  } finally {
    busy.value = false
  }
}
async function deletePrice(id: number) { await mutate(() => api.delete(`/alerts/price/${id}`), () => { alerts.value = alerts.value.filter(alert => alert.id !== id) }) }
async function deleteIndicator(id: number) { await mutate(() => api.delete(`/alerts/indicator/${id}`), () => { indicatorAlerts.value = indicatorAlerts.value.filter(alert => alert.id !== id) }) }
async function deleteScreener(id: number) { await mutate(() => api.delete(`/alerts/screener/${id}`), () => { screenerAlerts.value = screenerAlerts.value.filter(alert => alert.id !== id) }) }
async function rearmPrice(id: number) { await mutate(() => api.post<PriceAlert>(`/alerts/price/${id}/rearm`, {}), updated => { alerts.value = alerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function rearmIndicator(id: number) { await mutate(() => api.post<IndicatorAlert>(`/alerts/indicator/${id}/rearm`, {}), updated => { indicatorAlerts.value = indicatorAlerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function rearmScreener(id: number) { await mutate(() => api.post<ScreenerAlert>(`/alerts/screener/${id}/rearm`, {}), updated => { screenerAlerts.value = screenerAlerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function patchPrice(id: number, patch: Partial<Pick<PriceAlert, 'repeat' | 'status'>>) { await mutate(() => api.patch<PriceAlert>(`/alerts/price/${id}`, patch), updated => { alerts.value = alerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function patchIndicator(id: number, patch: Partial<Pick<IndicatorAlert, 'repeat' | 'status'>>) { await mutate(() => api.patch<IndicatorAlert>(`/alerts/indicator/${id}`, patch), updated => { indicatorAlerts.value = indicatorAlerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function patchScreener(id: number, patch: Partial<Pick<ScreenerAlert, 'repeat' | 'status'>>) { await mutate(() => api.patch<ScreenerAlert>(`/alerts/screener/${id}`, patch), updated => { screenerAlerts.value = screenerAlerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function markViewed(id: number) { await mutate(() => api.patch<AlertHistory>(`/alerts/history/${id}/view`, {}), updated => { history.value = history.value.map(event => event.id === id ? updated : event) }) }
async function mutate<T>(request: () => Promise<T>, apply: (value: T) => void) {
  const generation = viewGeneration
  busy.value = true
  error.value = ''
  try {
    const result = await request()
    if (generation === viewGeneration) apply(result)
    void queryClient.invalidateQueries({ queryKey: alertsQueryRoot })
  } catch (cause: any) {
    if (generation === viewGeneration) error.value = cause?.message ?? 'Unable to update alert'
  } finally {
    if (generation === viewGeneration) busy.value = false
  }
}
function conditionLabel(value: string) { return value.replace(/_/g, ' ') }
function formatPrice(value: number | string) { return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 }) }
function indicatorLabel(type: string) {
  return type.trim().toUpperCase()
}
function formatFiredAt(value: string) { return new Date(value).toLocaleString() }

watch(() => props.instrumentId, () => { void load() }, { immediate: true })
watch(() => props.timeframe, value => {
  if (timeframeOptions.some(option => option.value === value)) alertTimeframe.value = value
})
watch(indicatorType, resetIndicatorParams, { immediate: true })
watch(indicatorBType, () => {
  indicatorBParams.value = indicatorParamsFor(indicatorBType.value)
}, { immediate: true })
watch(alertKind, value => {
  if (value === 'indicator' && condition.value === 'touches') condition.value = 'crosses_above'
  if (value === 'price' && ['gt', 'gte', 'lt', 'lte'].includes(condition.value)) condition.value = 'crosses_above'
})
</script>

<style scoped>
.alerts-tool { container-type: inline-size; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; height: 100%; min-height: 0; background: #11161b; color: #c7d0d8; font: 10px "Segoe UI", Arial, sans-serif; }
.alerts-tool__create { display: grid; grid-template-columns: minmax(58px, .8fr) minmax(86px, 1fr) minmax(66px, .7fr) minmax(42px, .65fr) auto 34px; gap: 4px; padding: 5px; border-bottom: 1px solid #2c3740; }
.alerts-tool__create label { min-width: 0; color: #8798a3; }
.alerts-tool__create label span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 9px; }
select, input, button { min-width: 0; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }
.alerts-tool__repeat { display:flex; align-items:center; gap:2px; min-width:0; white-space:nowrap; color:#92a3ae; }
.alerts-tool__repeat input { width:13px; height:13px; min-width:13px; flex:0 0 13px; margin:0; }
select { width: 100%; } input { padding: 2px 4px; } button { cursor: pointer; } button:disabled { cursor: default; opacity: .55; }
.alerts-tool__list { margin: 0; padding: 0; overflow: auto; list-style: none; }
.alerts-tool__list li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto auto; align-items: center; gap: 5px; min-height: 26px; padding: 3px 6px; border-bottom: 1px solid #20282f; }
.alerts-tool__list span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-transform: capitalize; }
.alerts-tool__list small { color: #8093a0; } .alerts-tool__list button { min-width: 17px; padding: 1px 4px; }
.alerts-tool__state, .alerts-tool__error { margin: 0; padding: 10px; color: #8b9aa4; } .alerts-tool__error { color: #e49a9a; }
.alerts-tool__history { max-height: 86px; overflow:auto; border-top:1px solid #2c3740; }.alerts-tool__history header { padding:4px 6px; color:#8ca2b0; text-transform:uppercase; font-size:9px; }.alerts-tool__history button { display:grid; width:100%; grid-template-columns:112px 52px minmax(0,1fr); gap:5px; padding:3px 6px; border-width:1px 0 0; text-align:left; }.alerts-tool__history span,.alerts-tool__history small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#8498a5; }.alerts-tool__history b { text-transform:capitalize; color:#c6d4dc; }
@container (max-width: 560px) { .alerts-tool__create { grid-template-columns: repeat(3, minmax(0, 1fr)); } .alerts-tool__kind { grid-column: span 1; } .alerts-tool__indicator { grid-column: span 1; } .alerts-tool__repeat { justify-content: flex-start; } .alerts-tool__create > button { min-width: 34px; } }
@container (max-width: 360px) { .alerts-tool__create { grid-template-columns: repeat(2, minmax(0, 1fr)); } .alerts-tool__create > label:first-child, .alerts-tool__create > label:nth-child(2) { grid-column: span 1; } .alerts-tool__repeat { grid-column: span 1; } }
</style>
