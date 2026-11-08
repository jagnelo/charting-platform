import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { OHLCVBar, Timeframe, Instrument, IndicatorConfig, ChartBarType } from '@/types'
import { api, type ApiRequestPriority } from '@/lib/api'
import { acquireSelectedHistory, defaultHistoryRange, olderHistoryRange } from '@/lib/onDemandAcquisition'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'
import { hasActiveAnalysisDrag } from '@/lib/workstation/plotDrag'
import { dataPreparationCoordinator, PreparationProgressRefreshQueue, preparationStatusMessage } from '@/lib/dataPreparation'
import type { Basket } from '@/types'

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

export interface WorkstationPanelChartRefresh {
  matches: (symbol: string, timeframe: Timeframe) => boolean
  refresh: (symbol: string, timeframe: Timeframe, isCurrent: () => boolean) => Promise<void>
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
    const historyBoundaryMessage = ref('')
    const historyRetryAt = ref<string | null>(null)
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
    let olderHistoryAbortController: AbortController | null = null
    let basketPreparationController: AbortController | null = null
    let basketPreparationKey: string | null = null
    let basketPreparationGeneration = 0
    let renderedLoadScopeKey: string | null = null
    let noProgressHistoryCursor: string | null = null
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

    function resetForAuthSessionBoundary() {
      _loadGeneration += 1
      _stopCoveragePoller()
      cancelPendingIndicatorSave()
      olderHistoryAbortController?.abort()
      olderHistoryAbortController = null
      basketPreparationController?.abort()
      basketPreparationController = null
      basketPreparationKey = null
      basketPreparationGeneration = 0
      inFlightLoad = null
      bars.value = []
      instrument.value = null
      indicators.value = []
      symbol.value = ''
      hasReachedStart.value = false
      historyBoundaryMessage.value = ''
      historyRetryAt.value = null
      isFetchingHistory.value = false
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

    async function fetchInstrument(sym: string, priority?: ApiRequestPriority): Promise<Instrument | null> {
      try {
        const path = `/instruments/${encodeURIComponent(sym)}`
        return await (priority
          ? api.get<Instrument>(path, undefined, { priority })
          : api.get<Instrument>(path))
      } catch {
        return null
      }
    }

    async function loadInstrument(sym: string): Promise<Instrument | null> {
      const loaded = await fetchInstrument(sym)
      instrument.value = loaded
      return loaded
    }

    async function fetchIndicatorsForInstrument(instrumentId: number, priority?: ApiRequestPriority): Promise<IndicatorConfig[]> {
      try {
        const path = `/instrument-indicators/${instrumentId}`
        const res = await (priority
          ? api.get<{ indicators: IndicatorConfig[] }>(path, undefined, { priority })
          : api.get<{ indicators: IndicatorConfig[] }>(path))
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
      // The active workstation chart is a foreground cache read. Keep it in
      // the reserved API lane so unrelated analysis panels cannot occupy all
      // five ordinary HTTP/1.1 slots ahead of visible local candles.
      const requestOptions = opts.localOnly ? { priority: 'high' as const } : undefined
      const requestKey = JSON.stringify({ sym: sym.toUpperCase(), tf, type, transformParams: opts.transformParams ?? {}, adjusted: true, before: opts.before ?? null, limit: opts.limit ?? PAGE_SIZE, localOnly: Boolean(opts.localOnly), basketId })
      const request = async () => {
        if (basketId == null && opts.localOnly && !SERVER_TRANSFORMED_TYPES.has(type)) {
          const params = {
            ...(opts.before ? { before: opts.before } : {}),
            limit: opts.limit ?? PAGE_SIZE,
          }
          const raw = requestOptions
            ? await api.get<any[]>(`/ohlcv/local/${encoded}/${tf}`, params, requestOptions)
            : await api.get<any[]>(`/ohlcv/local/${encoded}/${tf}`, params)
          return _mapBars(raw)
        }
        if (basketId != null) {
          const basketPath = `/baskets/${basketId}/ohlcv/${tf}`
          const basketParams = {
            ...params,
            limit: opts.limit ?? PAGE_SIZE,
          }
          const raw = requestOptions
            ? await api.get<any[]>(basketPath, basketParams, requestOptions)
            : await api.get<any[]>(basketPath, basketParams)
          return _mapBars(raw)
        }
        const path = SERVER_TRANSFORMED_TYPES.has(type)
          ? `/ohlcv/${encoded}/${tf}/transformed`
          : `/ohlcv/${encoded}/${tf}`
        const query = SERVER_TRANSFORMED_TYPES.has(type)
          ? {
            ...params,
            ...(opts.localOnly ? { local_only: true } : {}),
            bar_type: type,
          }
          : {
            ...params,
            ...(opts.localOnly ? { local_only: true } : {}),
          }
        const raw = requestOptions
          ? await api.get<any[]>(path, query, requestOptions)
          : await api.get<any[]>(path, query)
        return _mapBars(raw)
      }
      return dedupeOhlcvRequest(requestKey, request, undefined, {
        ignoreCompleted: opts.fresh,
      })
    }

    function startBasketMemberPreparation(basketId: number, sym: string, tf: Timeframe, generation: number) {
      const key = `${basketId}:${tf}`
      if (basketPreparationKey === key && basketPreparationController) {
        basketPreparationGeneration = generation
        return
      }
      basketPreparationController?.abort()
      const controller = new AbortController()
      basketPreparationController = controller
      basketPreparationKey = key
      basketPreparationGeneration = generation
      const isCurrent = () => basketPreparationGeneration === _loadGeneration
        && symbol.value === sym && timeframe.value === tf
        && basketPreparationKey === key && !controller.signal.aborted
      historyBoundaryMessage.value = 'Checking the saved basket members for missing chart data…'

      void (async () => {
        try {
          const basket = await api.get<Basket>(`/baskets/${basketId}`, undefined, { priority: 'high', signal: controller.signal })
          if (!isCurrent()) return
          if (basket.id !== basketId || !Array.isArray(basket.members) || !basket.members.length
            || basket.members.some(member => !Number.isSafeInteger(member.instrument_id) || member.instrument_id <= 0)) {
            historyBoundaryMessage.value = 'The saved basket member list could not be verified; the current chart remains available.'
            return
          }
          const members = [...basket.members].sort((left, right) => left.position - right.position)
          const states = new Map<number, { symbol: string; response?: import('@/lib/dataPreparation').DataEnsureResponse; error?: unknown }>()
          const queues = new Map(members.map(member => [member.instrument_id, new PreparationProgressRefreshQueue()]))
          const refreshBasket = async () => {
            if (!isCurrent()) return
            try {
              const mapped = await fetchBarsPage(sym, tf, { type: barType.value, localOnly: true, transformParams: transformParams.value, fresh: true })
              if (!isCurrent()) return
              bars.value = mapped
              renderedLoadScopeKey = chartLoadScopeKey(sym, tf, barType.value, localOnlyMode.value, transformParams.value)
            } catch {
              if (isCurrent()) historyBoundaryMessage.value = 'Basket member data progressed, but the current basket chart could not be refreshed.'
            }
          }
          const hasUsableHistory = (response: import('@/lib/dataPreparation').DataEnsureResponse) => response.dependencies.some(dependency =>
            dependency.dataset === 'history' && (dependency.covered_ranges.length > 0
              || (dependency.covered_start !== null && dependency.covered_end !== null)))
          const updateSummary = () => {
            if (!isCurrent()) return
            const pending = [...states.values()].filter(state => {
              if (state.error) return false
              const response = state.response
              if (!response) return true
              if (response.has_pending_work === false) return false
              return response.has_pending_work === true
                || ['queued', 'running', 'waiting'].includes(response.status)
                || response.status === 'partial'
            }).length
            const missing = [...states.values()].flatMap(state => {
              if (state.error) return [`${state.symbol}: preparation could not be checked.`]
              if (!state.response || ['ready'].includes(state.response.status)) return []
              const history = state.response.dependencies.find(dependency => dependency.dataset === 'history')
              if (history?.status === 'ready') return []
              return [`${state.symbol}: ${preparationStatusMessage(state.response)}`]
            })
            historyBoundaryMessage.value = pending
              ? `Preparing saved basket members (${members.length - pending}/${members.length})…`
              : missing.length
                ? `The complete basket chart is waiting for member data. ${missing.join(' ')}`
                : `All saved basket members have current local chart data.`
          }
          members.forEach(member => {
            const memberSymbol = String(member.symbol ?? member.label ?? member.instrument_id).trim().toUpperCase()
            const queue = queues.get(member.instrument_id)!
            states.set(member.instrument_id, { symbol: memberSymbol })
          })
          updateSummary()
          // Submit all independent durable member requests before awaiting any
          // result. Aborting this observer on route change does not cancel work
          // already accepted by the Provider queue.
          const tasks = members.map(async member => {
            const memberSymbol = String(member.symbol ?? member.label ?? member.instrument_id).trim().toUpperCase()
            const queue = queues.get(member.instrument_id)!
            try {
              const result = await dataPreparationCoordinator.ensure({
                target: { kind: 'instrument', instrument_id: member.instrument_id },
                datasets: ['identity', 'profile', 'history'],
                timeframe: tf,
                adjusted: true,
              }, {
                signal: controller.signal,
                priority: 'high',
                onProgress: progress => {
                  if (!isCurrent()) return
                  const state = states.get(member.instrument_id)!
                  state.response = progress.response
                  updateSummary()
                  if (hasUsableHistory(progress.response)) {
                    void queue.request(progress.response, refreshBasket).catch(() => undefined)
                  }
                },
              })
              if (!isCurrent()) return
              states.set(member.instrument_id, { symbol: memberSymbol, response: result })
              if (hasUsableHistory(result)) await queue.request(result, refreshBasket)
            } catch (error) {
              if (isCurrent() && (error as { name?: string })?.name !== 'AbortError') {
                states.set(member.instrument_id, { symbol: memberSymbol, error })
              }
            } finally {
              updateSummary()
            }
          })
          await Promise.allSettled(tasks)
          if (isCurrent()) updateSummary()
        } catch {
          if (isCurrent()) historyBoundaryMessage.value = 'Basket members could not be checked; the existing basket chart remains available.'
        } finally {
          if (basketPreparationController === controller) {
            basketPreparationController = null
            basketPreparationKey = null
          }
        }
      })()
    }

    async function performLoadBars(sym: string, tf: Timeframe, nextBarType: ChartBarType, localOnly: boolean, normalizedTransformParams: ChartTransformParams, forceFresh = false) {
      if (!sym || !tf) return
      olderHistoryAbortController?.abort()
      olderHistoryAbortController = null
      isLoadingMore.value = false
      cancelPendingIndicatorSave()
      const generation = ++_loadGeneration
      const basketId = basketIdFromSymbol(sym)
      const requestedBasketPreparationKey = basketId !== null && localOnly ? `${basketId}:${tf}` : null
      if (basketPreparationKey && basketPreparationKey !== requestedBasketPreparationKey) {
        basketPreparationController?.abort()
        basketPreparationController = null
        basketPreparationKey = null
        basketPreparationGeneration = 0
      } else if (basketPreparationController && requestedBasketPreparationKey === basketPreparationKey) {
        basketPreparationGeneration = generation
      }
      const transformKey = JSON.stringify(normalizedTransformParams)
      const requestScopeKey = chartLoadScopeKey(sym, tf, nextBarType, localOnly, normalizedTransformParams)
      const isCurrent = () => generation === _loadGeneration && symbol.value === sym && timeframe.value === tf && barType.value === nextBarType && localOnlyMode.value === Boolean(localOnly) && JSON.stringify(transformParams.value) === transformKey
      const sameSelection = symbol.value === sym && timeframe.value === tf && barType.value === nextBarType && JSON.stringify(transformParams.value) === transformKey
      // A deliberate chart reload is the explicit way to retry a completed
      // older-history request that made no local progress.
      noProgressHistoryCursor = null
      // UI refs can move ahead of loadBars (for example setBarType), so only a
      // previously successful request with the complete route/transform scope
      // may keep the currently rendered chart alive during a settled refresh.
      const refreshesRenderedSelection = forceFresh || (renderedLoadScopeKey === requestScopeKey && bars.value.length > 0)
      if (!sameSelection) {
        historyBoundaryMessage.value = ''
        historyRetryAt.value = null
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

      localOnlyMode.value = Boolean(localOnly)
      if (basketId != null) {
        // The authenticated basket membership request is independent from the
        // synthetic chart read. Start it immediately so slow/empty cached
        // basket bars cannot delay submitting the real member preparations.
        if (localOnly) startBasketMemberPreparation(basketId, sym, tf, generation)
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

      const publishLocalBars = (mapped: OHLCVBar[]) => {
        if (!isCurrent()) return false
        bars.value = mapped
        renderedLoadScopeKey = requestScopeKey
        hasReachedStart.value = mapped.length === 0
        // The local-history endpoint is already scoped to a canonical cached
        // series. Do not hide those bars behind the separate instrument/profile
        // read; that metadata request can remain pending while the chart is
        // useful. The normal identity path below still validates the selection
        // before indicators or further acquisition are attached.
        isLoading.value = false
        return true
      }
      if (localBarsPromise) {
        void localBarsPromise.then(result => {
          if (!result.error && (result.mapped?.length || !refreshesRenderedSelection)) {
            // Publish newly available local OHLCV as soon as its own read
            // completes. A cold-cache progress refresh is forceFresh, but its
            // bars are still independent of a slower canonical metadata read;
            // waiting for fetchInstrument below can leave a useful chart blank
            // while the durable history worker has already filled the cache.
            // Preserve an existing rendered chart when a refresh still returns
            // no rows.
            publishLocalBars(result.mapped ?? [])
          }
        })
      }

      const loadedInstrument = await fetchInstrument(sym, localOnly ? 'high' : undefined)
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
        const localResult = localBarsPromise ? await localBarsPromise : null
        if (!isCurrent()) return
        if (localOnly && bars.value.length > 0 && renderedLoadScopeKey === requestScopeKey) {
          historyBoundaryMessage.value = 'Instrument details are unavailable; cached local chart bars remain visible.'
          isLoading.value = false
          return
        }
        if (localResult && !localResult.error && localResult.mapped?.length) {
          publishLocalBars(localResult.mapped)
          historyBoundaryMessage.value = 'Instrument details are unavailable; cached local chart bars remain visible.'
          return
        }
        error.value = `Instrument "${sym.toUpperCase()}" was not found.`
        isLoading.value = false
        return
      }

      const indicatorsPromise = fetchIndicatorsForInstrument(loadedInstrument.id, localOnly ? 'high' : undefined)
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
      if (historyRetryAt.value && Date.parse(historyRetryAt.value) > Date.now()) {
        historyBoundaryMessage.value = `Older history is temporarily held; try again after ${new Date(historyRetryAt.value).toLocaleTimeString()}.`
        return
      }
      if (!bars.value.length) return
      if (basketIdFromSymbol(symbol.value) != null) {
        hasReachedStart.value = true
        return
      }

      const oldestTs = bars.value[0].ts
      const sym = symbol.value
      const tf  = timeframe.value
      const type = barType.value
      const currentTransformParams = transformParams.value
      const cursorKey = `${chartLoadScopeKey(sym, tf, type, localOnlyMode.value, currentTransformParams)}|${oldestTs}`
      if (noProgressHistoryCursor === cursorKey) {
        historyBoundaryMessage.value = `No new saved bars were confirmed for older ${tf} history for ${sym}. Refresh chart data before trying this range again.`
        return
      }

      isLoadingMore.value = true
      historyBoundaryMessage.value = ''
      historyRetryAt.value = null
      const historyController = new AbortController()
      olderHistoryAbortController?.abort()
      olderHistoryAbortController = historyController
      const generation = _loadGeneration
      try {
        // The cursor is an explicit user pan. Re-read it locally instead of
        // trusting a completed cached response that may have produced no new
        // bars on the prior attempt.
        let mapped = await fetchBarsPage(sym, tf, { before: oldestTs, localOnly: localOnlyMode.value, type, transformParams: currentTransformParams, fresh: true })
        if (_loadGeneration !== generation || symbol.value !== sym || timeframe.value !== tf || barType.value !== type) return
        if (!mapped.length && localOnlyMode.value) {
          isFetchingHistory.value = true
          historyBoundaryMessage.value = `Checking older ${tf} history for ${sym}…`
          const defaultWindow = defaultHistoryRange(tf)
          const range = olderHistoryRange(tf, oldestTs, undefined, defaultWindow.start)
          const outcome = await acquireSelectedHistory(
            sym,
            tf,
            true,
            { ...range, timeframe: tf, adjusted: true },
            (stage, retryAt) => {
              if (_loadGeneration !== generation || symbol.value !== sym || timeframe.value !== tf) return
              historyBoundaryMessage.value = stage === 'waiting'
                ? `Waiting to retry older ${tf} history for ${sym} after ${new Date(retryAt!).toLocaleTimeString()}…`
                : stage === 'coverage'
                  ? `Checking saved ${tf} history for ${sym}…`
                  : stage === 'identity'
                    ? `Confirming ${sym} before loading older history…`
                    : `Requesting older ${tf} history for ${sym}…`
            },
            () => _loadGeneration === generation && symbol.value === sym && timeframe.value === tf && barType.value === type,
            undefined,
            { signal: historyController.signal },
          )
          if (_loadGeneration !== generation || symbol.value !== sym || timeframe.value !== tf || barType.value !== type
            || outcome.kind === 'superseded') return
          if (outcome.kind === 'identity-unavailable') {
            historyRetryAt.value = outcome.retryAt ?? null
            historyBoundaryMessage.value = outcome.status === 'held'
              ? `Older ${tf} history for ${sym} is temporarily held${outcome.retryAt ? `; try again after ${new Date(outcome.retryAt).toLocaleTimeString()}` : ''}. The current chart remains available.`
              : `Older ${tf} history for ${sym} is unavailable because its identity could not be confirmed.`
            hasReachedStart.value = false
            return
          }
          if (outcome.kind === 'admission-held') {
            historyBoundaryMessage.value = `Older ${tf} history for ${sym} is temporarily held; the current chart remains available.`
            hasReachedStart.value = false
            return
          }
          if (outcome.kind === 'admission-unavailable') {
            historyBoundaryMessage.value = `The allowed older ${tf} history window for ${sym} could not be confirmed.`
            hasReachedStart.value = false
            return
          }
          if (outcome.kind === 'coverage-unavailable') {
            noProgressHistoryCursor = cursorKey
            historyBoundaryMessage.value = `Saved older ${tf} history coverage for ${sym} could not be confirmed; refresh chart data before checking this range again.`
            hasReachedStart.value = false
            return
          }
          if (outcome.kind === 'at-earliest-bound') {
            historyRetryAt.value = null
            historyBoundaryMessage.value = `The available ${tf} history for ${sym} begins ${new Date(outcome.earliestStart).toLocaleDateString()}.`
            hasReachedStart.value = true
            return
          }
          if (outcome.kind === 'already-covered') {
            noProgressHistoryCursor = cursorKey
            historyBoundaryMessage.value = `No older ${tf} bars were returned for ${sym}; refresh chart data before checking this range again.`
            hasReachedStart.value = false
            return
          }
          if (outcome.result.status === 'held' || outcome.result.status === 'failed' || outcome.result.status === 'no_data') {
            historyRetryAt.value = outcome.result.retry_at
              ?? outcome.result.source_outcomes.find(source => source.retry_at)?.retry_at
              ?? null
            historyBoundaryMessage.value = outcome.result.status === 'held'
              ? `Older ${tf} history for ${sym} is temporarily held${historyRetryAt.value ? `; try again after ${new Date(historyRetryAt.value).toLocaleTimeString()}` : ''}. The current chart remains available.`
              : outcome.result.status === 'no_data'
                ? `No older ${tf} history is available for ${sym}.`
                : `Older ${tf} history for ${sym} could not be loaded.`
            hasReachedStart.value = outcome.result.status === 'no_data'
            return
          }
          mapped = await fetchBarsPage(sym, tf, { before: oldestTs, localOnly: true, type, transformParams: currentTransformParams, fresh: true })
          if (_loadGeneration !== generation || symbol.value !== sym || timeframe.value !== tf || barType.value !== type) return
          if (!mapped.length) {
            noProgressHistoryCursor = cursorKey
            historyBoundaryMessage.value = `The older ${tf} request completed without new saved bars for ${sym}; refresh chart data before trying this range again.`
            hasReachedStart.value = false
            return
          }
          historyBoundaryMessage.value = outcome.result.status === 'partial'
            ? `Older ${tf} history is partially available for ${sym}; more may be requested as you navigate.`
            : `Loaded older ${tf} history for ${sym}.`
        }
        if (!mapped.length) {
          hasReachedStart.value = !localOnlyMode.value
          return
        }
        const existingTimestamps = new Set(bars.value.map(bar => bar.ts))
        const distinctOlderBars = mapped.filter(bar => !existingTimestamps.has(bar.ts))
        if (!distinctOlderBars.length) {
          noProgressHistoryCursor = cursorKey
          historyBoundaryMessage.value = `The older ${tf} request returned no new saved bars for ${sym}; refresh chart data before trying this range again.`
          hasReachedStart.value = false
          return
        }
        bars.value = [...distinctOlderBars, ...bars.value]
        noProgressHistoryCursor = null
        // A short local page means the next explicit pan may cross into a
        // provider-admitted older slice. Do not treat page size as exhaustion.
        hasReachedStart.value = false
      } catch {
        if (_loadGeneration === generation && symbol.value === sym && timeframe.value === tf && barType.value === type) {
          historyBoundaryMessage.value = `Older ${tf} history for ${sym} could not be checked; the current chart remains available.`
          hasReachedStart.value = false
        }
      } finally {
        if (_loadGeneration === generation && symbol.value === sym && timeframe.value === tf && barType.value === type) {
          isFetchingHistory.value = false
          isLoadingMore.value = false
        }
        if (olderHistoryAbortController === historyController) olderHistoryAbortController = null
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
      isLoading, loading: isLoading, isLoadingMore, hasReachedStart, historyBoundaryMessage, historyRetryAt, error, isFetchingHistory, uplotData,
      selectedIndicatorIndex, editRequestIndicatorIndex,
      indicatorEditGeneration,
      loadBars, refreshLocalBars, loadMoreBars, loadInstrument,
      setBarType, fetchLatestBars,
      setIndicators, addIndicator, removeIndicator, updateIndicator, reorderIndicators,
      selectIndicator, requestEditIndicator,
      saveIndicatorsForInstrument,
      resetForAuthSessionBoundary,
    }
  })
}

// ── Public API ─────────────────────────────────────────────────────────────────

// The singleton stores map lets us lazily create per-panel store definitions.
const _storeMap = new Map<string, ReturnType<typeof createChartStore>>()
const _mountedWorkstationPanelRefresh = new Map<string, WorkstationPanelChartRefresh>()

/** Register one mounted Workstation chart component for post-acquisition local refreshes. */
export function registerWorkstationPanelChartRefresh(
  panelId: string,
  registration: WorkstationPanelChartRefresh,
): () => void {
  _mountedWorkstationPanelRefresh.set(panelId, registration)
  return () => {
    if (_mountedWorkstationPanelRefresh.get(panelId) === registration) {
      _mountedWorkstationPanelRefresh.delete(panelId)
    }
  }
}

/** Refresh only mounted chart panels that still display the acquired local scope. */
export async function refreshMountedWorkstationChartPanels(
  symbol: string,
  timeframe: Timeframe,
  isCurrent: () => boolean = () => true,
): Promise<void> {
  const normalizedSymbol = symbol.trim().toUpperCase()
  if (!normalizedSymbol || !isCurrent()) return
  const matching = [..._mountedWorkstationPanelRefresh.values()]
    .filter(panel => isCurrent() && panel.matches(normalizedSymbol, timeframe))
  await Promise.allSettled(matching.map(async panel => {
    if (isCurrent() && panel.matches(normalizedSymbol, timeframe)) {
      await panel.refresh(normalizedSymbol, timeframe, isCurrent)
    }
  }))
}

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
