import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('@/components/workstation/StudySeriesUPlot.vue', () => ({ default: { template: '<div class="series-chart" />', props: ['name', 'timestamps', 'values'] } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))

import StudyLabTool from '@/components/workstation/StudyLabTool.vue'

describe('StudyLabTool', () => {
  it('validates, starts an immutable isolated study run, and renders artifacts', async () => {
    apiPost.mockImplementation((path: string) => {
      if (path === '/code/validate') return Promise.resolve({ valid: true, diagnostics: [], dependencies: ['stats', 'output'], lookback_hint: 1, output_contracts: ['histogram', 'scalar', 'table'] })
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 42 }] })
      if (path === '/research/runs') return Promise.resolve({ id: 9, status: 'completed', reproducibility_hash: 'sha256:test', artifacts: [
        { id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } },
        { id: 9, name: 'shortest_streak', artifact_type: 'scalar', payload: { value: 1 } },
        { id: 7, name: 'qualifies', artifact_type: 'boolean', payload: { value: true } },
        { id: 4, name: 'completed_streaks', artifact_type: 'table', payload: { value: [{ length: 2, end_timestamp: '2026-01-03' }] } },
        { id: 5, name: 'trend', artifact_type: 'series', payload: { value: { timestamps: ['2026-01-01', '2026-01-02'], values: [null, 11] } } },
        { id: 6, name: 'signals', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'positive_close' }] } },
        { id: 8, name: 'distribution', artifact_type: 'histogram', payload: { value: { bins: [{ start: 1, end: 2, count: 1 }], sample_size: 1 } } },
      ] })
      return Promise.resolve({})
    })
    const wrapper = mount(StudyLabTool, { props: { activeSymbol: 'SPY' } })

    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Validated for isolated execution'))
    await wrapper.findAll('button')[1].trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Run #9'))

    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({ code_version_id: 42, run_config: { symbol: 'SPY' } }))
    expect(wrapper.text()).toContain('current_streak')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).toContain('qualifies')
    expect(wrapper.text()).toContain('True')
    expect(wrapper.text()).toContain('completed_streaks')
    expect(wrapper.find('table').text()).toContain('end_timestamp')
    expect(wrapper.find('.series-chart').exists()).toBe(true)
    expect(wrapper.find('.histogram-chart').exists()).toBe(true)
    await wrapper.find('.study-lab-tool__events button').trigger('click')
    expect(wrapper.emitted('occurrence')?.[0]).toEqual([{ symbol: 'SPY', timestamp: '2026-01-02', kind: 'positive_close' }])
  })
})
