import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiDelete, apiGet, apiPut } = vi.hoisted(() => ({ apiDelete: vi.fn(), apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { delete: apiDelete, get: apiGet, put: apiPut } }))

import ChartTemplateControl from '@/components/workstation/ChartTemplateControl.vue'

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
    expect(wrapper.text()).toContain('Trend 20')
    await wrapper.get('.chart-template__apply').trigger('click')

    expect(wrapper.emitted('apply')?.[0]).toEqual([{
      bar_type: 'line', indicators: [{
        type: 'ema', params: { period: 20 }, style: { color: '#ffaa00', lineWidth: 1 }, pane: 'main',
      }],
    }])
  })
})
