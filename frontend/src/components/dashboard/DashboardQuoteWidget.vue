<template>
  <div class="quote-widget">
    <div v-if="loading" class="widget-state">{{ preparationMessage || `Preparing ${symbol}...` }}</div>
    <div v-else-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="preparationMessage" class="widget-state error">{{ preparationMessage }}</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <template v-else>
      <div class="quote-top">
        <div>
          <div class="quote-symbol">{{ instrument?.symbol ?? symbol }}</div>
          <div class="quote-name">{{ instrument?.name }}</div>
        </div>
        <router-link class="quote-open" :to="`/chart/${encodeURIComponent(symbol)}`">Chart</router-link>
      </div>
      <div class="quote-price">{{ formatMoney(lastClose, instrument?.currency) }}</div>
      <div class="quote-change" :class="changePct >= 0 ? 'up' : 'down'">
        {{ changePct >= 0 ? '+' : '' }}{{ (changePct * 100).toFixed(2) }}%
      </div>
      <div class="quote-meta">
        <span>{{ instrument?.currency || 'Currency -' }}</span>
        <span>{{ instrument?.equity_detail?.sector || 'Sector -' }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { formatMoney } from '@/lib/format'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { dataPreparationCoordinator, instrumentHistoryPreparationRequest, preparationStatusMessage } from '@/lib/dataPreparation'
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
  try {
    const requestedSymbol = symbol.value
    const target = await resolveTarget(requestedSymbol)
    if (!mounted || seq !== refreshSeq) return
    const prepared = await dataPreparationCoordinator.ensure(
      instrumentHistoryPreparationRequest({ kind: 'instrument', symbol: target }, 'D1'),
      {
        signal: controller.signal,
        onProgress: progress => {
          if (mounted && seq === refreshSeq) preparationMessage.value = preparationStatusMessage(progress.response)
        },
      },
    )
    if (!mounted || seq !== refreshSeq) return
    preparationMessage.value = prepared.status === 'ready' ? '' : preparationStatusMessage(prepared)
    if (prepared.status !== 'ready') return
    const loadedInstrument = await api.get<Instrument>(`/instruments/${encodeURIComponent(target)}`)
    if (!mounted || seq !== refreshSeq) return
    instrument.value = loadedInstrument
    const bars = await api.get<Array<{ close: number }>>(`/ohlcv/${encodeURIComponent(target)}/D1`, { limit: 2 })
    if (!mounted || seq !== refreshSeq) return
    const latest = bars[bars.length - 1]
    const prev = bars[bars.length - 2] ?? latest
    if (!latest) throw new Error('Prepared daily history contains no bars yet.')
    lastClose.value = Number(latest.close)
    prevClose.value = Number(prev?.close ?? latest.close)
  } catch (e: any) {
    if (mounted && seq === refreshSeq && !controller.signal.aborted) {
      error.value = e?.message ?? 'Quote unavailable'
    }
  } finally {
    if (mounted && seq === refreshSeq) loading.value = false
    if (refreshController === controller) refreshController = null
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
