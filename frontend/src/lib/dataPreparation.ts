import { api } from '@/lib/api'

export type PreparationDataset = 'identity' | 'profile' | 'history' | 'holdings' | 'fundamentals'
export type PreparationTimeframe = 'M1' | 'M5' | 'M15' | 'M30' | 'H1' | 'H2' | 'H4' | 'H12' | 'D1' | 'W1' | 'MN' | 'Y1'
export type PreparationStatus = 'queued' | 'running' | 'partial' | 'ready' | 'waiting' | 'unavailable' | 'failed'

export type PreparationInstrument =
  | { kind: 'instrument'; instrument_id: number; symbol?: never }
  | { kind: 'instrument'; symbol: string; instrument_id?: never }
export type PreparationTarget =
  | PreparationInstrument
  | { kind: 'market_group'; group_key: string }
  | { kind: 'family'; family_key: string }

interface PreparationAnalysisParameters {
  lookback?: number
  sampling?: number
  tail_length?: number
  history_length?: number
}
export type PreparationRatioLeg =
  | { instrument_id: number; symbol?: never }
  | { symbol: string; instrument_id?: never }
export type PreparationAnalysis =
  | (PreparationAnalysisParameters & { kind: 'ratio'; legs: [PreparationRatioLeg, PreparationRatioLeg]; benchmark_symbol?: never })
  | (PreparationAnalysisParameters & { kind: 'rrg'; legs?: never; benchmark_symbol?: string })

export interface DataEnsureRequest {
  target: PreparationTarget
  datasets?: PreparationDataset[]
  timeframe?: PreparationTimeframe
  adjusted?: boolean
  start_at?: string | null
  end_at?: string | null
  analysis?: PreparationAnalysis | null
}

export interface PreparationDependency {
  dependency_id: string
  depends_on: string[]
  instrument_id: number | null
  dataset: PreparationDataset
  status: PreparationStatus
  requested_start: string | null
  requested_end: string | null
  covered_start: string | null
  covered_end: string | null
  reason_code: string | null
  retry_at: string | null
  updated_at: string
}

export interface DataEnsureResponse {
  request_id: string
  status: PreparationStatus
  created_at: string
  updated_at: string
  version: number
  target: Record<string, unknown>
  dependencies: PreparationDependency[]
  completed: number
  total: number
  last_progress_at: string
}

export interface PreparationProgress {
  response: DataEnsureResponse
  completed: number
  total: number
  activeDependencies: number
}

export interface PreparationOptions {
  signal?: AbortSignal
  onProgress?: (progress: PreparationProgress) => void
}

const ACTIVE_POLL_MS = 750
const MAX_TIMER_DELAY_MS = 2_147_000_000
const ALL_STATUSES = new Set<PreparationStatus>(['queued', 'running', 'partial', 'ready', 'waiting', 'unavailable', 'failed'])
const TERMINAL_STATUSES = new Set<PreparationStatus>(['ready', 'unavailable', 'failed'])

function abortError(): DOMException {
  return new DOMException('Data preparation was cancelled.', 'AbortError')
}

