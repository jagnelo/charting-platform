<template>
  <section class="alerts-tool">
    <form class="alerts-tool__create" @submit.prevent="create">
      <label>
        <span>{{ symbol }} alert</span>
        <select v-model="condition" :disabled="!instrumentId || busy">
          <option value="crosses_above">Crosses above</option>
          <option value="crosses_below">Crosses below</option>
          <option value="touches">Touches</option>
        </select>
      </label>
      <input v-model="threshold" :disabled="!instrumentId || busy" inputmode="decimal" placeholder="Price" aria-label="Alert price" />
      <label class="alerts-tool__repeat"><input v-model="repeat" type="checkbox" :disabled="!instrumentId || busy" />Repeat</label>
      <button type="submit" :disabled="!instrumentId || busy || !validThreshold">Add</button>
    </form>
    <p v-if="error" class="alerts-tool__error">{{ error }}</p>
    <p v-else-if="loading" class="alerts-tool__state">Loading alerts…</p>
    <p v-else-if="!instrumentId" class="alerts-tool__state">Select a canonical instrument.</p>
    <p v-else-if="!alerts.length && !indicatorAlerts.length" class="alerts-tool__state">No alerts for {{ symbol }}.</p>
    <ul v-else class="alerts-tool__list">
      <li v-for="alert in alerts" :key="`price-${alert.id}`">
        <span><b>{{ conditionLabel(alert.condition) }}</b> {{ formatPrice(alert.threshold_price) }}</span>
        <small>{{ alert.status }}{{ alert.repeat ? ' · repeats' : '' }}</small>
        <button type="button" :aria-label="`${alert.repeat ? 'Disable' : 'Enable'} repeat for price alert`" @click="patchPrice(alert.id, { repeat: !alert.repeat })">{{ alert.repeat ? '↻' : '↺' }}</button>
        <button v-if="alert.status === 'active'" type="button" aria-label="Pause price alert" @click="patchPrice(alert.id, { status: 'paused' })">Ⅱ</button>
        <button v-else-if="alert.status === 'paused'" type="button" aria-label="Resume price alert" @click="patchPrice(alert.id, { status: 'active' })">▶</button>
        <button v-if="alert.status !== 'active'" type="button" @click="rearmPrice(alert.id)">Rearm</button>
        <button type="button" aria-label="Delete price alert" @click="deletePrice(alert.id)">×</button>
      </li>
      <li v-for="alert in indicatorAlerts" :key="`indicator-${alert.id}`">
        <span><b>{{ alert.indicator_a_type }}</b> {{ alert.condition }} {{ alert.threshold_value ?? alert.indicator_b_type ?? '' }}</span>
        <small>{{ alert.status }}{{ alert.repeat ? ' · repeats' : '' }}</small>
        <button type="button" :aria-label="`${alert.repeat ? 'Disable' : 'Enable'} repeat for indicator alert`" @click="patchIndicator(alert.id, { repeat: !alert.repeat })">{{ alert.repeat ? '↻' : '↺' }}</button>
        <button v-if="alert.status === 'active'" type="button" aria-label="Pause indicator alert" @click="patchIndicator(alert.id, { status: 'paused' })">Ⅱ</button>
        <button v-else-if="alert.status === 'paused'" type="button" aria-label="Resume indicator alert" @click="patchIndicator(alert.id, { status: 'active' })">▶</button>
        <button v-if="alert.status !== 'active'" type="button" @click="rearmIndicator(alert.id)">Rearm</button>
        <button type="button" aria-label="Delete indicator alert" @click="deleteIndicator(alert.id)">×</button>
      </li>
    </ul>
    <section v-if="instrumentId && history.length" class="alerts-tool__history" aria-label="Alert firing history">
      <header>Recent firing history</header>
      <button v-for="event in history" :key="event.id" type="button" @click="markViewed(event.id)">
        <span>{{ formatFiredAt(event.fired_at) }}</span><b>{{ event.alert_type }}</b><small>{{ event.trigger_value == null ? 'No trigger value' : formatPrice(event.trigger_value) }}</small>
      </button>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'

type PriceAlert = { id: number; condition: string; threshold_price: number | string; status: string; repeat: boolean }
type IndicatorAlert = { id: number; indicator_a_type: string; condition: string; threshold_value: number | string | null; indicator_b_type: string | null; status: string; repeat: boolean }
type AlertHistory = { id: number; alert_type: string; fired_at: string; trigger_value: number | string | null; is_viewed: boolean }

const props = defineProps<{ instrumentId: number | null | undefined; symbol: string }>()
const alerts = ref<PriceAlert[]>([])
const indicatorAlerts = ref<IndicatorAlert[]>([])
const condition = ref('crosses_above')
const threshold = ref('')
const repeat = ref(false)
const history = ref<AlertHistory[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
let viewGeneration = 0
const validThreshold = computed(() => Number.isFinite(Number(threshold.value)) && Number(threshold.value) > 0)

async function load() {
  const generation = ++viewGeneration
  alerts.value = []
  indicatorAlerts.value = []
  history.value = []
  error.value = ''
  if (!props.instrumentId) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const instrumentId = props.instrumentId
    const params = { instrument_id: instrumentId }
    const [prices, indicators, firingHistory] = await Promise.all([
      api.get<PriceAlert[]>('/alerts/price', params),
      api.get<IndicatorAlert[]>('/alerts/indicator', params),
      api.get<AlertHistory[]>(`/alerts/history/instrument/${instrumentId}`),
    ])
    if (generation !== viewGeneration || props.instrumentId !== instrumentId) return
    alerts.value = prices
    indicatorAlerts.value = indicators
    history.value = firingHistory
  } catch (cause: any) {
    if (generation === viewGeneration) error.value = cause?.message ?? 'Unable to load alerts'
  } finally {
    if (generation === viewGeneration) loading.value = false
  }
}

