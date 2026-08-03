import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))
vi.mock('@/components/workstation/StudyHistogramUPlot.vue', () => ({ default: { template: '<div class="histogram-chart" />', props: ['name', 'bins', 'current'] } }))

import ResearchResultsTool from '@/components/workstation/ResearchResultsTool.vue'

describe('ResearchResultsTool', () => {
  beforeEach(() => apiGet.mockReset())

  it('loads persisted runs and exposes selected structured artifacts', async () => {
    apiGet.mockResolvedValue([{ id: 9, status: 'completed', reproducibility_hash: 'abc', diagnostics: [], artifacts: [{ id: 3, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } }, { id: 4, name: 'distribution', artifact_type: 'histogram', payload: { value: { bins: [{ start: 1, end: 2, count: 1 }] } } }] }])
    const wrapper = mount(ResearchResultsTool)
    await flushPromises()

    expect(apiGet).toHaveBeenCalledWith('/research/runs', { limit: 25 })
    expect(wrapper.text()).toContain('Run #9')
    expect(wrapper.text()).toContain('current_streak')
    expect(wrapper.find('.histogram-chart').exists()).toBe(true)
  })
})
