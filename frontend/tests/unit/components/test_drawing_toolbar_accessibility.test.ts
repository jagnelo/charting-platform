import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import DrawingToolbar from '@/components/chart/DrawingToolbar.vue'
import { useDrawingsStore } from '@/stores/drawings'

describe('DrawingToolbar accessibility', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('returns keyboard focus to the group trigger after selecting a drawing tool', async () => {
    const wrapper = mount(DrawingToolbar, {
      attachTo: document.body,
      global: {
        stubs: { WorkstationGlyph: { template: '<span />' } },
      },
    })

    const trigger = wrapper.get('button[aria-label="Lines"]')
    ;(trigger.element as HTMLButtonElement).focus()
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await nextTick()

    const trendline = wrapper.get('[role="menuitem"][aria-label="Trend Line"]')
    expect(document.activeElement).toBe(trendline.element)
    await trendline.trigger('keydown', { key: 'Enter' })
    await nextTick()

    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

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

    const drawStore = useDrawingsStore()
    drawStore.drawings = [{ id: 7, instrument_id: 1, drawing_type: 'trendline', data: { points: [] }, style: {}, is_visible: true, is_locked: false }]
    drawStore.selectDrawing(7)
    await nextTick()
    const visibility = wrapper.get('button[aria-label="Hide drawing"]')
    const lock = wrapper.get('button[aria-label="Lock drawing"]')
    expect(visibility.attributes('aria-pressed')).toBe('true')
    expect(lock.attributes('aria-pressed')).toBe('false')

    drawStore.drawings[0]!.is_visible = false
    drawStore.drawings[0]!.is_locked = true
    await nextTick()
    expect(wrapper.get('button[aria-label="Show drawing"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('button[aria-label="Unlock drawing"]').attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })
})
