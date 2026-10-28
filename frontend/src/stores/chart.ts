import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { OHLCVBar, Timeframe, Instrument, IndicatorConfig, ChartBarType } from '@/types'
import { api } from '@/lib/api'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'
import { hasActiveAnalysisDrag } from '@/lib/workstation/plotDrag'

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

export interface ChartTransformParams {
  brick_size?: number
  reversal_pct?: number
  box_size?: number
  reversal?: number
}

function basketIdFromSymbol(sym: string): number | null {
  const match = sym.trim().match(/^BASKET:(\d+)$/i)
  return match ? Number(match[1]) : null
}

function stableJsonValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableJsonValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, stableJsonValue(nested)]),
    )
  }
  return value
}

function indicatorStacksEqual(left: IndicatorConfig[], right: IndicatorConfig[]): boolean {
  return JSON.stringify(stableJsonValue(left)) === JSON.stringify(stableJsonValue(right))
}

function chartLoadScopeKey(
  sym: string,
  tf: Timeframe,
  type: ChartBarType,
  localOnly: boolean,
  transformParams: ChartTransformParams,
): string {
  return JSON.stringify([
    sym,
    tf,
    type,
    Boolean(localOnly),
    transformParams.brick_size ?? null,
    transformParams.reversal_pct ?? null,
    transformParams.box_size ?? null,
    transformParams.reversal ?? null,
  ])
}

