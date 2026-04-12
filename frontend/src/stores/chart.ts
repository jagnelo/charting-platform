import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { OHLCVBar, Timeframe, Instrument, IndicatorConfig } from '@/types'
import { api } from '@/lib/api'

const PAGE_SIZE = 500  // must match backend PAGE_SIZE

function createChartStore(storeId: string) {
  return defineStore(storeId, () => {
    const symbol     = ref<string>('')
    const timeframe  = ref<Timeframe>('D1')
    const bars       = ref<OHLCVBar[]>([])
    const instrument = ref<Instrument | null>(null)
    const indicators = ref<IndicatorConfig[]>([])
    const isLoading      = ref(false)
    const error          = ref<string | null>(null)
    const isLoadingMore  = ref(false)
    const hasReachedStart   = ref(false)
    const isFetchingHistory = ref(false)

    let _saveTimer:     ReturnType<typeof setTimeout>  | null = null
    let _coveragePoller: ReturnType<typeof setInterval> | null = null

    const activeIndicators = computed(() =>
      indicators.value.filter(i =>
        !i.lockedTimeframes?.length || i.lockedTimeframes.includes(timeframe.value)
      )
    )

    const uplotData = computed(() => {
      if (!bars.value.length) return [[], [], [], [], [], []]
      const barIndex = bars.value.map((_, i) => i)
      const opens    = bars.value.map(b => b.open)
      const highs    = bars.value.map(b => b.high)
      const lows     = bars.value.map(b => b.low)
      const closes   = bars.value.map(b => b.close)
      const volumes  = bars.value.map(b => b.volume ?? 0)
      return [barIndex, opens, highs, lows, closes, volumes]
    })

    async function loadInstrument(sym: string) {
      try {
        instrument.value = await api.get(`/instruments/${encodeURIComponent(sym)}`)
      } catch {
        // Auto-creates from yfinance on first visit
      }
    }

    async function loadIndicatorsForInstrument(instrumentId: number) {
      try {
        const res = await api.get<{ indicators: IndicatorConfig[] }>(`/instrument-indicators/${instrumentId}`)
        indicators.value = res.indicators
      } catch { /* silent */ }
    }

    async function saveIndicatorsForInstrument() {
      if (!instrument.value) return
      try {
        await api.put(`/instrument-indicators/${instrument.value.id}`, { indicators: indicators.value })
      } catch { /* silent */ }
    }

    async function loadBars(sym: string, tf: Timeframe) {
      isLoading.value = true
      error.value = null
      symbol.value = sym
      timeframe.value = tf
      hasReachedStart.value = false
      isLoadingMore.value = false
      _stopCoveragePoller()
      isFetchingHistory.value = false

      await loadInstrument(sym)

      if (instrument.value) {
        await loadIndicatorsForInstrument(instrument.value.id)
      }

      try {
        const raw = await api.get<any[]>(`/ohlcv/${encodeURIComponent(sym)}/${tf}`)
        bars.value = _mapBars(raw)
        if (raw.length < PAGE_SIZE) hasReachedStart.value = true
      } catch (e: any) {
        error.value = e.message ?? 'Failed to load chart data'
      } finally {
        isLoading.value = false
      }
      _pollCoverage(sym)
    }

    async function loadMoreBars() {
      if (isLoadingMore.value || hasReachedStart.value || !symbol.value || !timeframe.value) return
      if (!bars.value.length) return

      isLoadingMore.value = true
      const oldestTs = bars.value[0].ts
      const sym = symbol.value
      const tf  = timeframe.value
      try {
        const raw = await api.get<any[]>(`/ohlcv/${encodeURIComponent(sym)}/${tf}`, { before: oldestTs })
        if (!raw.length) {
          if (!isFetchingHistory.value) hasReachedStart.value = true
          return
        }
        if (symbol.value !== sym || timeframe.value !== tf) return
        bars.value = [..._mapBars(raw), ...bars.value]
        if (raw.length < PAGE_SIZE) {
          if (!isFetchingHistory.value) hasReachedStart.value = true
        }
      } catch { /* silent */ } finally {
        isLoadingMore.value = false
      }
    }

    function _mapBars(raw: any[]): OHLCVBar[] {
      return raw.map(b => ({
        ...b,
        open:   Number(b.open),
        high:   Number(b.high),
        low:    Number(b.low),
        close:  Number(b.close),
        volume: b.volume != null ? Number(b.volume) : undefined,
        vwap:   b.vwap   != null ? Number(b.vwap)   : undefined,
      }))
    }

    function setIndicators(configs: IndicatorConfig[]) { indicators.value = configs }
    function addIndicator(config: IndicatorConfig)     { indicators.value.push(config) }
    function removeIndicator(index: number)            { indicators.value.splice(index, 1) }
    function updateIndicator(index: number, config: IndicatorConfig) { indicators.value[index] = config }
    function reorderIndicators(newOrder: IndicatorConfig[]) { indicators.value = newOrder }

    async function _pollCoverage(sym: string) {
      _stopCoveragePoller()
      const check = async () => {
        if (symbol.value !== sym) { _stopCoveragePoller(); return }
        try {
          const res = await api.get<{ is_fetching: boolean }>(`/instruments/${encodeURIComponent(sym)}/data-coverage`)
          const wasFetching = isFetchingHistory.value
          isFetchingHistory.value = res.is_fetching
          if (!res.is_fetching) {
            _stopCoveragePoller()
            if (wasFetching && hasReachedStart.value && bars.value.length > 0) {
              hasReachedStart.value = false
            }
          }
        } catch {
          isFetchingHistory.value = false
          _stopCoveragePoller()
        }
      }
      await check()
      if (isFetchingHistory.value) _coveragePoller = setInterval(check, 5_000)
    }

    function _stopCoveragePoller() {
      if (_coveragePoller !== null) { clearInterval(_coveragePoller); _coveragePoller = null }
    }

    watch(indicators, () => {
      if (!instrument.value) return
      if (_saveTimer) clearTimeout(_saveTimer)
      _saveTimer = setTimeout(saveIndicatorsForInstrument, 1000)
    }, { deep: true })

    return {
      symbol, timeframe, bars, instrument, indicators, activeIndicators,
      isLoading, isLoadingMore, hasReachedStart, error, isFetchingHistory, uplotData,
      loadBars, loadMoreBars, loadInstrument,
      setIndicators, addIndicator, removeIndicator, updateIndicator, reorderIndicators,
      saveIndicatorsForInstrument,
    }
  })
}

// ── Public API ─────────────────────────────────────────────────────────────────

// The singleton stores map lets us lazily create per-panel store definitions.
const _storeMap = new Map<string, ReturnType<typeof createChartStore>>()

function _getStoreFor(id: string) {
  let store = _storeMap.get(id)
  if (!store) {
    store = createChartStore(id)
    _storeMap.set(id, store)
  }
  return store
}

/** Global single-chart store — backward-compatible alias for `usePanelStore('chart')`. */
export const useChartStore = _getStoreFor('chart')

/** Returns a panel-scoped chart store. Use `'chart'` for the default single-panel store. */
export function usePanelStore(panelId: string) {
  return _getStoreFor(panelId === 'main' ? 'chart' : `chart-${panelId}`)()
}
