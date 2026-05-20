import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PaperForwardMonitorPanel from '@/components/strategy/PaperForwardMonitorPanel.vue'

describe('PaperForwardMonitorPanel', () => {
  it('renders monitor summary and recent snapshots', () => {
    const wrapper = mount(PaperForwardMonitorPanel, {
      props: {
        windowBars: 20,
        snapshots: [
          { snapshot_at: '2026-05-10T10:00:00Z', latest_equity: 100250, trade_count: 3 },
          { snapshot_at: '2026-05-11T10:00:00Z', latest_equity: 100420, trade_count: 4 },
        ],
      },
    })

    expect(wrapper.text()).toContain('2 snapshots')
    expect(wrapper.text()).toContain('Latest')
    expect(wrapper.text()).toContain('20 bars')
    expect(wrapper.text()).toContain('11/05')
  })
})