async function create() {
  if (!props.instrumentId || !validThreshold.value) return
  busy.value = true
  error.value = ''
  try {
    const alert = await api.post<PriceAlert>('/alerts/price', {
      instrument_id: props.instrumentId,
      condition: condition.value,
      threshold_price: Number(threshold.value),
      price_field: 'close',
      repeat: repeat.value,
    })
    alerts.value.unshift(alert)
    threshold.value = ''
    repeat.value = false
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to create alert'
  } finally {
    busy.value = false
  }
}
async function deletePrice(id: number) { await mutate(() => api.delete(`/alerts/price/${id}`), () => { alerts.value = alerts.value.filter(alert => alert.id !== id) }) }
async function deleteIndicator(id: number) { await mutate(() => api.delete(`/alerts/indicator/${id}`), () => { indicatorAlerts.value = indicatorAlerts.value.filter(alert => alert.id !== id) }) }
async function rearmPrice(id: number) { await mutate(() => api.post<PriceAlert>(`/alerts/price/${id}/rearm`, {}), updated => { alerts.value = alerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function rearmIndicator(id: number) { await mutate(() => api.post<IndicatorAlert>(`/alerts/indicator/${id}/rearm`, {}), updated => { indicatorAlerts.value = indicatorAlerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function patchPrice(id: number, patch: Partial<Pick<PriceAlert, 'repeat' | 'status'>>) { await mutate(() => api.patch<PriceAlert>(`/alerts/price/${id}`, patch), updated => { alerts.value = alerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function patchIndicator(id: number, patch: Partial<Pick<IndicatorAlert, 'repeat' | 'status'>>) { await mutate(() => api.patch<IndicatorAlert>(`/alerts/indicator/${id}`, patch), updated => { indicatorAlerts.value = indicatorAlerts.value.map(alert => alert.id === id ? updated : alert) }) }
async function markViewed(id: number) { await mutate(() => api.patch<AlertHistory>(`/alerts/history/${id}/view`, {}), updated => { history.value = history.value.map(event => event.id === id ? updated : event) }) }
async function mutate<T>(request: () => Promise<T>, apply: (value: T) => void) {
  const generation = viewGeneration
  busy.value = true
  error.value = ''
  try {
    const result = await request()
    if (generation === viewGeneration) apply(result)
  } catch (cause: any) {
    if (generation === viewGeneration) error.value = cause?.message ?? 'Unable to update alert'
  } finally {
    if (generation === viewGeneration) busy.value = false
  }
}
function conditionLabel(value: string) { return value.replace(/_/g, ' ') }
function formatPrice(value: number | string) { return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 }) }
function formatFiredAt(value: string) { return new Date(value).toLocaleString() }

watch(() => props.instrumentId, () => { void load() }, { immediate: true })
</script>

<style scoped>
.alerts-tool { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; height: 100%; min-height: 0; background: #11161b; color: #c7d0d8; font: 10px "Segoe UI", Arial, sans-serif; }
.alerts-tool__create { display: grid; grid-template-columns: minmax(0, 1fr) 66px auto 34px; gap: 4px; padding: 5px; border-bottom: 1px solid #2c3740; }
.alerts-tool__create label { min-width: 0; color: #8798a3; }
.alerts-tool__create label span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 9px; }
select, input, button { min-width: 0; border: 1px solid #34434e; background: #172027; color: #d2dce3; font: inherit; }
.alerts-tool__repeat { display:flex; align-items:center; gap:2px; white-space:nowrap; color:#92a3ae; }
select { width: 100%; } input { padding: 2px 4px; } button { cursor: pointer; } button:disabled { cursor: default; opacity: .55; }
.alerts-tool__list { margin: 0; padding: 0; overflow: auto; list-style: none; }
.alerts-tool__list li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto auto; align-items: center; gap: 5px; min-height: 26px; padding: 3px 6px; border-bottom: 1px solid #20282f; }
.alerts-tool__list span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-transform: capitalize; }
.alerts-tool__list small { color: #8093a0; } .alerts-tool__list button { min-width: 17px; padding: 1px 4px; }
.alerts-tool__state, .alerts-tool__error { margin: 0; padding: 10px; color: #8b9aa4; } .alerts-tool__error { color: #e49a9a; }
.alerts-tool__history { max-height: 86px; overflow:auto; border-top:1px solid #2c3740; }.alerts-tool__history header { padding:4px 6px; color:#8ca2b0; text-transform:uppercase; font-size:9px; }.alerts-tool__history button { display:grid; width:100%; grid-template-columns:112px 52px minmax(0,1fr); gap:5px; padding:3px 6px; border-width:1px 0 0; text-align:left; }.alerts-tool__history span,.alerts-tool__history small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#8498a5; }.alerts-tool__history b { text-transform:capitalize; color:#c6d4dc; }
</style>
