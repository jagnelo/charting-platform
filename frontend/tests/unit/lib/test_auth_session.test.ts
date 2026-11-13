import { createPinia, defineStore, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it } from 'vitest'
import { beginAuthSessionBoundary, captureAuthSession, clearUserScopedPiniaStores, installAuthSessionCleanup } from '@/lib/authSession'

describe('authenticated client session boundary', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('aborts the prior session and recreates private Pinia stores from fresh defaults while retaining auth', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const useAuth = defineStore('auth', () => ({ user: ref('user-a') }))
    const usePrivateWorkspace = defineStore('private-workspace', () => ({ layout: ref('default-layout') }))
    const auth = useAuth(pinia)
    const previousWorkspace = usePrivateWorkspace(pinia)
    previousWorkspace.layout = 'user-a-layout'
    const previousSession = captureAuthSession()

    beginAuthSessionBoundary()
    clearUserScopedPiniaStores(pinia)

    expect(previousSession.signal.aborted).toBe(true)
    expect(auth.user).toBe('user-a')
    expect(pinia._s.has('private-workspace')).toBe(false)
    expect(pinia.state.value['private-workspace']).toBeUndefined()
    const nextWorkspace = usePrivateWorkspace(pinia)
    expect(nextWorkspace).not.toBe(previousWorkspace)
    expect(nextWorkspace.layout).toBe('default-layout')
  })

  it('clears cached research and note results with workspace and drawing stores at the application boundary', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const queryClient = new QueryClient()
    const useAuth = defineStore('auth', () => ({ user: ref('user-a') }))
    const useWorkspace = defineStore('workspace', () => ({ snapshot: ref('empty') }))
    const useDrawings = defineStore('drawings', () => ({ byInstrument: ref<Record<string, string[]>>({}) }))
    const auth = useAuth(pinia)
    const workspace = useWorkspace(pinia)
    const drawings = useDrawings(pinia)
    workspace.snapshot = 'workspace-a'
    drawings.byInstrument = { '7': ['drawing-a'] }
    queryClient.setQueryData(['workstation', 'research-runs'], [{ id: 'run-a' }])
    queryClient.setQueryData(['workstation', 'instrument-note', 7], { content: 'note-a' })

    const stop = installAuthSessionCleanup(queryClient, pinia)
    beginAuthSessionBoundary()
    stop()

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    expect(pinia._s.has('workspace')).toBe(false)
    expect(pinia._s.has('drawings')).toBe(false)
    expect(pinia._s.has('auth')).toBe(true)
    expect(auth.user).toBe('user-a')
    expect(workspace.snapshot).toBe('workspace-a')
    expect(drawings.byInstrument['7']).toEqual(['drawing-a'])
    expect(useWorkspace(pinia).snapshot).toBe('empty') // factory default, not the prior instance
    expect(useWorkspace(pinia)).not.toBe(workspace)
  })
})
