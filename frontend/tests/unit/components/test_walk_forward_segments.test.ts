import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WalkForwardSegments from '@/components/strategy/WalkForwardSegments.vue'

describe('WalkForwardSegments', () => {
  it('renders segment summaries and details', async () => {
    const wrapper = mount(WalkForwardSegments, {
      props: {
        trainingShare: 0.6,
        avgOutSampleReturnPct: 2.25,
        segments: [
          {
            segment: 1,
            in_sample_from: '2026-01-01T00:00:00Z',
            in_sample_to: '2026-02-01T00:00:00Z',
            out_sample_from: '2026-02-02T00:00:00Z',
            out_sample_to: '2026-03-01T00:00:00Z',
            in_sample_return_pct: 3.4,
            out_sample_return_pct: 1.8,
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('1 segments')
    expect(wrapper.text()).toContain('Training 60%')
    expect(wrapper.text()).toContain('Avg OOS 2.25%')

    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('Segment 1')
    expect(wrapper.text()).toContain('Out-sample 1.80%')
  })
})
