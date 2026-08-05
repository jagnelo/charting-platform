import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { OHLCVBar, Timeframe, Instrument, IndicatorConfig, ChartBarType } from '@/types'
import { api } from '@/lib/api'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'

const PAGE_SIZE = 500  // must match backend PAGE_SIZE
const SERVER_TRANSFORMED_TYPES = new Set<ChartBarType>([
  'ohlc',
  'heikin_ashi',
  'area',
  'baseline',
  'renko',
  'kagi',
  'point_figure',
])

function basketIdFromSymbol(sym: string): number | null {
  const match = sym.trim().match(/^BASKET:(\d+)$/i)
  return match ? Number(match[1]) : null
}

function createChartStore(storeId: string) {
  return defineStore(storeId, () => {
    const symbol     = ref<string>('')
    const timeframe  = ref<Timeframe>('D1')
    const barType    = ref<ChartBarType>('candles')
    const bars       = ref<OHLCVBar[]>([])
    const instrument = ref<Instrument | null>(null)
    const indicators = ref<IndicatorConfig[]>([])
    const isLoading      = ref(false)
    const error          = ref<string | null>(null)
    const isLoadingMore  = ref(false)
    const hasReachedStart   = ref(false)
    const isFetchingHistory = ref(false)
    const selectedIndicatorIndex    = ref<number | null>(null)
    const editRequestIndicatorIndex = ref<number | null>(null)

    let _saveTimer:     ReturnType<typeof setTimeout>  | null = null
    let _coveragePoller: ReturnType<typeof setInterval> | null = null
    let _loadGeneration = 0

    const activeIndicators = computed(() =>
      indicators.value.filter(i =>
        !i.hidden && (!i.lockedTimeframes?.length || i.lockedTimeframes.includes(timeframe.value))
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

    async function fetchInstrument(sym: string): Promise<Instrument | null> {
      try {
        return await api.get<Instrument>(`/instruments/${encodeURIComponent(sym)}`)
      } catch {
        return null
      }
    }

    async function loadInstrument(sym: string): Promise<Instrument | null> {
      const loaded = await fetchInstrument(sym)
      instrument.value = loaded
      return loaded
    }

    async function fetchIndicatorsForInstrument(instrumentId: number): Promise<IndicatorConfig[]> {
      try {
        const res = await api.get<{ indicators: IndicatorConfig[] }>(`/instrument-indicators/${instrumentId}`)
        return res.indicators
      } catch { return [] }
    }

    async function saveIndicatorsForInstrument() {
      if (!instrument.value) return
      try {
        await api.put(`/instrument-indicators/${instrument.value.id}`, { indicators: indicators.value })
      } catch { /* silent */ }
    }

    function setBarType(type: ChartBarType) {
      barType.value = type
    }

    async function fetchBarsPage(
      sym: string,
      tf: Timeframe,
      opts: { before?: string; limit?: number; type?: ChartBarType; localOnly?: boolean } = {},
    ): Promise<OHLCVBar[]> {
      const type = opts.type ?? barType.value
      const params: Record<string, any> = {}
      if (opts.before) params.before = opts.before
      if (opts.limit) params.limit = opts.limit

      const encoded = encodeURIComponent(sym)
      const basketId = basketIdFromSymbol(sym)
      const requestKey = JSON.stringify({ sym: sym.toUpperCase(), tf, type, adjusted: true, before: opts.before ?? null, limit: opts.limit ?? PAGE_SIZE, localOnly: Boolean(opts.localOnly), basketId })
      return dedupeOhlcvRequest(requestKey, async () => {
      if (opts.localOnly) {
        const raw = await api.get<any[]>(`/ohlcv/local/${encoded}/${tf}`, { limit: opts.limit ?? PAGE_SIZE })
        return _mapBars(raw)
      }
      if (basketId != null) {
        const raw = await api.get<any[]>(`/baskets/${basketId}/ohlcv/${tf}`, {
          ...params,
          limit: opts.limit ?? PAGE_SIZE,
        })
        return _mapBars(raw)
      }
      const raw = SERVER_TRANSFORMED_TYPES.has(type)
        ? await api.get<any[]>(`/ohlcv/${encoded}/${tf}/transformed`, { ...params, bar_type: type })
        : await api.get<any[]>(`/ohlcv/${encoded}/${tf}`, params)
      return _mapBars(raw)
      })
    }

    async function loadBars(sym = symbol.value, tf: Timeframe = timeframe.value, nextBarType: ChartBarType = barType.value, localOnly = false) {
      if (!sym || !tf) return
      const generation = ++_loadGeneration
      const isCurrent = () => generation === _loadGeneration && symbol.value === sym && timeframe.value === tf && barType.value === nextBarType
      isLoading.value = true
      error.value = null
      symbol.value = sym
      timeframe.value = tf
      barType.value = nextBarType
      instrument.value = null
      indicators.value = []
      bars.value = []
      hasReachedStart.value = false
      isLoadingMore.value = false
      _stopCoveragePoller()
      isFetchingHistory.value = false

      const basketId = basketIdFromSymbol(sym)
      if (basketId != null) {
        try {
          const mapped = await fetchBarsPage(sym, tf, { type: nextBarType })
          if (!isCurrent()) return
          bars.value = mapped
          hasReachedStart.value = true
        } catch (e: any) {
          if (isCurrent()) error.value = e.message ?? 'Failed to load basket chart data'
        } finally {
          if (isCurrent()) isLoading.value = false
        }
        return
      }

      const loadedInstrument = await fetchInstrument(sym)
      if (!isCurrent()) return
      instrument.value = loadedInstrument

      if (!loadedInstrument) {
        error.value = `Instrument "${sym.toUpperCase()}" was not found.`
        isLoading.value = false
        return
      }

      const loadedIndicators = await fetchIndicatorsForInstrument(loadedInstrument.id)
      if (!isCurrent()) return
      indicators.value = loadedIndicators

      try {
        const mapped = await fetchBarsPage(sym, tf, { type: nextBarType, localOnly })
        if (!isCurrent()) return
        bars.value = mapped
        // A short initial page can mean either "brand-new listing" or "cache is
        // currently incomplete". Let the older-page path make that decision so
        // partial caches can self-repair when the user scrolls left.
        if (!mapped.length) hasReachedStart.value = true
        // For brand-new instruments the backend computes 52w stats only after D1
        // bars are persisted. Reload instrument here so those stats are available.
        const currentInstrument = instrument.value as Instrument | null
        if (currentInstrument && !currentInstrument.stats?.week52_high) {
          const refreshedInstrument = await fetchInstrument(sym)
          if (isCurrent()) instrument.value = refreshedInstrument
        }
      } catch (e: any) {
        if (isCurrent()) error.value = e.message ?? 'Failed to load chart data'
      } finally {
        if (isCurrent()) isLoading.value = false
      }
      if (isCurrent() && !loadedInstrument.is_synthetic) _pollCoverage(sym, generation)
    }

    async function loadMoreBars() {
      if (isLoadingMore.value || hasReachedStart.value || !symbol.value || !timeframe.value) return
      if (!bars.value.length) return
      if (basketIdFromSymbol(symbol.value) != null) {
        hasReachedStart.value = true
        return
      }

      isLoadingMore.value = true
      const oldestTs = bars.value[0].ts
      const sym = symbol.value
      const tf  = timeframe.value
      const type = barType.value
      const generation = _loadGeneration
      try {
        const mapped = await fetchBarsPage(sym, tf, { before: oldestTs })
        if (!mapped.length) {
          if (!isFetchingHistory.value) hasReachedStart.value = true
          return
        }
        if (_loadGeneration !== generation || symbol.value !== sym || timeframe.value !== tf || barType.value !== type) return
        bars.value = [...mapped, ...bars.value]
        if (mapped.length < PAGE_SIZE) {
          if (!isFetchingHistory.value) hasReachedStart.value = true
        }
      } catch { /* silent */ } finally {
        isLoadingMore.value = false
      }
    }

    async function fetchLatestBars(): Promise<OHLCVBar[]> {
      if (!symbol.value || !timeframe.value) return []
      return fetchBarsPage(symbol.value, timeframe.value)
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
    function selectIndicator(i: number | null) { selectedIndicatorIndex.value = i }
    function requestEditIndicator(i: number | null) { editRequestIndicatorIndex.value = i }

    async function _pollCoverage(sym: string, generation: number) {
      _stopCoveragePoller()
      const check = async () => {
        if (_loadGeneration !== generation || symbol.value !== sym) { _stopCoveragePoller(); return }
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
      barType,
      isLoading, loading: isLoading, isLoadingMore, hasReachedStart, error, isFetchingHistory, uplotData,
      selectedIndicatorIndex, editRequestIndicatorIndex,
      loadBars, loadMoreBars, loadInstrument,
      setBarType, fetchLatestBars,
      setIndicators, addIndicator, removeIndicator, updateIndicator, reorderIndicators,
      selectIndicator, requestEditIndicator,
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
