import { describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { DataEnsureRequest, DataEnsureResponse, DataPreparationCoordinator, instrumentHistoryPreparationRequest, isPreparationTimeframe, PreparationDependency, PreparationProgressRefreshQueue, preparationStatusMessage, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'

const baseTime = '2026-11-06T12:00:00.000Z'
const request: DataEnsureRequest = { target: { kind: 'instrument', symbol: 'SPY' }, timeframe: 'D1', datasets: ['identity', 'history'] }

function response(status: DataEnsureResponse['status'], version: number, overrides: Omit<Partial<DataEnsureResponse>, 'dependencies'> & { dependencies?: Array<Partial<PreparationDependency> & Pick<PreparationDependency, 'dependency_id' | 'depends_on' | 'dataset' | 'status' | 'updated_at'>> } = {}): DataEnsureResponse {
  return {
    request_id: 'request-1', status, created_at: baseTime, updated_at: baseTime, version,
    target: { kind: 'instrument', symbol: 'SPY' }, completed: status === 'ready' ? 2 : 0,
    total: 2, last_progress_at: baseTime, ...overrides,
    dependencies: (overrides.dependencies ?? []).map(dependency => ({
      symbol: null, instrument_id: null, requested_start: null, requested_end: null,
      covered_start: null, covered_end: null, reason_code: null, retry_at: null,
      covered_ranges: [], ...dependency,
    })),
  }
}

function coordinator(client: { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }, pollInterval = 1, now = Date.now) {
  return new DataPreparationCoordinator(client as unknown as typeof api, pollInterval, now)
}

describe('DataPreparationCoordinator', () => {
  it('uses the full admitted history default for ordinary selections without a viewport start bound', () => {
    expect(instrumentHistoryPreparationRequest({ kind: 'instrument', symbol: 'XLB' }, 'D1')).toEqual({
      target: { kind: 'instrument', symbol: 'XLB' }, datasets: ['identity', 'profile', 'history'], timeframe: 'D1', adjusted: true,
    })
  })

  it('coalesces duplicate progress and refreshes each newer partial range through completion', async () => {
    const dependency = (coveredEnd: string, updatedAt: string, status: DataEnsureResponse['status'] = 'partial') => ({
      dependency_id: 'history:1:MN', depends_on: [], instrument_id: 1, dataset: 'history' as const, status,
      requested_start: '2023-01-01T00:00:00Z', requested_end: '2026-11-06T00:00:00Z',
      covered_start: '2025-11-01T00:00:00Z', covered_end: coveredEnd,
      reason_code: null, retry_at: null, updated_at: updatedAt,
    })
    const partialOne = response('partial', 2, { dependencies: [dependency('2025-11-15T00:00:00Z', '2026-11-06T12:00:01Z')] })
    const partialTwo = response('partial', 3, { dependencies: [dependency('2025-12-15T00:00:00Z', '2026-11-06T12:00:02Z')] })
    const ready = response('ready', 4, { completed: 1, total: 1, dependencies: [dependency('2026-11-05T00:00:00Z', '2026-11-06T12:00:03Z', 'ready')] })
    const queue = new PreparationProgressRefreshQueue()
    const refreshed: number[] = []
    let releaseFirst!: () => void
    const first = queue.request(partialOne, () => new Promise<void>(resolve => {
      refreshed.push(2)
      releaseFirst = resolve
    }))
    await Promise.resolve()
    const second = queue.request(partialTwo, async () => { refreshed.push(3) })
    const duplicate = queue.request(partialTwo, async () => { refreshed.push(30) })
    expect(shouldRefreshAnalysisProgress(partialOne)).toBe(true)
    expect(queue.isLatest(partialTwo)).toBe(true)
    releaseFirst()
    await Promise.all([first, second, duplicate])
    await queue.request(ready, async () => { refreshed.push(4) })

    expect(refreshed).toEqual([2, 3, 4])
  })

  it('deduplicates concurrent identical requests and publishes durable progress', async () => {
    const client = { post: vi.fn().mockResolvedValue(response('running', 1)), get: vi.fn().mockResolvedValue(response('ready', 2)) }
    const progressA = vi.fn(), progressB = vi.fn()
    const service = coordinator(client)

    const [first, second] = await Promise.all([
      service.ensure(request, { onProgress: progressA }),
      service.ensure({ datasets: ['identity', 'history'], timeframe: 'D1', target: { symbol: 'SPY', kind: 'instrument' } }, { onProgress: progressB }),
    ])

    expect(client.post).toHaveBeenCalledTimes(1)
    expect(client.get).toHaveBeenCalledTimes(1)
    expect(first.status).toBe('ready')
    expect(second.request_id).toBe(first.request_id)
    expect(progressA).toHaveBeenCalledWith(expect.objectContaining({ completed: 0, total: 2 }))
    expect(progressB).toHaveBeenCalledWith(expect.objectContaining({ response: expect.objectContaining({ version: 2 }) }))
  })

  it('waits only until a server-supplied temporary retry time', async () => {
    const retryAt = new Date(Date.now() + 25).toISOString()
    const client = {
      post: vi.fn().mockResolvedValue(response('waiting', 1, { dependencies: [{
        dependency_id: 'history:1:D1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'waiting',
        requested_start: null, requested_end: null, covered_start: null, covered_end: null,
        reason_code: 'provider_quota_admission_denied', retry_at: retryAt, updated_at: baseTime,
      }] })),
      get: vi.fn().mockResolvedValue(response('ready', 2)),
    }
    const service = coordinator(client)
    const started = Date.now()

    const result = await service.ensure(request)

    expect(result.status).toBe('ready')
    expect(Date.now() - started).toBeGreaterThanOrEqual(15)
    expect(client.get).toHaveBeenCalledTimes(1)
  })

  it('returns a waiting state without inventing a retry time', async () => {
    const client = { post: vi.fn().mockResolvedValue(response('waiting', 1, { dependencies: [{
      dependency_id: 'history:1:D1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'waiting',
      requested_start: null, requested_end: null, covered_start: null, covered_end: null,
      reason_code: 'manual_hold', retry_at: null, updated_at: baseTime,
    }] })), get: vi.fn() }
    const service = coordinator(client)

    const result = await service.ensure(request)

    expect(result.status).toBe('waiting')
    expect(client.get).not.toHaveBeenCalled()
  })

  it('settles partial identity/history when ETF holdings are unavailable and no durable work remains', async () => {
    const partial = response('partial', 2, {
      completed: 2, total: 3, has_pending_work: false,
      dependencies: [
        { dependency_id: 'identity:7', depends_on: [], instrument_id: 7, symbol: 'SPY', dataset: 'identity', status: 'ready', updated_at: baseTime },
        { dependency_id: 'history:7:D1', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY', dataset: 'history', status: 'ready', updated_at: baseTime,
          covered_ranges: [{ start_at: '2025-01-01T00:00:00Z', end_at: '2026-11-06T00:00:00Z', data_source_id: 4, market_series_id: 9,
            adjustment_basis: 'split_dividend', adjustment_version: 'v1', is_adjusted: true }] },
        { dependency_id: 'holdings:7', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY', dataset: 'holdings', status: 'unavailable', updated_at: baseTime,
          reason_code: 'holdings_not_supported' },
      ],
    })
    const client = { post: vi.fn().mockResolvedValue(partial), get: vi.fn() }
    const progress = vi.fn()

    await expect(coordinator(client).ensure(request, { onProgress: progress })).resolves.toMatchObject({
      status: 'partial', has_pending_work: false,
      dependencies: expect.arrayContaining([expect.objectContaining({ dataset: 'history', covered_ranges: [expect.objectContaining({ market_series_id: 9 })] })]),
    })
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ response: partial }))
    expect(client.get).not.toHaveBeenCalled()
  })

  it('settles incomplete coverage when no accepted jobs remain instead of polling forever', async () => {
    const partial = response('partial', 2, {
      has_pending_work: false,
      dependencies: [{ dependency_id: 'history:7:D1', depends_on: [], instrument_id: 7, symbol: 'SPY',
        dataset: 'history', status: 'partial', updated_at: baseTime,
        requested_start: '2021-01-01T00:00:00Z', requested_end: '2026-11-06T00:00:00Z',
        covered_ranges: [{ start_at: '2025-01-01T00:00:00Z', end_at: '2026-11-06T00:00:00Z', data_source_id: 4, market_series_id: 9,
          adjustment_basis: 'split_dividend', adjustment_version: 'v1', is_adjusted: true }] }],
    })
    const client = { post: vi.fn().mockResolvedValue(partial), get: vi.fn() }

    await expect(coordinator(client).ensure(request)).resolves.toMatchObject({ status: 'partial', has_pending_work: false })
    expect(client.get).not.toHaveBeenCalled()
  })

  it('continues polling while older history chunks remain accepted and queued', async () => {
    const queued = response('partial', 2, {
      has_pending_work: true,
      dependencies: [{ dependency_id: 'history:7:D1', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY',
        dataset: 'history', status: 'partial', updated_at: baseTime, covered_ranges: [] }],
    })
    const ready = response('ready', 3, { completed: 2, total: 2, has_pending_work: false,
      dependencies: [{ dependency_id: 'history:7:D1', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY',
        dataset: 'history', status: 'ready', updated_at: baseTime,
        covered_ranges: [{ start_at: '2024-11-06T00:00:00Z', end_at: '2026-11-06T00:00:00Z', data_source_id: 4, market_series_id: 9,
          adjustment_basis: 'split_dividend', adjustment_version: 'v1', is_adjusted: true }] }] })
    const client = { post: vi.fn().mockResolvedValue(queued), get: vi.fn().mockResolvedValue(ready) }
    const progress = vi.fn()

    await expect(coordinator(client).ensure(request, { onProgress: progress })).resolves.toMatchObject({ status: 'ready' })
    expect(client.get).toHaveBeenCalledTimes(1)
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ response: queued }))
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ response: ready }))
  })

  it('waits for a known deferred dependency when ready data is already available', async () => {
    const retryAt = new Date(Date.now() + 30).toISOString()
    const partial = response('partial', 2, {
      has_pending_work: true,
      dependencies: [
        { dependency_id: 'history:7:D1', depends_on: [], instrument_id: 7, symbol: 'SPY', dataset: 'history', status: 'ready', updated_at: baseTime },
        { dependency_id: 'holdings:7', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY', dataset: 'holdings', status: 'waiting', updated_at: baseTime,
          reason_code: 'provider_quota_admission_denied', retry_at: retryAt },
      ],
    })
    const settledPartial = response('partial', 3, { completed: 1, total: 2, has_pending_work: false,
      dependencies: partial.dependencies.map(item => item.dataset === 'holdings' ? { ...item, status: 'unavailable', retry_at: null } : item) })
    const client = { post: vi.fn().mockResolvedValue(partial), get: vi.fn().mockResolvedValue(settledPartial) }
    const started = Date.now()

    await expect(coordinator(client).ensure(request)).resolves.toMatchObject({ status: 'partial', has_pending_work: false })
    expect(Date.now() - started).toBeGreaterThanOrEqual(20)
    expect(client.get).toHaveBeenCalledTimes(1)
  })

  it('waits on a partial history response when its only remaining older work is deferred', async () => {
    vi.useFakeTimers()
    try {
      let now = Date.parse(baseTime)
      const retryAt = new Date(now + 60_000).toISOString()
      const deferred = response('partial', 2, { has_pending_work: true, completed: 1, total: 2, dependencies: [{
        dependency_id: 'history:7:D1', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY',
        dataset: 'history', status: 'partial', updated_at: baseTime,
        requested_start: '2024-11-06T00:00:00Z', requested_end: '2026-11-06T00:00:00Z',
        covered_ranges: [{ start_at: '2025-11-06T00:00:00Z', end_at: '2026-11-06T00:00:00Z', data_source_id: 4, market_series_id: 9,
          adjustment_basis: 'split_dividend', adjustment_version: 'v1', is_adjusted: true }],
        reason_code: 'provider_quota_admission_denied', retry_at: retryAt,
      }] })
      const finished = response('partial', 3, { has_pending_work: false, completed: 1, total: 2, dependencies: deferred.dependencies })
      const client = { post: vi.fn().mockResolvedValue(deferred), get: vi.fn().mockResolvedValue(finished) }
      const progress = vi.fn()
      const resultPromise = coordinator(client, 5, () => now).ensure(request, { onProgress: progress })
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()

      expect(progress).toHaveBeenCalledWith(expect.objectContaining({ response: deferred }))
      expect(progress.mock.calls[0]?.[0].response.dependencies[0]?.covered_ranges).toHaveLength(1)
      expect(client.get).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(59_999)
      expect(client.get).not.toHaveBeenCalled()
      now = Date.parse(retryAt)
      await vi.advanceTimersByTimeAsync(1)

      await expect(resultPromise).resolves.toMatchObject({ status: 'partial', has_pending_work: false })
      expect(client.get).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps polling runnable history when a separate chunk is deferred', async () => {
    vi.useFakeTimers()
    try {
      const now = Date.parse(baseTime)
      const retryAt = new Date(now + 60_000).toISOString()
      const mixed = response('partial', 2, { has_pending_work: true, dependencies: [
        { dependency_id: 'history:7:D1:older', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY',
          dataset: 'history', status: 'partial', updated_at: baseTime, reason_code: 'provider_quota_admission_denied', retry_at: retryAt },
        { dependency_id: 'history:7:D1:current', depends_on: ['identity:7'], instrument_id: 7, symbol: 'SPY',
          dataset: 'history', status: 'queued', updated_at: baseTime, retry_at: null },
      ] })
      const ready = response('ready', 3, { has_pending_work: false })
      const client = { post: vi.fn().mockResolvedValue(mixed), get: vi.fn().mockResolvedValue(ready) }
      const resultPromise = coordinator(client, 5, () => now).ensure(request)
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
      expect(client.get).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(5)

      await expect(resultPromise).resolves.toMatchObject({ status: 'ready' })
      expect(client.get).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps a shared request alive while another subscriber cancels', async () => {
    let resolvePost: ((result: DataEnsureResponse) => void) | null = null
    const client = {
      post: vi.fn(() => new Promise<DataEnsureResponse>(resolve => { resolvePost = resolve })),
      get: vi.fn().mockResolvedValue(response('ready', 2)),
    }
    const service = coordinator(client)
    const cancelFirst = new AbortController()
    const first = service.ensure(request, { signal: cancelFirst.signal })
    const second = service.ensure(request)
    cancelFirst.abort()
    resolvePost?.(response('running', 1))

    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    await expect(second).resolves.toMatchObject({ status: 'ready' })
    expect(client.post).toHaveBeenCalledTimes(1)
    expect(client.get).toHaveBeenCalledTimes(1)
  })

  it('cancels old-session observers and does not coalesce the next user into their request', async () => {
    let resolveOld!: (result: DataEnsureResponse) => void
    const client = {
      post: vi.fn()
        .mockImplementationOnce(() => new Promise<DataEnsureResponse>(resolve => { resolveOld = resolve }))
        .mockResolvedValueOnce(response('ready', 1)),
      get: vi.fn(),
    }
    const service = coordinator(client)
    const oldUser = service.ensure(request)
    await Promise.resolve()

    service.cancelAll()
    await expect(oldUser).rejects.toMatchObject({ name: 'AbortError' })

    await expect(service.ensure(request)).resolves.toMatchObject({ status: 'ready' })
    expect(client.post).toHaveBeenCalledTimes(2)

    // A transport mock may settle after abort. It must not reattach to or
    // settle the next user's independent request entry.
    resolveOld(response('ready', 1))
    await Promise.resolve()
    expect(client.post).toHaveBeenCalledTimes(2)
  })

  it('rejects contradictory ready progress instead of presenting success', async () => {
    const client = { post: vi.fn().mockResolvedValue(response('ready', 1, { completed: 1, total: 2 })), get: vi.fn() }
    const service = coordinator(client)

    await expect(service.ensure(request)).rejects.toThrow('reported ready before all dependencies completed')
    expect(client.get).not.toHaveBeenCalled()
  })

  it('preserves Provider dependency symbols and exact covered-range adjustment lineage', async () => {
    const covered = response('partial', 2, { dependencies: [{
      dependency_id: 'history:7:D1', depends_on: ['identity:SPY'], instrument_id: 7, symbol: 'SPY',
      dataset: 'history', status: 'partial', updated_at: baseTime,
      covered_ranges: [{ start_at: '2025-01-01T00:00:00Z', end_at: '2025-02-01T00:00:00Z',
        data_source_id: 4, market_series_id: 9, adjustment_basis: 'split_dividend',
        adjustment_version: 'v1', is_adjusted: true }],
    }] })
    expect(covered.request_id).toBe('request-1')
    expect(covered.dependencies[0]).toMatchObject({ symbol: 'SPY', covered_ranges: [{ market_series_id: 9 }] })
    const client = { post: vi.fn().mockResolvedValue(covered), get: vi.fn().mockResolvedValue(response('ready', 3, { completed: 1, total: 1, dependencies: covered.dependencies })) }

    const ensured = await coordinator(client).ensure(request)
    expect(client.post).toHaveBeenCalledWith('/data/ensure', request, expect.any(Object))
    expect(ensured).toMatchObject({
      dependencies: [{ symbol: 'SPY', covered_ranges: [{ market_series_id: 9, adjustment_basis: 'split_dividend', is_adjusted: true }] }],
    })
  })

  it('rejects malformed covered-range lineage instead of presenting progress as valid', async () => {
    const malformed = response('partial', 2, { dependencies: [{
      dependency_id: 'history:7:D1', depends_on: [], instrument_id: 7, symbol: 'SPY',
      dataset: 'history', status: 'partial', updated_at: baseTime,
      covered_ranges: [{ start_at: 'not-a-time', end_at: '2025-02-01T00:00:00Z',
        data_source_id: null, market_series_id: null, adjustment_basis: '',
        adjustment_version: '', is_adjusted: true }],
    }] })
    const client = { post: vi.fn().mockResolvedValue(malformed), get: vi.fn() }

    await expect(coordinator(client).ensure(request)).rejects.toThrow('invalid covered range lineage')
    expect(client.get).not.toHaveBeenCalled()
  })

  it('translates structured source reasons into plain recovery feedback without exposing codes', () => {
    const waiting = response('waiting', 1, { dependencies: [{
      dependency_id: 'history:1:D1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'waiting',
      requested_start: null, requested_end: null, covered_start: null, covered_end: null,
      reason_code: 'provider_quota_admission_denied', retry_at: '2026-11-06T12:01:00.000Z', updated_at: baseTime,
    }] })
    const held = response('unavailable', 1, { dependencies: [{
      dependency_id: 'history:1:D1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'unavailable',
      requested_start: null, requested_end: null, covered_start: null, covered_end: null,
      reason_code: 'timeframes_not_entitled', retry_at: null, updated_at: baseTime,
    }] })
    const unresolved = response('unavailable', 1, { dependencies: [{
      dependency_id: 'identity:SPY', depends_on: [], instrument_id: null, dataset: 'identity', status: 'unavailable',
      requested_start: null, requested_end: null, covered_start: null, covered_end: null,
      reason_code: 'canonical_identity_unresolved', retry_at: null, updated_at: baseTime,
    }] })

    const waitingMessage = preparationStatusMessage(waiting, Date.parse(baseTime))
    const heldMessage = preparationStatusMessage(held, Date.parse(baseTime))

    expect(waitingMessage).toContain('request capacity')
    expect(waitingMessage).toContain('will resume at')
    expect(waitingMessage).not.toContain('provider_quota_admission_denied')
    expect(heldMessage).toContain('entitlement')
    expect(heldMessage).not.toContain('timeframes_not_entitled')
    expect(preparationStatusMessage(unresolved, Date.parse(baseTime))).toContain('identity and listing details')
    expect(preparationStatusMessage(response('unavailable', 1, { dependencies: [{
      dependency_id: 'history:1:D1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'unavailable',
      requested_start: null, requested_end: null, covered_start: null, covered_end: null,
      reason_code: 'provider_source_unavailable', retry_at: null, updated_at: baseTime,
    }] }), Date.parse(baseTime))).toContain('reviewed data source')
    expect(preparationStatusMessage(waiting, Date.parse(baseTime))).not.toContain('Try again')
  })

  it('accepts only the Provider-owned timeframe enum, including its supported annual period', async () => {
    const client = { post: vi.fn().mockResolvedValue(response('ready', 1)), get: vi.fn() }
    const service = coordinator(client)

    expect(isPreparationTimeframe('Y1')).toBe(true)
    expect(isPreparationTimeframe('Q1')).toBe(false)
    await expect(service.ensure({ ...request, timeframe: 'Y1' })).resolves.toMatchObject({ status: 'ready' })
    await expect(service.ensure({ ...request, timeframe: 'Q1' as any })).rejects.toThrow('timeframe is not supported')
    expect(client.post).toHaveBeenCalledTimes(1)
    expect(client.post).toHaveBeenCalledWith('/data/ensure', expect.objectContaining({ timeframe: 'Y1' }), expect.any(Object))
  })

  it('rejects ambiguous identities and invalid ranges before creating a request', async () => {
    const client = { post: vi.fn(), get: vi.fn() }
    const service = coordinator(client)

    await expect(service.ensure({ target: { kind: 'instrument', instrument_id: 7, symbol: 'SPY' } as any })).rejects.toThrow('exactly one instrument identity')
    await expect(service.ensure({ ...request, start_at: '2026-11-07T00:00:00Z', end_at: '2026-11-06T00:00:00Z' })).rejects.toThrow('must not be after')
    await expect(service.ensure({ ...request, start_at: '2026-11-06' })).rejects.toThrow('must include a timezone')
    expect(client.post).not.toHaveBeenCalled()
  })
})
