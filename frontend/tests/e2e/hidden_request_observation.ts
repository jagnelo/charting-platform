export interface TimedRequestObservation {
  path: string
  startTime: number | undefined
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
