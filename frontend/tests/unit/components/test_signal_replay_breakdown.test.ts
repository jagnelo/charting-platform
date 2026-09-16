import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SignalReplayBreakdown from '@/components/strategy/SignalReplayBreakdown.vue'

describe('SignalReplayBreakdown', () => {
  it('announces the empty replay state as a polite atomic status', () => {
    const wrapper = mount(SignalReplayBreakdown)
    const empty = wrapper.get('.signal-replay__empty')

    expect(empty.text()).toBe('No signal replay summary yet.')
    expect(empty.attributes('role')).toBe('status')
    expect(empty.attributes('aria-live')).toBe('polite')
    expect(empty.attributes('aria-atomic')).toBe('true')
  })

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
