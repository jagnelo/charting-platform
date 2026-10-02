import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import DrawingToolbar from '@/components/chart/DrawingToolbar.vue'

describe('DrawingToolbar accessibility', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('exposes the active drawing tool through aria-pressed', async () => {
    const wrapper = mount(DrawingToolbar, {
      global: {
        stubs: { WorkstationGlyph: { template: '<span />' } },
      },
    })

    const trigger = wrapper.get('button[aria-label="Lines"]')
    await trigger.trigger('click')
    const popup = wrapper.get('[role="menu"][aria-label="Lines drawing tools"]')
    const trendline = popup.get('button[role="menuitem"][aria-label="Trend Line"]')
    expect(trendline.attributes('aria-pressed')).toBe('false')

    await trendline.trigger('click')
    await trigger.trigger('click')
    expect(wrapper.get('[role="menu"][aria-label="Lines drawing tools"] button[aria-label="Trend Line"]').attributes('aria-pressed')).toBe('true')

    const avwap = wrapper.get('button[aria-label="Anchored VWAP — click on chart to set anchor"]')
    expect(avwap.attributes('aria-pressed')).toBe('false')
    await avwap.trigger('click')
    expect(avwap.attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })
})