function stableValue(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableValue).join(',')}]`
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${stableValue(item)}`).join(',')}}`
  }
  return JSON.stringify(value)
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(abortError())
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, Math.min(Math.max(0, milliseconds), MAX_TIMER_DELAY_MS))
    const onAbort = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', onAbort)
      reject(abortError())
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

async function waitUntil(timestamp: number, signal: AbortSignal, now: () => number): Promise<void> {
  while (timestamp > now()) await abortableDelay(timestamp - now(), signal)
}

function responseRetryAt(response: DataEnsureResponse, after: number): number | null {
  const candidates = response.dependencies
    .filter(dependency => dependency.status === 'waiting' && dependency.retry_at)
    .map(dependency => Date.parse(dependency.retry_at!))
    .filter(retryAt => Number.isFinite(retryAt) && retryAt > after)
  return candidates.length ? Math.min(...candidates) : null
}

function validateIdentity(identity: { instrument_id?: number; symbol?: string }, label: string): void {
  const hasId = Number.isInteger(identity.instrument_id) && Number(identity.instrument_id) > 0
  const hasSymbol = typeof identity.symbol === 'string' && identity.symbol.trim().length > 0
  if (hasId === hasSymbol) throw new Error(`${label} must include exactly one instrument identity.`)
}

function validateRequest(request: DataEnsureRequest): void {
  if (request.target.kind === 'instrument') validateIdentity(request.target, 'Preparation target')
  if (request.datasets && new Set(request.datasets).size !== request.datasets.length) {
    throw new Error('Preparation datasets must not contain duplicates.')
  }
  const timestamp = (value: string | null | undefined, label: string): number | null => {
    if (value == null) return null
    if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) throw new Error(`${label} must include a timezone.`)
    const parsed = Date.parse(value)
    if (!Number.isFinite(parsed)) throw new Error(`${label} is invalid.`)
    return parsed
  }
  const start = timestamp(request.start_at, 'Preparation start')
  const end = timestamp(request.end_at, 'Preparation end')
  if (start !== null && end !== null && start > end) throw new Error('Preparation start must not be after its end.')
  const analysis = request.analysis
  if (analysis?.kind === 'ratio') {
    if (analysis.legs.length !== 2) throw new Error('Ratio preparation requires exactly two legs.')
    analysis.legs.forEach((leg, index) => validateIdentity(leg, `Ratio leg ${index + 1}`))
  }
  if (analysis?.kind === 'rrg' && analysis.legs !== undefined) throw new Error('RRG preparation does not accept ratio legs.')
}

function validateResponse(response: DataEnsureResponse, expectedRequestId?: string, previousVersion = 0): void {
  if (!response || typeof response !== 'object' || typeof response.request_id !== 'string' || !response.request_id) {
    throw new Error('Data preparation returned an invalid request identity.')
  }
  if (expectedRequestId && response.request_id !== expectedRequestId) {
    throw new Error('Data preparation returned a different request identity while polling.')
  }
  if (!ALL_STATUSES.has(response.status)) throw new Error('Data preparation returned an unknown request state.')
  if (!Number.isInteger(response.version) || response.version < previousVersion || response.version < 1) {
    throw new Error('Data preparation returned an invalid progress version.')
  }
  if (!Number.isInteger(response.completed) || !Number.isInteger(response.total) || response.completed < 0 || response.total < 0 || response.completed > response.total) {
    throw new Error('Data preparation returned contradictory progress counts.')
  }
  if (!Array.isArray(response.dependencies)) throw new Error('Data preparation omitted dependency progress.')
  if (response.dependencies.some(dependency => !ALL_STATUSES.has(dependency.status))) {
    throw new Error('Data preparation returned an unknown dependency state.')
  }
  if (response.status === 'ready' && response.completed < response.total) {
    throw new Error('Data preparation reported ready before all dependencies completed.')
  }
}

interface Subscriber {
  signal?: AbortSignal
  onProgress?: PreparationOptions['onProgress']
  resolve: (response: DataEnsureResponse) => void
  reject: (error: unknown) => void
  abortListener?: () => void
}

interface InFlightRequest {
  request: DataEnsureRequest
  controller: AbortController
  subscribers: Set<Subscriber>
  promise: Promise<void> | null
}

/** Shared durable preparation lifecycle for charts, groups, and analysis tools. */
export class DataPreparationCoordinator {
  private readonly inFlight = new Map<string, InFlightRequest>()

  constructor(
    private readonly client: typeof api = api,
    private readonly pollIntervalMs = ACTIVE_POLL_MS,
    private readonly now: () => number = Date.now,
  ) {}

  ensure(request: DataEnsureRequest, options: PreparationOptions = {}): Promise<DataEnsureResponse> {
    if (options.signal?.aborted) return Promise.reject(abortError())
    try {
      validateRequest(request)
    } catch (error) {
      return Promise.reject(error)
    }
    const key = stableValue(request)
    let entry = this.inFlight.get(key)
    if (!entry) {
      entry = { request, controller: new AbortController(), subscribers: new Set(), promise: null }
      this.inFlight.set(key, entry)
    }
    const current = entry
    const result = new Promise<DataEnsureResponse>((resolve, reject) => {
      const subscriber: Subscriber = { signal: options.signal, onProgress: options.onProgress, resolve, reject }
      const detach = () => {
        if (!current.subscribers.delete(subscriber)) return
        if (subscriber.abortListener) subscriber.signal?.removeEventListener('abort', subscriber.abortListener)
        if (current.subscribers.size === 0 && this.inFlight.get(key) === current) {
          this.inFlight.delete(key)
          current.controller.abort()
        }
      }
      subscriber.abortListener = () => {
        detach()
        reject(abortError())
      }
      current.subscribers.add(subscriber)
      subscriber.signal?.addEventListener('abort', subscriber.abortListener, { once: true })
      if (subscriber.signal?.aborted) subscriber.abortListener()
    })
    if (!current.promise && current.subscribers.size) {
      current.promise = this.run(current).then(
        response => this.settle(key, current, null, response),
        error => this.settle(key, current, error),
      )
    }
    return result
  }

  private settle(key: string, entry: InFlightRequest, error: unknown, response?: DataEnsureResponse): void {
    for (const subscriber of [...entry.subscribers]) {
      entry.subscribers.delete(subscriber)
      if (subscriber.abortListener) subscriber.signal?.removeEventListener('abort', subscriber.abortListener)
      if (error) subscriber.reject(error)
      else subscriber.resolve(response!)
    }
    if (this.inFlight.get(key) === entry) this.inFlight.delete(key)
  }

  private publish(entry: InFlightRequest, response: DataEnsureResponse): void {
    const progress = {
      response,
      completed: response.completed,
      total: response.total,
      activeDependencies: response.dependencies.filter(dependency => ['queued', 'running', 'partial'].includes(dependency.status)).length,
    }
    for (const subscriber of entry.subscribers) subscriber.onProgress?.(progress)
  }

  private async run(entry: InFlightRequest): Promise<DataEnsureResponse> {
    const signal = entry.controller.signal
    const initial = await this.client.post<DataEnsureResponse>('/data/ensure', entry.request, { signal })
    validateResponse(initial)
    const requestId = initial.request_id
    let response = initial
    let version = initial.version
    let lastWaitDeadline = 0
    this.publish(entry, response)

    while (!TERMINAL_STATUSES.has(response.status)) {
      if (signal.aborted) throw abortError()
      if (response.status === 'waiting') {
        const retryAt = responseRetryAt(response, this.now())
        if (retryAt === null || retryAt <= lastWaitDeadline) return response
        lastWaitDeadline = retryAt
        await waitUntil(retryAt, signal, this.now)
      } else {
        await abortableDelay(this.pollIntervalMs, signal)
      }
      const next = await this.client.get<DataEnsureResponse>(`/data/requests/${encodeURIComponent(requestId)}`, undefined, { signal })
      validateResponse(next, requestId, version)
      version = next.version
      response = next
      this.publish(entry, response)
    }
    return response
  }
}

export const dataPreparationCoordinator = new DataPreparationCoordinator()

/** User-facing status language deliberately omits provider/policy reason codes. */
export function preparationStatusMessage(response: DataEnsureResponse, now = Date.now()): string {
  if (response.status === 'ready') return 'Requested data is ready.'
  const reasonCodes = [...new Set(response.dependencies.map(dependency => dependency.reason_code).filter((code): code is string => Boolean(code)))]
  const reasonMessage = reasonCodes.map(userSafeReasonMessage).find(Boolean)
  if (response.status === 'waiting') {
    const retryAt = responseRetryAt(response, now)
    const reason = reasonMessage ?? 'This data request is temporarily paused.'
    return retryAt === null
      ? `${reason} No automatic retry time is available; your current view remains usable.`
      : `${reason} It will resume at ${new Date(retryAt).toLocaleTimeString()}. Your current view remains usable.`
  }
  if (response.status === 'unavailable') return `${reasonMessage ?? 'Some requested data is unavailable.'} Available results remain usable.`
  if (response.status === 'failed') return `${reasonMessage ?? 'The data request could not be completed.'} Your current view remains usable.`
  return 'Preparing requested data…'
}

function userSafeReasonMessage(reasonCode: string): string | null {
  const code = reasonCode.toLowerCase()
  if (code.includes('quota') || code.includes('capacity')) return 'The data source is temporarily at its request capacity.'
  if (code.includes('credential') || code.includes('api_key') || code.includes('not_configured')) return 'The required data-source credentials are not available.'
  if (code.includes('entitlement') || code.endsWith('_not_entitled')) return 'The current data-source entitlement does not include this request.'
  if (code.includes('identity') || code.includes('instrument') || code.includes('canonical') || code.includes('profile')) return 'The instrument identity and listing details could not be confirmed for this request.'
  if (code.includes('history_depth') || code.includes('history_bound')) return 'The permitted history range could not be confirmed.'
  if (code.includes('no_eligible_history_provider') || code.includes('no_eligible_provider') || code.includes('no_admitted_provider_data')) return 'No reviewed data source can provide this request.'
  if (code.includes('provider') || code.includes('source')) return 'A reviewed data source could not complete this request.'
  return null
}
