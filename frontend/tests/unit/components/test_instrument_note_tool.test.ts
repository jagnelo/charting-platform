import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, put: apiPut } }))

import InstrumentNoteTool from '@/components/workstation/InstrumentNoteTool.vue'
import { beginAuthSessionBoundary, installAuthSessionCleanup } from '@/lib/authSession'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function mountTool(instrumentId = 7, symbol = 'SPY') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 60_000 } } })
  const wrapper = mount(InstrumentNoteTool, {
    props: { instrumentId, symbol },
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  return { wrapper, queryClient }
}

describe('InstrumentNoteTool draft lifecycle', () => {
  beforeEach(() => {
    apiGet.mockReset().mockResolvedValue(null)
    apiPut.mockReset()
  })

  async function waitForLoaded(wrapper: ReturnType<typeof mountTool>['wrapper']) {
    await vi.waitFor(() => expect(wrapper.get('.note-tool__status').text()).toBe('SPY · No note'))
  }

  async function debounceSave() {
    await new Promise(resolve => setTimeout(resolve, 575))
  }

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