function createChartStore(storeId: string) {
  return defineStore(storeId, () => {
    const symbol     = ref<string>('')
    const timeframe  = ref<Timeframe>('D1')
    const barType    = ref<ChartBarType>('candles')
    const transformParams = ref<ChartTransformParams>({})
    const bars       = ref<OHLCVBar[]>([])
    const instrument = ref<Instrument | null>(null)
    const indicators = ref<IndicatorConfig[]>([])
    const isLoading      = ref(false)
    const error          = ref<string | null>(null)
    const isLoadingMore  = ref(false)
    const hasReachedStart   = ref(false)
    const isFetchingHistory = ref(false)
    // Workstation charts are local-canonical. Legacy charts may opt into the
    // provider-hydrating route, so retain the mode across pagination/refreshes.
    const localOnlyMode = ref(false)
    const selectedIndicatorIndex    = ref<number | null>(null)
    const editRequestIndicatorIndex = ref<number | null>(null)
    const indicatorEditGeneration   = ref(0)

    let _saveTimer:     ReturnType<typeof setTimeout>  | null = null
    let _coveragePoller: ReturnType<typeof setInterval> | null = null
    let _loadGeneration = 0
    let inFlightLoad: { key: string; promise: Promise<void> } | null = null
    let renderedLoadScopeKey: string | null = null
    // A chart can finish its initial indicator request after the user has
    // already added/edited a plot. Never let that late hydration replace the
    // user's newer stack (this is especially important while a plot is being
    // dragged into another workstation tool).
    let indicatorsDirty = false
    let pendingIndicatorSave = false
    let pendingIndicatorSaveSymbol: string | null = null

    function cancelPendingIndicatorSave() {
      if (_saveTimer !== null) {
        clearTimeout(_saveTimer)
        _saveTimer = null
      }
    }

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

    async function saveIndicatorsForInstrument(): Promise<boolean> {
      cancelPendingIndicatorSave()
      const targetInstrument = instrument.value
      if (!targetInstrument) {
        pendingIndicatorSave = true
        pendingIndicatorSaveSymbol = symbol.value || null
        return false
      }
      pendingIndicatorSave = false
      pendingIndicatorSaveSymbol = null
      const payload = indicators.value.map(indicator => ({
        ...indicator,
        params: indicator.params ? { ...indicator.params } : indicator.params,
        style: indicator.style ? { ...indicator.style } : indicator.style,
        lockedTimeframes: indicator.lockedTimeframes ? [...indicator.lockedTimeframes] : indicator.lockedTimeframes,
      }))
      try {
        await api.put(`/instrument-indicators/${targetInstrument.id}`, { indicators: payload })
        return true
      } catch { /* silent */ return false }
    }

    function setBarType(type: ChartBarType) {
      barType.value = type
    }

    async function fetchBarsPage(
      sym: string,
      tf: Timeframe,
      opts: { before?: string; limit?: number; type?: ChartBarType; localOnly?: boolean; transformParams?: ChartTransformParams; fresh?: boolean } = {},
    ): Promise<OHLCVBar[]> {
      const type = opts.type ?? barType.value
      const params: Record<string, any> = { adjusted: true, ...(opts.transformParams ?? {}) }
      if (opts.before) params.before = opts.before
      if (opts.limit) params.limit = opts.limit

      const encoded = encodeURIComponent(sym)
      const basketId = basketIdFromSymbol(sym)
      const requestKey = JSON.stringify({ sym: sym.toUpperCase(), tf, type, transformParams: opts.transformParams ?? {}, adjusted: true, before: opts.before ?? null, limit: opts.limit ?? PAGE_SIZE, localOnly: Boolean(opts.localOnly), basketId })
      const request = async () => {
        if (opts.localOnly && !SERVER_TRANSFORMED_TYPES.has(type)) {
          const raw = await api.get<any[]>(`/ohlcv/local/${encoded}/${tf}`, {
            ...(opts.before ? { before: opts.before } : {}),
            limit: opts.limit ?? PAGE_SIZE,
          })
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
          ? await api.get<any[]>(`/ohlcv/${encoded}/${tf}/transformed`, {
            ...params,
            ...(opts.localOnly ? { local_only: true } : {}),
            bar_type: type,
          })
          : await api.get<any[]>(`/ohlcv/${encoded}/${tf}`, {
            ...params,
            ...(opts.localOnly ? { local_only: true } : {}),
          })
        return _mapBars(raw)
      }
      return dedupeOhlcvRequest(requestKey, request, undefined, {
        ignoreCompleted: opts.fresh,
      })
    }

    async function performLoadBars(sym: string, tf: Timeframe, nextBarType: ChartBarType, localOnly: boolean, normalizedTransformParams: ChartTransformParams, forceFresh = false) {
      if (!sym || !tf) return
      cancelPendingIndicatorSave()
      const generation = ++_loadGeneration
      const transformKey = JSON.stringify(normalizedTransformParams)
      const requestScopeKey = chartLoadScopeKey(sym, tf, nextBarType, localOnly, normalizedTransformParams)
      const isCurrent = () => generation === _loadGeneration && symbol.value === sym && timeframe.value === tf && barType.value === nextBarType && localOnlyMode.value === Boolean(localOnly) && JSON.stringify(transformParams.value) === transformKey
      const sameSelection = symbol.value === sym && timeframe.value === tf && barType.value === nextBarType && JSON.stringify(transformParams.value) === transformKey
      // UI refs can move ahead of loadBars (for example setBarType), so only a
      // previously successful request with the complete route/transform scope
      // may keep the currently rendered chart alive during a settled refresh.
      const refreshesRenderedSelection = forceFresh || (renderedLoadScopeKey === requestScopeKey && bars.value.length > 0)
      if (!sameSelection) {
        indicatorsDirty = false
        if (pendingIndicatorSaveSymbol !== sym) {
          pendingIndicatorSave = false
          pendingIndicatorSaveSymbol = null
        }
      }
      // Multiple mounted workstation roots can request the same selection
      // after the initial shared hydration has already settled. That remains a
      // genuine refresh, but it must not blank the current chart or toggle the
      // loading lifecycle that destroys and recreates its uPlot instance.
      isLoading.value = !refreshesRenderedSelection
      error.value = null
      symbol.value = sym
      timeframe.value = tf
      barType.value = nextBarType
      transformParams.value = normalizedTransformParams
      if (!refreshesRenderedSelection) instrument.value = null
      const preserveIndicatorsDuringDrag = hasActiveAnalysisDrag()
      if (!refreshesRenderedSelection) {
        renderedLoadScopeKey = null
        if (!preserveIndicatorsDuringDrag && !indicatorsDirty) indicators.value = []
        bars.value = []
        hasReachedStart.value = false
      }
      isLoadingMore.value = false
      _stopCoveragePoller()
      isFetchingHistory.value = false

      const basketId = basketIdFromSymbol(sym)
      localOnlyMode.value = Boolean(localOnly)
      if (basketId != null) {
        try {
          const mapped = await fetchBarsPage(sym, tf, {
            type: nextBarType,
            localOnly,
            transformParams: normalizedTransformParams,
            fresh: refreshesRenderedSelection,
          })
          if (!isCurrent()) return
          bars.value = mapped
          renderedLoadScopeKey = requestScopeKey
          hasReachedStart.value = true
        } catch (e: any) {
          if (isCurrent()) error.value = e.message ?? 'Failed to load basket chart data'
        } finally {
          if (isCurrent()) isLoading.value = false
        }
        return
      }

      // Workstation charts are explicitly local-only. Start that database read
      // alongside canonical instrument resolution so a cold instrument lookup
      // cannot serialize the two slowest parts of a symbol switch. Keep the
      // provider-capable legacy path ordered behind instrument validation: this
      // optimization must never turn an unresolved symbol into provider work.
      const localBarsPromise: Promise<{ mapped: OHLCVBar[] | null; error: unknown | null }> | null = localOnly
        ? fetchBarsPage(sym, tf, {
            type: nextBarType,
            localOnly: true,
            transformParams: normalizedTransformParams,
            fresh: refreshesRenderedSelection,
          }).then(
            mapped => ({ mapped, error: null }),
            error => ({ mapped: null, error }),
          )
        : null

      const loadedInstrument = await fetchInstrument(sym)
      if (!isCurrent()) return
      if (loadedInstrument || !refreshesRenderedSelection) instrument.value = loadedInstrument

      // A user can insert a plot while this symbol's metadata is still
      // hydrating. Flush that dirty stack now that the canonical instrument ID
      // is available; otherwise the insertion would only exist in memory and
      // disappear on the next symbol round-trip.
      if (isCurrent() && (pendingIndicatorSaveSymbol === sym || (pendingIndicatorSaveSymbol == null && indicatorsDirty))) {
        await saveIndicatorsForInstrument()
      }

      if (!loadedInstrument) {
        error.value = `Instrument "${sym.toUpperCase()}" was not found.`
        isLoading.value = false
        return
      }

      const indicatorsPromise = fetchIndicatorsForInstrument(loadedInstrument.id)
      try {
        const prefetchedBars = localBarsPromise ? await localBarsPromise : null
        if (prefetchedBars?.error) throw prefetchedBars.error
        const mapped = prefetchedBars?.mapped ?? await fetchBarsPage(sym, tf, {
          type: nextBarType,
          localOnly,
          transformParams: normalizedTransformParams,
          fresh: refreshesRenderedSelection,
        })
        const loadedIndicatorsBeforeRefresh = refreshesRenderedSelection
          ? await indicatorsPromise
          : null
        if (!isCurrent()) return
        if (loadedIndicatorsBeforeRefresh && !preserveIndicatorsDuringDrag && !indicatorsDirty
          && !indicatorStacksEqual(indicators.value, loadedIndicatorsBeforeRefresh)) {
          indicators.value = loadedIndicatorsBeforeRefresh
        }
        bars.value = mapped
        renderedLoadScopeKey = requestScopeKey
        if (mapped.length) hasReachedStart.value = false
        // A short initial page can mean either "brand-new listing" or "cache is
        // currently incomplete". Let the older-page path make that decision so
        // partial caches can self-repair when the user scrolls left.
        if (!mapped.length) hasReachedStart.value = true
        if (!refreshesRenderedSelection) {
          // Chart data and its OHLCV pointer are usable independently of saved
          // plot hydration. Do not keep a ready local chart blank while the
          // instrument-indicator request is still resolving.
          isLoading.value = false
          const loadedIndicators = await indicatorsPromise
          if (!isCurrent()) return
          if (!preserveIndicatorsDuringDrag && !indicatorsDirty
            && !indicatorStacksEqual(indicators.value, loadedIndicators)) {
            indicators.value = loadedIndicators
          }
        }
      } catch (e: any) {
        if (isCurrent()) error.value = e.message ?? 'Failed to load chart data'
      } finally {
        if (isCurrent()) isLoading.value = false
      }
      if (!isCurrent()) return

      const currentInstrument = instrument.value as Instrument | null
      const statsRefresh = currentInstrument && !currentInstrument.stats?.week52_high
        ? fetchInstrument(sym).then(refreshedInstrument => {
          if (isCurrent()) instrument.value = refreshedInstrument
        })
        : Promise.resolve()

      try {
        await statsRefresh
      } catch (e: any) {
        if (isCurrent()) error.value = e.message ?? 'Failed to load chart data'
      }
      if (isCurrent() && !loadedInstrument.is_synthetic) _pollCoverage(sym, generation)
    }

    function startLoadBars(sym: string, tf: Timeframe, nextBarType: ChartBarType, localOnly: boolean, normalizedTransformParams: ChartTransformParams, forceFresh = false): Promise<void> {
      const requestKey = chartLoadScopeKey(sym, tf, nextBarType, localOnly, normalizedTransformParams)
      let promise: Promise<void>
      promise = performLoadBars(sym, tf, nextBarType, localOnly, normalizedTransformParams, forceFresh)
        .finally(() => {
          if (inFlightLoad?.promise === promise) inFlightLoad = null
        })
      inFlightLoad = { key: requestKey, promise }
      return promise
    }

    function loadBars(sym = symbol.value, tf: Timeframe = timeframe.value, nextBarType: ChartBarType = barType.value, localOnly = false, nextTransformParams: ChartTransformParams = transformParams.value): Promise<void> {
      if (!sym || !tf) return Promise.resolve()
      const normalizedTransformParams = Object.fromEntries(Object.entries(nextTransformParams).filter(([, value]) => typeof value === 'number' && Number.isFinite(value))) as ChartTransformParams
      const requestKey = chartLoadScopeKey(sym, tf, nextBarType, localOnly, normalizedTransformParams)
      // Golden Layout can mount more than one virtual root for the same chart
      // store while a workspace is settling. Those roots must share one exact
      // hydration: restarting it clears bars, advances the generation and can
      // replace a viewport the user has already panned. Different selections,
      // timeframes, transforms and local/provider modes retain their distinct
      // keys, while a later call after settlement remains a genuine refresh.
      if (inFlightLoad?.key === requestKey) return inFlightLoad.promise
      return startLoadBars(sym, tf, nextBarType, localOnly, normalizedTransformParams)
    }

    async function refreshLocalBars(): Promise<void> {
      const sym = symbol.value
      const tf = timeframe.value
      const nextBarType = barType.value
      const normalizedTransformParams = Object.fromEntries(Object.entries(transformParams.value).filter(([, value]) => typeof value === 'number' && Number.isFinite(value))) as ChartTransformParams
      if (!sym || !tf) return
      const requestKey = chartLoadScopeKey(sym, tf, nextBarType, true, normalizedTransformParams)

      // A successful history action can finish while the initial chart load is
      // still awaiting instrument indicators. Coalescing the refresh into that
      // pending load would leave its earlier, empty local response on screen.
      // Wait for that exact selection to settle, then bypass the short-lived
      // OHLCV response cache for a fresh local read.
      while (inFlightLoad?.key === requestKey) {
        const pending = inFlightLoad.promise
        await pending.catch(() => undefined)
        if (symbol.value !== sym || timeframe.value !== tf || barType.value !== nextBarType
          || JSON.stringify(transformParams.value) !== JSON.stringify(normalizedTransformParams)) return
      }
      if (symbol.value !== sym || timeframe.value !== tf || barType.value !== nextBarType
        || JSON.stringify(transformParams.value) !== JSON.stringify(normalizedTransformParams)) return
      await startLoadBars(sym, tf, nextBarType, true, normalizedTransformParams, true)
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
      const currentTransformParams = transformParams.value
      const generation = _loadGeneration
      try {
        const mapped = await fetchBarsPage(sym, tf, { before: oldestTs, localOnly: localOnlyMode.value, type, transformParams: currentTransformParams })
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
      return fetchBarsPage(symbol.value, timeframe.value, { localOnly: localOnlyMode.value, transformParams: transformParams.value })
    }

    function _mapBars(raw: any[]): OHLCVBar[] {
      return raw.flatMap(b => {
        const open = Number(b?.open)
        const high = Number(b?.high)
        const low = Number(b?.low)
        const close = Number(b?.close)
        if (![open, high, low, close].every(Number.isFinite)) return []
        const volume = b?.volume == null ? undefined : Number(b.volume)
        const vwap = b?.vwap == null ? undefined : Number(b.vwap)
        return [{
          ...b,
          open,
          high,
          low,
          close,
          volume: volume != null && Number.isFinite(volume) ? volume : undefined,
          vwap: vwap != null && Number.isFinite(vwap) ? vwap : undefined,
        } as OHLCVBar]
      })
    }

    function noteIndicatorEdit() { indicatorsDirty = true; indicatorEditGeneration.value += 1 }
    function setIndicators(configs: IndicatorConfig[]) { noteIndicatorEdit(); indicators.value = configs }
    function addIndicator(config: IndicatorConfig)     { noteIndicatorEdit(); indicators.value.push(config) }
    function removeIndicator(index: number)            { noteIndicatorEdit(); indicators.value.splice(index, 1) }
    function updateIndicator(index: number, config: IndicatorConfig) { noteIndicatorEdit(); indicators.value[index] = config }
    function reorderIndicators(newOrder: IndicatorConfig[]) { noteIndicatorEdit(); indicators.value = newOrder }
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
      // Loading an instrument clears and then hydrates this ref. Those are
      // programmatic state transitions, not user edits; persisting them while
      // the indicator GET is still in flight can overwrite a saved stack with
      // an empty array. Only the explicit mutation helpers mark the stack
      // dirty, so automatic persistence must require that marker.
      if (!instrument.value || !indicatorsDirty) return
      if (_saveTimer) clearTimeout(_saveTimer)
      _saveTimer = setTimeout(saveIndicatorsForInstrument, 1000)
    }, { deep: true })

    return {
      symbol, timeframe, bars, instrument, indicators, activeIndicators,
      barType,
      transformParams,
      localOnlyMode,
      isLoading, loading: isLoading, isLoadingMore, hasReachedStart, error, isFetchingHistory, uplotData,
      selectedIndicatorIndex, editRequestIndicatorIndex,
      indicatorEditGeneration,
      loadBars, refreshLocalBars, loadMoreBars, loadInstrument,
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
