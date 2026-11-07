import { readonly, shallowRef } from 'vue'
import type { Pinia } from 'pinia'
import type { QueryClient } from '@tanstack/vue-query'

const sessionEpoch = shallowRef(0)
const epochView = readonly(sessionEpoch)
const boundaryListeners = new Set<(epoch: number) => void>()
let sessionController = new AbortController()

export interface AuthSessionSnapshot {
  epoch: number
  signal: AbortSignal
}

export class AuthSessionChangedError extends Error {
  constructor() {
    super('The authenticated session changed while this request was in flight.')
    this.name = 'AbortError'
  }
}

export function captureAuthSession(): AuthSessionSnapshot {
  return { epoch: sessionEpoch.value, signal: sessionController.signal }
}

export function currentAuthSessionEpoch() {
  return sessionEpoch.value
}

export function authSessionEpochView() {
  return epochView
}

export function assertAuthSessionCurrent(snapshot: AuthSessionSnapshot): void {
  if (snapshot.epoch !== sessionEpoch.value || snapshot.signal.aborted) throw new AuthSessionChangedError()
}

export function onAuthSessionBoundary(listener: (epoch: number) => void): () => void {
  boundaryListeners.add(listener)
  return () => boundaryListeners.delete(listener)
}

/**
 * Cancel private in-flight work and prevent responses started by the previous
 * authenticated user from being committed into the next user's client state.
 */
export function beginAuthSessionBoundary(): number {
  sessionController.abort()
  sessionController = new AbortController()
  sessionEpoch.value += 1
  for (const listener of [...boundaryListeners]) listener(sessionEpoch.value)
  return sessionEpoch.value
}

/**
 * Remove every instantiated user-scoped Pinia store and its serialized state.
 * The auth store is retained so the login/logout transition can finish; stores
 * used by routed content are recreated from defaults after the route remounts.
 */
export function clearUserScopedPiniaStores(pinia: Pinia): void {
  const stores = (pinia as Pinia & { _s: Map<string, { $id: string; $dispose(): void }> })._s
  for (const [id, store] of [...stores]) {
    if (id === 'auth') continue
    const reset = (store as typeof store & { resetForAuthSessionBoundary?: () => void }).resetForAuthSessionBoundary
    store.$dispose()
    reset?.()
    delete pinia.state.value[id]
  }
}

/** Install the same private-cache boundary used by the application bootstrap. */
export function installAuthSessionCleanup(queryClient: Pick<QueryClient, 'clear'>, pinia: Pinia): () => void {
  return onAuthSessionBoundary(() => {
    queryClient.clear()
    clearUserScopedPiniaStores(pinia)
  })
}
