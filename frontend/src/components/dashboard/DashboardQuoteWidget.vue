<template>
  <div class="quote-widget">
    <div v-if="loading && !instrument" class="widget-state">{{ preparationMessage || `Loading cached quote for ${symbol}...` }}</div>
    <div v-else-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="error && !instrument" class="widget-state error">{{ error }}</div>
    <template v-else-if="instrument || lastClose != null">
      <div class="quote-top">
        <div>
          <div class="quote-symbol">{{ instrument?.symbol ?? symbol }}</div>
          <div class="quote-name">{{ instrument?.name || 'Instrument details are unavailable; cached price data is retained.' }}</div>
        </div>
        <router-link class="quote-open" :to="`/chart/${encodeURIComponent(symbol)}`">Chart</router-link>
      </div>
      <div v-if="lastClose != null" class="quote-price">{{ formatMoney(lastClose, instrument?.currency) }}</div>
      <div v-else class="quote-price quote-price--empty">No cached price is available.</div>
      <div class="quote-change" :class="changePct >= 0 ? 'up' : 'down'">
        {{ changePct >= 0 ? '+' : '' }}{{ (changePct * 100).toFixed(2) }}%
      </div>
      <div class="quote-meta">
        <span>{{ instrument?.currency || 'Currency -' }}</span>
        <span>{{ instrument?.equity_detail?.sector || 'Sector -' }}</span>
      </div>
      <div v-if="preparationMessage" class="quote-preparation" role="status">{{ preparationMessage }}</div>
      <div v-if="error" class="quote-preparation error" role="status">{{ error }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { formatMoney } from '@/lib/format'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { dataPreparationCoordinator, instrumentHistoryPreparationRequest, preparationStatusMessage, PreparationProgressRefreshQueue, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'
import type { Instrument } from '@/types'

const props = defineProps<{ config: Record<string, any>; overrideSymbol?: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const instrument = ref<Instrument | null>(null)
const lastClose = ref<number | null>(null)
const prevClose = ref<number | null>(null)
const preparationMessage = ref('')

const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? '').trim()).toUpperCase()
)
let refreshSeq = 0
let mounted = false
let refreshController: AbortController | null = null
const changePct = computed(() => {
  if (lastClose.value == null || prevClose.value == null || prevClose.value === 0) return 0
  return (lastClose.value - prevClose.value) / prevClose.value
})

async function refresh() {
  const seq = ++refreshSeq
  refreshController?.abort()
  const controller = new AbortController()
  refreshController = controller
  let preparationSettled = false
  preparationMessage.value = ''
  if (!symbol.value) {
    instrument.value = null
    lastClose.value = null
    prevClose.value = null
    error.value = null
    loading.value = false
    if (refreshController === controller) refreshController = null
    return
  }
  loading.value = true
  error.value = null
  instrument.value = null
  lastClose.value = null
  prevClose.value = null
  try {
    const requestedSymbol = symbol.value
    const target = await resolveTarget(requestedSymbol)
    if (!mounted || seq !== refreshSeq) return
    const isCurrent = () => mounted && seq === refreshSeq && !controller.signal.aborted
    const queue = new PreparationProgressRefreshQueue()
    const readCachedQuote = async () => {
      const [profile, history] = await Promise.allSettled([
        api.get<Instrument>(`/instruments/${encodeURIComponent(target)}`),
        api.get<Array<{ close: number }>>(`/ohlcv/${encodeURIComponent(target)}/D1`, { limit: 2 }),
      ])
      if (!isCurrent()) return
      if (profile.status === 'fulfilled') instrument.value = profile.value
      if (history.status === 'fulfilled') {
        const bars = history.value
        const latest = bars[bars.length - 1]
        const previous = bars[bars.length - 2] ?? latest
        if (latest) {
          lastClose.value = Number(latest.close)
          prevClose.value = Number(previous?.close ?? latest.close)
        }
      }
      if (profile.status === 'rejected' && history.status === 'rejected') throw profile.reason
      if (history.status === 'rejected' || lastClose.value == null) error.value = 'Cached price history is unavailable.'
      else if (profile.status === 'rejected') error.value = 'Instrument details are unavailable; the cached price remains visible.'
      else error.value = null
    }
    const initialRead = readCachedQuote()
    const refreshForProgress = (response: import('@/lib/dataPreparation').DataEnsureResponse) =>
      queue.request(response, async () => {
        await initialRead
        if (!isCurrent() || !queue.isLatest(response)) return
        await readCachedQuote()
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
              if (isCurrent()) error.value = cause?.message ?? 'Cached quote could not be refreshed.'
            })
          }
        },
      },
    )
    void preparation.then(async prepared => {
      if (!isCurrent()) return
      preparationMessage.value = prepared.status === 'ready' ? '' : preparationStatusMessage(prepared)
      await refreshForProgress(prepared)
      if (prepared.status === 'ready' && isCurrent() && lastClose.value == null) {
        preparationMessage.value = 'Prepared daily history contains no bars yet.'
      }
    }).catch(cause => {
      if (isCurrent()) preparationMessage.value = 'Data preparation could not be completed; showing cached quote data.'
    }).finally(() => {
      preparationSettled = true
      if (refreshController === controller) refreshController = null
    })
    await initialRead
  } catch (e: any) {
    if (mounted && seq === refreshSeq && !controller.signal.aborted) {
      error.value = e?.message ?? 'Quote unavailable'
    }
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
.quote-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.quote-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.quote-symbol { color: #fff; font-size: 18px; font-weight: 800; }
.quote-name {
  color: #777;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.quote-open {
  color: #64b5f6;
  text-decoration: none;
  border: 1px solid #242424;
  border-radius: 4px;
  padding: 3px 6px;
  font-size: 10px;
}
.quote-price { color: #eee; font-size: 24px; font-weight: 700; }
.quote-price--empty { color: #777; font-size: 12px; }
.quote-change { font-size: 13px; font-weight: 700; }
.quote-change.up { color: #81c784; }
.quote-change.down { color: #ef5350; }
.quote-meta {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  color: #777;
  font-size: 10px;
}
.quote-meta span {
  border: 1px solid #242424;
  border-radius: 4px;
  padding: 3px 5px;
  background: #111;
}
.quote-preparation { color: #9c9c77; font-size: 10px; }
.quote-preparation.error { color: #ef9a9a; }
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
