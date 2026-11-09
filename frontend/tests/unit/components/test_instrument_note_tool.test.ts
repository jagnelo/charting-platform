import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPut, setPriority } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  setPriority: vi.fn(() => true),
}))
vi.mock('@/lib/api', () => ({
  api: { get: apiGet, put: apiPut },
  setQueuedApiRequestPriority: setPriority,
}))

import InstrumentNoteTool from '@/components/workstation/InstrumentNoteTool.vue'
import { beginAuthSessionBoundary, installAuthSessionCleanup } from '@/lib/authSession'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function mountTool(
  instrumentId = 7,
  symbol = 'SPY',
  options: { queryClient?: QueryClient; requestPriority?: 'auto' | 'high' } = {},
) {
  const queryClient = options.queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 60_000 } } })
  const wrapper = mount(InstrumentNoteTool, {
    props: { instrumentId, symbol, requestPriority: options.requestPriority ?? 'auto' },
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { wrapper, queryClient }
}

describe('InstrumentNoteTool draft lifecycle', () => {
  beforeEach(() => {
    apiGet.mockReset().mockResolvedValue(null)
    apiPut.mockReset()
    setPriority.mockReset().mockReturnValue(true)
  })

  async function waitForLoaded(wrapper: ReturnType<typeof mountTool>['wrapper']) {
    await vi.waitFor(() => expect(wrapper.get('.note-tool__status').text()).toBe('SPY · No note'))
  }

  async function debounceSave() {
    await new Promise(resolve => setTimeout(resolve, 575))
  }

  it('promotes the existing hidden Notes read when a visible Notes panel joins its pending query', async () => {
    const pendingRead = deferred<null>()
    apiGet.mockReturnValue(pendingRead.promise)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 60_000 } } })
    const hidden = mountTool(7, 'SPY', { queryClient, requestPriority: 'auto' })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))

    const visible = mountTool(7, 'SPY', { queryClient, requestPriority: 'high' })
    await flushPromises()

    // Both panels share one pending queryFn/HTTP request; the visible join
    // promotes that already-queued request instead of issuing a duplicate.
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(setPriority).toHaveBeenCalledWith('instrument-note:7', 'high')

    pendingRead.resolve(null)
    await waitForLoaded(hidden.wrapper)
    await waitForLoaded(visible.wrapper)
    hidden.wrapper.unmount()
    visible.wrapper.unmount()
    queryClient.clear()
  })

  it('promotes a pending note read after fallback canonical identity resolves and priority becomes visible', async () => {
    const identity = deferred<{ id: number; symbol: string }>()
    const note = deferred<null>()
    apiGet.mockReturnValueOnce(identity.promise).mockReturnValueOnce(note.promise)
    const { wrapper, queryClient } = mountTool(null, 'SPY', { requestPriority: 'auto' })

    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet).toHaveBeenNthCalledWith(1, '/instruments/SPY', { canonical_only: true }, { priority: 'high' })
    identity.resolve({ id: 2, symbol: 'SPY' })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
    expect(apiGet.mock.calls[1]?.[0]).toBe('/notes/instruments/2')
    expect(apiGet.mock.calls[1]?.[2]).toMatchObject({ priority: 'auto', queueKey: 'instrument-note:2' })
    expect(setPriority).not.toHaveBeenCalled()

    await wrapper.setProps({ requestPriority: 'high' })
    await flushPromises()
    expect(setPriority).toHaveBeenCalledWith('instrument-note:2', 'high')
    expect(apiGet).toHaveBeenCalledTimes(2)

    note.resolve(null)
    await waitForLoaded(wrapper)
    expect(wrapper.get('textarea').element.disabled).toBe(false)
    wrapper.unmount()
    queryClient.clear()
  })

  it('shows identity resolution while the selected symbol lookup is pending, then loads that symbol note', async () => {
    const identity = deferred<{ id: number; symbol: string }>()
    const note = deferred<null>()
    apiGet.mockReturnValueOnce(identity.promise).mockReturnValueOnce(note.promise)
    const { wrapper, queryClient } = mountTool(null, 'QQQ')

    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet).toHaveBeenNthCalledWith(1, '/instruments/QQQ', { canonical_only: true }, { priority: 'high' })
    expect(wrapper.get('.note-tool__status').text()).toBe('QQQ · Resolving canonical instrument…')
    expect(wrapper.get('textarea').element.disabled).toBe(true)

    identity.resolve({ id: 4, symbol: 'QQQ' })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
    expect(apiGet.mock.calls[1]?.[0]).toBe('/notes/instruments/4')
    expect(wrapper.get('.note-tool__status').text()).toBe('QQQ · Loading…')

    note.resolve(null)
    await vi.waitFor(() => expect(wrapper.get('.note-tool__status').text()).toBe('QQQ · No note'))
    expect(wrapper.get('textarea').element.disabled).toBe(false)
    apiPut.mockResolvedValue({ updated_at: '2026-11-08T09:00:00Z' })
    await wrapper.get('textarea').setValue('QQQ note saved against resolved identity')
    await debounceSave()
    await vi.waitFor(() => expect(wrapper.get('.note-tool__status').text()).toContain('Saved '))
    expect(apiPut).toHaveBeenCalledWith('/notes/instruments/4', { content: 'QQQ note saved against resolved identity' })
    wrapper.unmount()
    queryClient.clear()
  })

  it('reports a missing canonical identity only after the lookup returns not found', async () => {
    apiGet.mockRejectedValueOnce({ status: 404, message: 'not found' })
    const { wrapper, queryClient } = mountTool(null, 'UNKNOWN')

    await vi.waitFor(() => expect(wrapper.get('.note-tool__status').text()).toBe('UNKNOWN · No canonical instrument'))
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/instruments/UNKNOWN', { canonical_only: true }, { priority: 'high' })
    expect(wrapper.get('textarea').element.disabled).toBe(true)
    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps a late identity result from an earlier symbol out of the current Notes context', async () => {
    const qqqIdentity = deferred<{ id: number; symbol: string }>()
    apiGet.mockReturnValueOnce(qqqIdentity.promise).mockResolvedValueOnce(null)
    const { wrapper, queryClient } = mountTool(null, 'QQQ')

    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(wrapper.get('.note-tool__status').text()).toBe('QQQ · Resolving canonical instrument…')
    await wrapper.setProps({ instrumentId: 7, symbol: 'SPY' })
    await vi.waitFor(() => expect(wrapper.get('.note-tool__status').text()).toBe('SPY · No note'))

    qqqIdentity.resolve({ id: 4, symbol: 'QQQ' })
    await flushPromises()
    expect(apiGet).toHaveBeenCalledTimes(2)
    expect(apiGet.mock.calls[1]?.[0]).toBe('/notes/instruments/7')
    expect(wrapper.get('.note-tool__status').text()).toBe('SPY · No note')
    expect(wrapper.get('textarea').element.disabled).toBe(false)
    wrapper.unmount()
    queryClient.clear()
  })

  it('flushes the old instrument draft on context switch and fences its late acknowledgement', async () => {
    const save = deferred<{ updated_at: string }>()
    apiPut.mockReturnValue(save.promise)
    const { wrapper, queryClient } = mountTool()
    await flushPromises()
    await waitForLoaded(wrapper)

    await wrapper.get('textarea').setValue('latest SPY note')
    expect(wrapper.get('.note-tool__status').text()).toContain('Saving…')
    await wrapper.setProps({ instrumentId: 8, symbol: 'MSFT' })
    await flushPromises()

    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPut).toHaveBeenCalledWith('/notes/instruments/7', { content: 'latest SPY note' })
    expect(wrapper.get('.note-tool__status').text()).toBe('MSFT · No note')

    save.resolve({ updated_at: '2026-11-07T10:00:00Z' })
    await flushPromises()
    expect(wrapper.get('.note-tool__status').text()).toBe('MSFT · No note')
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toMatchObject({ content: 'latest SPY note' })
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).not.toHaveProperty('pending')
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 8])).toBeNull()
    wrapper.unmount()
    queryClient.clear()
  })

  it('flushes the debounced draft when the panel unmounts and retains it in the query cache', async () => {
    const save = deferred<{ updated_at: string }>()
    apiPut.mockReturnValue(save.promise)
    const { wrapper, queryClient } = mountTool()
    await flushPromises()
    await waitForLoaded(wrapper)

    await wrapper.get('textarea').setValue('saved on close')
    wrapper.unmount()
    await flushPromises()
    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPut).toHaveBeenCalledWith('/notes/instruments/7', { content: 'saved on close' })
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toMatchObject({
      content: 'saved on close',
      pending: true,
    })

    save.resolve({ updated_at: '2026-11-07T10:01:00Z' })
    await flushPromises()
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toMatchObject({
      content: 'saved on close',
      updated_at: '2026-11-07T10:01:00Z',
    })
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).not.toHaveProperty('pending')
    queryClient.clear()
  })

  it('does not mark an older acknowledgement saved while a newer draft is pending', async () => {
    const first = deferred<{ updated_at: string }>()
    const second = deferred<{ updated_at: string }>()
    apiPut.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { wrapper, queryClient } = mountTool()
    await flushPromises()
    await waitForLoaded(wrapper)

    await wrapper.get('textarea').setValue('first draft')
    await debounceSave()
    await flushPromises()
    expect(apiPut).toHaveBeenCalledTimes(1)

    await wrapper.get('textarea').setValue('newest draft')
    await debounceSave()
    await flushPromises()
    expect(apiPut).toHaveBeenCalledTimes(1)
    first.resolve({ updated_at: '2026-11-07T10:02:00Z' })
    await flushPromises()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2))
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut).toHaveBeenLastCalledWith('/notes/instruments/7', { content: 'newest draft' })
    expect(wrapper.get('.note-tool__status').text()).toContain('Saving…')
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toMatchObject({
      content: 'newest draft',
      pending: true,
    })

    second.resolve({ updated_at: '2026-11-07T10:03:00Z' })
    await flushPromises()
    expect(wrapper.get('.note-tool__status').text()).toContain('Saved ')
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toMatchObject({
      content: 'newest draft',
      updated_at: '2026-11-07T10:03:00Z',
    })
    wrapper.unmount()
    queryClient.clear()
  })

  it('does not send a queued old-session draft after auth changes or repopulate its cleared cache', async () => {
    const first = deferred<{ updated_at: string }>()
    apiPut.mockReturnValueOnce(first.promise)
    const { wrapper, queryClient } = mountTool()
    const removeSessionCleanup = installAuthSessionCleanup(queryClient, createPinia())
    await flushPromises()
    await waitForLoaded(wrapper)

    await wrapper.get('textarea').setValue('first old-session draft')
    await debounceSave()
    await flushPromises()
    expect(apiPut).toHaveBeenCalledTimes(1)

    await wrapper.get('textarea').setValue('newer queued old-session draft')
    await debounceSave()
    await flushPromises()
    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toMatchObject({
      content: 'newer queued old-session draft',
      pending: true,
    })

    beginAuthSessionBoundary()
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toBeUndefined()
    first.resolve({ updated_at: '2026-11-07T10:04:00Z' })
    await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPut).toHaveBeenCalledWith('/notes/instruments/7', { content: 'first old-session draft' })
    expect(queryClient.getQueryData(['workstation', 'instrument-note', 7])).toBeUndefined()

    removeSessionCleanup()
    wrapper.unmount()
    queryClient.clear()
  })

})
