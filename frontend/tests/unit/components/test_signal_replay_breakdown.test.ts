import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SignalReplayBreakdown from '@/components/strategy/SignalReplayBreakdown.vue'

describe('SignalReplayBreakdown', () => {
  it('renders replay summary chips and setup breakdown rows', async () => {
    const wrapper = mount(SignalReplayBreakdown, {
      props: {
        signalCount: 12,
        replayedSignalCount: 9,
        setupTypeBreakdown: {
          breakout: 7,
          reclaim: 5,
        },
      },
    })

    expect(wrapper.text()).toContain('12 signals')
    expect(wrapper.text()).toContain('9 replayed')
    expect(wrapper.text()).toContain('75.0% replayed')
    expect(wrapper.text()).toContain('Breakout')
    expect(wrapper.text()).toContain('Reclaim')

    await wrapper.findAll('button')[0].trigger('click')
    expect(wrapper.text()).toContain('Breakout made up')
  })
})
