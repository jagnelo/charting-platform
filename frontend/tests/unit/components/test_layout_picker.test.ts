import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import LayoutPicker from '@/components/chart/LayoutPicker.vue'
import { useLayoutStore } from '@/stores/layout'

describe('LayoutPicker', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('flips the custom grid popup above a bottom-edge trigger and cleans listeners', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('innerHeight', 180)
    const wrapper = mount(LayoutPicker, { attachTo: document.body })
    const trigger = wrapper.get('button[title="Custom grid layout"]').element as HTMLButtonElement
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({ x: 250, y: 156, top: 156, left: 250, right: 280, bottom: 174, width: 30, height: 18, toJSON: () => ({}) })
    await wrapper.get('button[title="Custom grid layout"]').trigger('click')
    const popup = wrapper.get('[role="menu"][aria-label="Custom grid layout"]').element as HTMLElement
    expect(popup.style.top).toBe('8px')
    expect(popup.style.maxHeight).toBe('150px')
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    await wrapper.get('button[title="Custom grid layout"]').trigger('click')
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('flips the profile menu above the trigger and preserves layout actions', async () => {
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('innerHeight', 180)
    const store = useLayoutStore()
    const wrapper = mount(LayoutPicker, { attachTo: document.body })
    const trigger = wrapper.get('button[title="Layout profiles"]').element as HTMLButtonElement
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({ x: 300, y: 156, top: 156, left: 300, right: 330, bottom: 174, width: 30, height: 18, toJSON: () => ({}) })
    await wrapper.get('button[title="Layout profiles"]').trigger('click')
    const menu = wrapper.get('[role="menu"][aria-label="Layout profiles"]').element as HTMLElement
    expect(menu.style.top).toBe('8px')
    expect(menu.style.maxHeight).toBe('164px')
    expect(wrapper.text()).toContain('No saved profiles')
    await wrapper.get('button[title="Layout profiles"]').trigger('click')
    expect(store.layout).toBe('1')
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('dismisses an open menu on Escape or an outside pointer and removes the document listener', async () => {
    const addSpy = vi.spyOn(document, 'addEventListener')
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const wrapper = mount(LayoutPicker, { attachTo: document.body })
    const trigger = wrapper.get('button[title="Custom grid layout"]')
    await trigger.trigger('click')
    expect(wrapper.find('[aria-label="Custom grid layout"]').exists()).toBe(true)
    await trigger.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[aria-label="Custom grid layout"]').exists()).toBe(false)
    expect(removeSpy).toHaveBeenCalledWith('pointerdown', expect.any(Function), true)

    await trigger.trigger('click')
    document.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(wrapper.find('[aria-label="Custom grid layout"]').exists()).toBe(false)
    expect(addSpy).toHaveBeenCalledWith('pointerdown', expect.any(Function), true)
    wrapper.unmount()
  })
})
