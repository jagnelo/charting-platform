import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ToolWindow from '@/components/workstation/ToolWindow.vue'

describe('ToolWindow', () => {
  it('publishes actual maximize, float, close, and link-group actions without inert header controls', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Chart', symbol: 'SPY', linkGroup: 'blue' } })

    expect(wrapper.find('[aria-label="Drag tool"]').attributes('draggable')).toBe('true')
    expect(wrapper.find('[aria-label="Open tool menu"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Maximize tool"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Float tool"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Close tool"]').exists()).toBe(true)
    expect(wrapper.find('.tool-window__drag-glyph').exists()).toBe(true)
    expect(wrapper.find('.tool-window__menu-glyph').exists()).toBe(true)
    expect(wrapper.find('.tool-window__maximize-glyph').exists()).toBe(true)
    expect(wrapper.find('.tool-window__float-glyph').exists()).toBe(true)
  expect(wrapper.find('.tool-window__close-glyph').exists()).toBe(true)
    expect(wrapper.text()).not.toMatch(/[⋮□↗×]/)
    await wrapper.find('[title="Tool menu"]').trigger('click')
    expect(wrapper.find('[role="menu"]').isVisible()).toBe(true)
    const menuFloat = wrapper.findAll('[role="menuitem"]').find(node => node.text() === 'Float')
    expect(menuFloat).toBeDefined()
    await menuFloat!.trigger('click')

    await wrapper.find('[title="Maximize"]').trigger('click')
    await wrapper.find('[title="Float"]').trigger('click')
    await wrapper.find('[title="Close"]').trigger('click')
    await wrapper.find('select').setValue('yellow')

    expect(wrapper.emitted('maximize')).toHaveLength(1)
    expect(wrapper.emitted('float')).toHaveLength(2)
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('update:linkGroup')?.[0]).toEqual(['yellow'])
    expect(wrapper.find('.tool-window__link-swatch').attributes('style')).toContain('background')
    expect(wrapper.find('[aria-label="Chart symbol link group"] option[value="yellow"]').text()).toBe('Yellow')
  })

  it('keeps timeframe linking distinct from symbol linking and uses MN for monthly bars', async () => {
    const wrapper = mount(ToolWindow, {
      props: { title: 'Chart', symbol: 'SPY', linkGroup: 'blue', timeframeLinkGroup: 'red', timeframe: 'MN' },
    })

    expect((wrapper.find('[aria-label="Chart timeframe"]').element as HTMLSelectElement).value).toBe('MN')
    expect(wrapper.find('[aria-label="Chart timeframe"] option[value="M1"]').exists()).toBe(true)
    await wrapper.find('[aria-label="Chart timeframe link group"]').setValue('green')
    await wrapper.find('[aria-label="Chart timeframe"]').setValue('W1')

    expect(wrapper.emitted('update:timeframeLinkGroup')?.[0]).toEqual(['green'])
    expect(wrapper.emitted('update:timeframe')?.[0]).toEqual(['W1'])
    expect(wrapper.find('[aria-label="Chart timeframe link group"] option[value="red"]').text()).toBe('Red')
    expect(wrapper.findAll('.tool-window__link-swatch')).toHaveLength(2)
  })

  it('keeps every dense header control in the flex layout at constrained widths', () => {
    const wrapper = mount(ToolWindow, {
      props: { title: 'Relative Strength Comparison', symbol: 'SPY', linkGroup: 'blue', timeframeLinkGroup: 'red', timeframe: 'D1' },
    })
    expect(wrapper.find('.tool-window__header').classes()).toContain('tool-window__header')
    expect(wrapper.find('.tool-window__actions').classes()).toContain('tool-window__actions')
    expect(wrapper.find('[aria-label="Relative Strength Comparison timeframe"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Relative Strength Comparison timeframe link group"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Relative Strength Comparison symbol link group"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Open tool menu"]').exists()).toBe(true)
  })

  it('publishes one symbol-link update when a browser emits input and change for one selection', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Chart', linkGroup: 'blue' } })
    const select = wrapper.find('[aria-label="Chart symbol link group"]')

    await select.setValue('yellow')
    await select.trigger('input')

    expect(wrapper.emitted('update:linkGroup')).toHaveLength(1)
    expect(wrapper.emitted('update:linkGroup')?.[0]).toEqual(['yellow'])
  })

  it('dismisses its tool menu when pointer focus moves outside the menu', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Chart', linkGroup: 'blue' } })
    await wrapper.find('[title="Tool menu"]').trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)

    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('supports keyboard navigation, activation, and return focus for the tool menu', async () => {
    const wrapper = mount(ToolWindow, { attachTo: document.body, props: { title: 'Chart', linkGroup: 'blue' } })
    const trigger = wrapper.find('[title="Tool menu"]')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    const items = wrapper.findAll('[role="menuitem"]')
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    expect(document.activeElement).toBe(items[0].element)

    await items[0].trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1].element)
    await items[1].trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(items[2].element)
    await items[2].trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)

    await trigger.trigger('click')
    await wrapper.find('[role="menuitem"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('flips the action menu above a bottom-edge trigger and cleans viewport listeners', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('innerHeight', 150)
    const wrapper = mount(ToolWindow, { attachTo: document.body, props: { title: 'Chart', linkGroup: 'blue' } })
    const trigger = wrapper.find('[title="Tool menu"]').element as HTMLButtonElement
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      x: 250, y: 126, top: 126, left: 250, right: 267, bottom: 146, width: 17, height: 20,
      toJSON: () => ({}),
    })
    await wrapper.find('[title="Tool menu"]').trigger('click')
    const menu = wrapper.find('[role="menu"]').element as HTMLElement
    expect(menu.style.top).toBe('8px')
    expect(menu.style.maxHeight).toBe('134px')
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    await wrapper.find('[title="Tool menu"]').trigger('click')
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    wrapper.unmount()
    vi.unstubAllGlobals()
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })
})
