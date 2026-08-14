import { mount as vueMount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiDelete, apiGet, apiPut } = vi.hoisted(() => ({ apiDelete: vi.fn(), apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { delete: apiDelete, get: apiGet, put: apiPut } }))

import ChartTemplateControl from '@/components/workstation/ChartTemplateControl.vue'

function mount(component: typeof ChartTemplateControl, options: Record<string, any> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return vueMount(component, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
}

describe('ChartTemplateControl', () => {
  beforeEach(() => {
    apiDelete.mockReset()
    apiGet.mockReset()
    apiPut.mockReset()
    apiGet.mockResolvedValue([])
    apiPut.mockResolvedValue({})
  })

  it('persists an immutable indicator stack with chart-local rendering configuration', async () => {
    const wrapper = mount(ChartTemplateControl, {
      props: {
        configuration: { symbol: 'SPY', bar_type: 'candles', current_price_projection: true },
        indicatorConfigs: [{
          type: 'sma', params: { period: 20 }, style: { color: '#00ff00', lineWidth: 2 }, pane: 'main',
        }],
      },
    })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled())

    await wrapper.get('button[aria-label="Chart templates"]').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.get('[aria-label="Chart template name"]').setValue('Trend template')
    await wrapper.find('.chart-template__save button').trigger('click')

    expect(apiPut).toHaveBeenCalledWith(expect.stringContaining('/chart_template/trend-template-'), expect.objectContaining({
      payload: expect.objectContaining({ configuration: expect.objectContaining({
        bar_type: 'candles',
        current_price_projection: true,
        indicators: [{ type: 'sma', params: { period: 20 }, style: { color: '#00ff00', lineWidth: 2 }, pane: 'main' }],
      }) }),
    }))
    expect(apiPut.mock.calls[0][1].payload.configuration).not.toHaveProperty('symbol')
  })

  it('publishes a saved indicator stack for the active chart without template identity', async () => {
    apiGet.mockResolvedValueOnce([{
      stable_key: 'trend-20', name: 'Trend 20', version: 3,
      payload: { configuration: { bar_type: 'line', indicators: [{
        type: 'ema', params: { period: 20 }, style: { color: '#ffaa00', lineWidth: 1 }, pane: 'main',
      }] } },
    }])
    const wrapper = mount(ChartTemplateControl, {
      props: { configuration: { symbol: 'SPY', instrument_id: 7, bar_type: 'candles' } },
    })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled())
    await wrapper.get('button[aria-label="Chart templates"]').trigger('click')
    await wrapper.vm.$nextTick()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Trend 20'))
    await wrapper.get('.chart-template__apply').trigger('click')

    expect(wrapper.emitted('apply')?.[0]).toEqual([{
      bar_type: 'line', indicators: [{
        type: 'ema', params: { period: 20 }, style: { color: '#ffaa00', lineWidth: 1 }, pane: 'main',
      }],
    }])
  })

  it('persists alternative-bar parameters and clears them when chart defaults are reset', async () => {
    const wrapper = mount(ChartTemplateControl, {
      props: { configuration: {
        symbol: 'SPY', bar_type: 'point_figure', box_size: 5, reversal: 2,
      } },
    })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled())
    await wrapper.get('button[aria-label="Chart templates"]').trigger('click')
    await wrapper.get('[aria-label="Chart template name"]').setValue('Point figure template')
    await wrapper.get('.chart-template__save button').trigger('click')
    expect(apiPut.mock.calls[0][1].payload.configuration).toEqual(expect.objectContaining({
      bar_type: 'point_figure', box_size: 5, reversal: 2,
    }))

    await wrapper.get('footer button').trigger('click')
    expect(wrapper.emitted('apply')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      bar_type: 'candles', brick_size: undefined, reversal_pct: undefined,
      box_size: undefined, reversal: undefined,
    }))
  })

  it('restores saved comparison symbols instead of retaining the active chart comparisons', async () => {
    apiGet.mockResolvedValueOnce([{
      stable_key: 'relative-template', name: 'Relative template', version: 2,
      payload: { configuration: { bar_type: 'line', comparison_symbols: ['RSP', 'XLK'] } },
    }])
    const wrapper = mount(ChartTemplateControl, {
      props: { configuration: { symbol: 'SPY', comparison_symbols: ['QQQ'] } },
    })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled())
    await wrapper.get('button[aria-label="Chart templates"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Relative template'))
    await wrapper.get('.chart-template__apply').trigger('click')
    expect(wrapper.emitted('apply')?.[0]).toEqual([{ bar_type: 'line', comparison_symbols: ['RSP', 'XLK'] }])
  })

  it('renames a saved template in place while preserving its stable identity and configuration', async () => {
    apiGet.mockResolvedValueOnce([{
      stable_key: 'trend-20', name: 'Trend 20', version: 3,
      payload: { configuration: { bar_type: 'line', indicators: [] } },
    }])
    const wrapper = mount(ChartTemplateControl, { props: { configuration: { symbol: 'SPY', bar_type: 'candles' } } })
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalled())
    await wrapper.get('button[aria-label="Chart templates"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Trend 20'))
    await wrapper.get('button[aria-label="Rename Trend 20"]').trigger('click')
    await wrapper.get('input[aria-label="Rename Trend 20"]').setValue('Weekly strength')
    await wrapper.get('button[aria-label="Save template name"]').trigger('click')
    expect(apiPut).toHaveBeenCalledWith('/workspaces/library/items/chart_template/trend-20', expect.objectContaining({
      name: 'Weekly strength',
      stable_key: 'trend-20',
      payload: expect.objectContaining({ configuration: { bar_type: 'line', indicators: [] } }),
    }))
  })

  it('deduplicates template hydration across chart roots', async () => {
    apiGet.mockResolvedValue([{ stable_key: 'shared', name: 'Shared', version: 1, payload: { configuration: {} } }])
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const global = { plugins: [[VueQueryPlugin, { queryClient }]] }
    const first = vueMount(ChartTemplateControl, { global, props: { configuration: { symbol: 'SPY' } } })
    const second = vueMount(ChartTemplateControl, { global, props: { configuration: { symbol: 'XLK' } } })
    await first.get('button[aria-label="Chart templates"]').trigger('click')
    await second.get('button[aria-label="Chart templates"]').trigger('click')
    await vi.waitFor(() => expect(first.text()).toContain('Shared'))
    await vi.waitFor(() => expect(second.text()).toContain('Shared'))
    expect(apiGet).toHaveBeenCalledTimes(1)
    first.unmount()
    second.unmount()
  })

  it('opens from the keyboard, focuses the editor, and returns focus on Escape', async () => {
    const wrapper = mount(ChartTemplateControl, { attachTo: document.body, props: { configuration: {} } })
    const trigger = wrapper.get('button[aria-label="Chart templates"]')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    await vi.waitFor(() => expect(document.activeElement).toBe(wrapper.get('[aria-label="Chart template name"]').element))
    await wrapper.get('[aria-label="Chart template name"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('closes through the header control and restores trigger focus', async () => {
    const wrapper = mount(ChartTemplateControl, { attachTo: document.body, props: { configuration: {} } })
    const trigger = wrapper.get('button[aria-label="Chart templates"]')
    await trigger.trigger('click')
    await wrapper.get('button[aria-label="Close chart templates"]').trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('opens above a bottom-edge trigger and removes viewport listeners on close', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('innerHeight', 180)
    const wrapper = mount(ChartTemplateControl, { attachTo: document.body, props: { configuration: {} } })
    const trigger = wrapper.get('button[aria-label="Chart templates"]').element as HTMLButtonElement
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      x: 120, y: 156, top: 156, left: 120, right: 220, bottom: 174, width: 100, height: 18,
      toJSON: () => ({}),
    })
    await wrapper.get('button[aria-label="Chart templates"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('[role="menu"]').exists()).toBe(true))
    const menu = wrapper.get('[role="menu"]').element as HTMLElement
    expect(menu.style.top).toBe('8px')
    expect(menu.style.maxHeight).toBe('164px')
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    await wrapper.get('button[aria-label="Close chart templates"]').trigger('click')
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    wrapper.unmount()
    vi.unstubAllGlobals()
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })
})
