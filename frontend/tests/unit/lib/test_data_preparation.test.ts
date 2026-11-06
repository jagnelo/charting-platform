import { describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'
import { DataEnsureRequest, DataEnsureResponse, DataPreparationCoordinator, preparationStatusMessage } from '@/lib/dataPreparation'

const baseTime = '2026-11-06T12:00:00.000Z'
const request: DataEnsureRequest = { target: { kind: 'instrument', symbol: 'SPY' }, timeframe: 'D1', datasets: ['identity', 'history'] }

function response(status: DataEnsureResponse['status'], version: number, overrides: Partial<DataEnsureResponse> = {}): DataEnsureResponse {
  return {
    request_id: 'request-1', status, created_at: baseTime, updated_at: baseTime, version,
    target: { kind: 'instrument', symbol: 'SPY' }, dependencies: [], completed: status === 'ready' ? 2 : 0,
    total: 2, last_progress_at: baseTime, ...overrides,
  }
}

function coordinator(client: { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }, pollInterval = 1, now = Date.now) {
  return new DataPreparationCoordinator(client as unknown as typeof api, pollInterval, now)
}

describe('DataPreparationCoordinator', () => {
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

  it('rejects contradictory ready progress instead of presenting success', async () => {
    const client = { post: vi.fn().mockResolvedValue(response('ready', 1, { completed: 1, total: 2 })), get: vi.fn() }
    const service = coordinator(client)

    await expect(service.ensure(request)).rejects.toThrow('reported ready before all dependencies completed')
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
