export interface TimedRequestObservation {
  path: string
  startTime: number | undefined
}

/** Inject before navigation. Network completion/abort must not erase initiation. */
export function installBrowserRequestObservation(): void {
  const observations: TimedRequestObservation[] = []
  Object.defineProperty(globalThis, '__analysisRequestStarts', { configurable: true, value: observations })
  const observe = (input: RequestInfo | URL) => {
    const value = typeof input === 'string' ? input : 'url' in input ? input.url : input.href
    const path = new URL(value, globalThis.location.href).pathname
    if (path.startsWith('/api/v1/market-groups/') || path.startsWith('/api/v1/analysis/')) {
      observations.push({ path, startTime: performance.timeOrigin + performance.now() })
    }
  }
  const originalFetch = globalThis.fetch
  globalThis.fetch = function (input, init) {
    observe(input)
    return originalFetch.call(globalThis, input, init)
  }
  const urls = new WeakMap<XMLHttpRequest, string | URL>()
  const prototype = XMLHttpRequest.prototype
  const originalOpen = prototype.open
  const originalSend = prototype.send
  prototype.open = function (this: XMLHttpRequest, method: string, url: string | URL, async = true, username?: string | null, password?: string | null) {
    urls.set(this, url)
    return originalOpen.call(this, method, url, async, username, password)
  }
  prototype.send = function (body) {
    const url = urls.get(this)
    if (url !== undefined) observe(url)
    return originalSend.call(this, body)
  }
}

/** Every protocol-observed request still requires browser initiation evidence. */
export function requireObservedRequestCoverage(
  observations: readonly TimedRequestObservation[],
  nativeRequestPaths: readonly string[],
): void {
  const counts = new Map<string, number>()
  for (const { path } of observations) counts.set(path, (counts.get(path) ?? 0) + 1)
  for (const path of nativeRequestPaths) {
    const count = counts.get(path) ?? 0
    if (count === 0) throw new Error(`Unobserved request initiation for ${path}`)
    counts.set(path, count - 1)
  }
}

/** Classify requests by browser-clock initiation time; unknown timing is unsafe. */
export function requestsStartedWhileHidden(
  requests: readonly TimedRequestObservation[],
  hiddenAtEpochMs: number,
): string[] {
  if (!Number.isFinite(hiddenAtEpochMs) || hiddenAtEpochMs <= 0) {
    throw new Error('Hidden transition timestamp must be a positive browser epoch time')
  }

  return requests
    .map(request => {
      const { startTime } = request
      if (typeof startTime !== 'number' || !Number.isFinite(startTime) || startTime <= 0) {
        throw new Error(`Request start time unavailable for ${request.path}`)
      }
      return { path: request.path, startTime }
    })
    .filter(request => request.startTime >= hiddenAtEpochMs)
    .map(request => request.path)
}
