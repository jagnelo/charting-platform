/**
 * Small provider-neutral OHLCV request coordinator for chart surfaces.
 *
 * Multiple docked/pop-out tools can ask for the same canonical series during a
 * symbol or timeframe broadcast. Coalesce the in-flight request and retain a
 * short-lived successful response so linked tools do not fan out identical
 * reads. Callers still own cancellation/generation guards for their surface.
 */
type CacheEntry<T> = { value: T; expiresAt: number }

const inFlight = new Map<string, Promise<unknown>>()
const completed = new Map<string, CacheEntry<unknown>>()
const DEFAULT_TTL_MS = 5_000

export function dedupeOhlcvRequest<T>(
  key: string,
  request: () => Promise<T>,
  ttlMs = DEFAULT_TTL_MS,
  options: { ignoreCompleted?: boolean } = {},
): Promise<T> {
  // An explicit refresh ignores only a settled value. All consumers still
  // join the same pending transport, and its result replaces the shared cache.
  const pending = inFlight.get(key)
  if (pending) return pending as Promise<T>

  const now = Date.now()
  const cached = completed.get(key)
  if (!options.ignoreCompleted && cached && cached.expiresAt > now) {
    return Promise.resolve(cached.value as T)
  }
  if (cached) completed.delete(key)

  const promise = request()
    .then(value => {
      completed.set(key, { value, expiresAt: Date.now() + Math.max(0, ttlMs) })
      return value
    })
    .finally(() => { inFlight.delete(key) })
  inFlight.set(key, promise)
  return promise
}

/** Test/support hook: clear only the process-local coordinator state. */
export function clearOhlcvRequestCache() {
  inFlight.clear()
  completed.clear()
}
