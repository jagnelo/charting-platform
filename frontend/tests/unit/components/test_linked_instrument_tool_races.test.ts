import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, put: apiPut } }))

import InstrumentNoteTool from '@/components/workstation/InstrumentNoteTool.vue'
import InstrumentAlertsTool from '@/components/workstation/InstrumentAlertsTool.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}

beforeEach(() => {
  apiGet.mockReset()
  apiPut.mockReset()
})

describe('linked instrument tool stale-response guards', () => {
  it('does not let an older note load overwrite the newly selected instrument', async () => {
    const first = deferred<{ content: string; updated_at: string } | null>()
    apiGet.mockImplementation((path: string) => path.endsWith('/1') ? first.promise : Promise.resolve({ content: 'XLK note', updated_at: '2026-08-03T00:00:00Z' }))
    const wrapper = mount(InstrumentNoteTool, { props: { instrumentId: 1, symbol: 'SPY' } })
    await wrapper.setProps({ instrumentId: 2, symbol: 'XLK' })
    await vi.waitFor(() => expect(wrapper.get('textarea').element).toHaveProperty('value', 'XLK note'))

    first.resolve({ content: 'stale SPY note', updated_at: '2026-08-02T00:00:00Z' })
    await wrapper.vm.$nextTick()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('XLK note')
  })

  it('does not let an older alerts load overwrite the newly selected instrument', async () => {
    const first = deferred<unknown[]>()
    apiGet.mockImplementation((_path: string, params?: { instrument_id?: number }) => {
      if (params?.instrument_id === 1) return first.promise
      if (_path === '/alerts/price') return Promise.resolve([{ id: 2, condition: 'touches', threshold_price: 9, status: 'active', repeat: false }])
      return Promise.resolve([])
    })
    const wrapper = mount(InstrumentAlertsTool, { props: { instrumentId: 1, symbol: 'SPY' } })
    await wrapper.setProps({ instrumentId: 2, symbol: 'XLK' })
    await vi.waitFor(() => expect(wrapper.text()).toContain('touches'))

    first.resolve([])
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('touches')
    expect(wrapper.text()).not.toContain('No alerts for XLK.')
  })
})
