<template>
  <div class="details-widget">
    <div v-if="loading && !instrument" class="widget-state">{{ preparationMessage || `Loading cached details for ${symbol}...` }}</div>
    <div v-else-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="error && !instrument" class="widget-state error">{{ error }}</div>
    <template v-else-if="instrument">
      <div class="details-main">
        <div class="details-symbol">{{ instrument.symbol }}</div>
        <router-link class="details-open" :to="`/chart/${encodeURIComponent(instrument.symbol)}`">Open</router-link>
      </div>
      <div class="details-name">{{ instrument.name || instrument.description }}</div>
      <div class="details-grid">
        <div v-for="row in rows" :key="row.label" class="detail-row">
          <span>{{ row.label }}</span>
          <b>{{ row.value || '-' }}</b>
        </div>
      </div>
      <div v-if="preparationMessage" class="details-preparation" role="status">{{ preparationMessage }}</div>
      <div v-if="error" class="details-preparation error" role="status">{{ error }} Cached instrument details remain available.</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { dataPreparationCoordinator, instrumentHistoryPreparationRequest, preparationStatusMessage, PreparationProgressRefreshQueue, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'
import type { Instrument } from '@/types'

const props = defineProps<{ config: Record<string, any>; overrideSymbol?: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const instrument = ref<Instrument | null>(null)
const preparationMessage = ref('')
const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? '').trim()).toUpperCase()
)
let refreshSeq = 0
let mounted = false
let refreshController: AbortController | null = null

const rows = computed(() => {
  const detail = instrument.value?.equity_detail
  const stats = instrument.value?.stats
  return [
    { label: 'Currency', value: instrument.value?.currency },
    { label: 'Sector', value: detail?.sector },
    { label: 'Industry', value: detail?.industry },
    { label: 'Country', value: detail?.country },
    { label: 'Market Cap', value: formatLarge(stats?.market_cap) },
    { label: 'P/E', value: stats?.pe_ratio != null ? Number(stats.pe_ratio).toFixed(2) : '' },
    { label: 'Beta', value: stats?.beta != null ? Number(stats.beta).toFixed(2) : '' },
    { label: '52W High', value: formatNumber(stats?.week52_high) },
    { label: '52W Low', value: formatNumber(stats?.week52_low) },
  ]
})

function formatNumber(value?: number | string | null) {
  if (value == null) return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatLarge(value?: number | string | null) {
  if (value == null) return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  return formatNumber(n)
}

async function refresh() {
  const seq = ++refreshSeq
  refreshController?.abort()
  const controller = new AbortController()
  refreshController = controller
  let preparationSettled = false
  preparationMessage.value = ''
  if (!symbol.value) {
    instrument.value = null
    error.value = null
    loading.value = false
    if (refreshController === controller) refreshController = null
    return
  }
  loading.value = true
  error.value = null
  instrument.value = null
  try {
    const requestedSymbol = symbol.value
    const target = await resolveTarget(requestedSymbol)
    if (!mounted || seq !== refreshSeq) return
    const isCurrent = () => mounted && seq === refreshSeq && !controller.signal.aborted
    const queue = new PreparationProgressRefreshQueue()
    const readCachedDetails = async (refreshHistory = false) => {
      const loadedInstrument = await api.get<Instrument>(`/instruments/${encodeURIComponent(target)}`)
      if (!isCurrent()) return
      instrument.value = loadedInstrument
      const hasYearRange = loadedInstrument.is_synthetic
        || Boolean(loadedInstrument.stats?.week52_high && loadedInstrument.stats?.week52_low)
      if (refreshHistory && !hasYearRange) {
        // This is an ordinary local-series read. It may populate the profile's
        // cached range fields, but does not wait for or trigger a provider path.
        await api.get(`/ohlcv/${encodeURIComponent(target)}/D1`, { limit: 260 }).catch(() => null)
        if (!isCurrent()) return
        const refreshedInstrument = await api.get<Instrument>(`/instruments/${encodeURIComponent(target)}`)
        if (isCurrent()) instrument.value = refreshedInstrument
      }
    }
    const initialRead = readCachedDetails(true)
    const refreshForProgress = (response: import('@/lib/dataPreparation').DataEnsureResponse) =>
      queue.request(response, async () => {
        await initialRead
        if (!isCurrent() || !queue.isLatest(response)) return
        await readCachedDetails(response.status === 'ready')
      })
    const preparation = dataPreparationCoordinator.ensure(
      instrumentHistoryPreparationRequest({ kind: 'instrument', symbol: target }, 'D1'),
      {
        signal: controller.signal,
        onProgress: progress => {
          if (!isCurrent()) return
          preparationMessage.value = preparationStatusMessage(progress.response)
          if (shouldRefreshAnalysisProgress(progress.response)) {
            void refreshForProgress(progress.response).catch(cause => {
              if (isCurrent()) error.value = cause?.message ?? 'Cached instrument details could not be refreshed.'
            })
          }
        },
      },
    )
    void preparation.then(async prepared => {
      if (!isCurrent()) return
      preparationMessage.value = prepared.status === 'ready' ? '' : preparationStatusMessage(prepared)
      await refreshForProgress(prepared)
    }).catch(() => {
      if (isCurrent()) preparationMessage.value = 'Data preparation could not be completed; showing cached instrument details.'
    }).finally(() => {
      preparationSettled = true
      if (refreshController === controller) refreshController = null
    })
    await initialRead
  } catch (e: any) {
    if (mounted && seq === refreshSeq && !controller.signal.aborted) error.value = e?.message ?? 'Instrument unavailable'
  } finally {
    if (mounted && seq === refreshSeq) loading.value = false
    if (preparationSettled && refreshController === controller) refreshController = null
  }
}

async function resolveTarget(target: string) {
  return ensureKnownInstrumentSymbol(target)
}

watch(symbol, refresh)
onMounted(() => {
  mounted = true
  void refresh()
})
onBeforeUnmount(() => {
  mounted = false
  refreshSeq += 1
  refreshController?.abort()
  refreshController = null
})
</script>

<style scoped>
.details-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.details-main {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.details-symbol { color: #fff; font-size: 17px; font-weight: 800; }
.details-open {
  color: #64b5f6;
  text-decoration: none;
  border: 1px solid #242424;
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 10px;
}
.details-name { color: #888; font-size: 11px; line-height: 1.35; }
.details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px 10px;
  overflow: auto;
  min-height: 0;
}
.detail-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #777;
  font-size: 10px;
  border-bottom: 1px solid #181818;
  padding-bottom: 4px;
}
.detail-row b {
  color: #ccc;
  font-weight: 500;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.details-preparation { color: #9c9c77; font-size: 10px; }
.details-preparation.error { color: #ef9a9a; }
.widget-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
  padding: 12px;
}
.widget-state.error { color: #ef5350; font-size: 10px; }
</style>
