import { DOMWrapper, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ToolWindow from '@/components/workstation/ToolWindow.vue'

describe('ToolWindow', () => {
  it('uses the host supplied maximize state for virtual tools and closes menus when inactive', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Relative Rotation', active: true, maximized: false } })
    const toggle = wrapper.get('button[aria-label="Maximize tool"]')
    expect(toggle.attributes('title')).toBe('Maximize')

    await wrapper.setProps({ maximized: true })
    await vi.waitFor(() => expect(wrapper.find('button[aria-label="Restore tool"]').exists()).toBe(true))
    expect(wrapper.get('button[aria-label="Restore tool"]').attributes('title')).toBe('Restore')
    await wrapper.get('[aria-label="Open tool menu"]').trigger('click')
    expect(document.getElementById(wrapper.get('[aria-label="Open tool menu"]').attributes('aria-controls'))?.querySelector('[role="menuitem"]')?.textContent).toBe('Restore')
    await wrapper.get('[aria-label="Open tool menu"]').trigger('click')
    await wrapper.setProps({ maximized: false })
    await vi.waitFor(() => expect(wrapper.find('button[aria-label="Maximize tool"]').exists()).toBe(true))

    await wrapper.get('[aria-label="Open tool menu"]').trigger('click')
    expect(document.getElementById(wrapper.get('[aria-label="Open tool menu"]').attributes('aria-controls'))).not.toBeNull()
    await wrapper.setProps({ active: false })
    expect(wrapper.get('.tool-window').classes()).not.toContain('tool-window--active')
    expect(document.getElementById(wrapper.get('[aria-label="Open tool menu"]').attributes('aria-controls'))).toBeNull()

    wrapper.unmount()
  })

  it('keeps maximize controls in sync without requiring a Golden Layout DOM ancestor', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Industries', maximized: false } })
    expect(wrapper.get('[aria-label="Maximize tool"]').exists()).toBe(true)
    await wrapper.setProps({ maximized: true })
    expect(wrapper.get('[aria-label="Restore tool"]').exists()).toBe(true)
    await wrapper.get('[aria-label="Open tool menu"]').trigger('click')
    const menuId = wrapper.get('[aria-label="Open tool menu"]').attributes('aria-controls')
    expect(document.getElementById(menuId)?.querySelector('[role="menuitem"]')?.textContent).toBe('Restore')
    wrapper.unmount()
  })

  it('gives the Relative Rotation body its own scrollable viewport without changing other tool defaults', () => {
    const rotation = mount(ToolWindow, { props: { title: 'Relative Rotation', scrollableBody: true } })
    const chart = mount(ToolWindow, { props: { title: 'Chart' } })
    expect(rotation.find('.tool-window').classes()).toContain('tool-window--scrollable-body')
    expect(chart.find('.tool-window').classes()).not.toContain('tool-window--scrollable-body')
    rotation.unmount()
    chart.unmount()
  })

  it('exposes the instance key used by workstation tool activation readiness', () => {
    const wrapper = mount(ToolWindow, { props: { windowKey: 'breadth-instance-1', title: 'Market Breadth' } })

    expect(wrapper.find('.tool-window').attributes('data-tool-key')).toBe('breadth-instance-1')
  })

  it('publishes actual maximize, float, close, and link-group actions without inert header controls', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Chart', symbol: 'SPY', linkGroup: 'blue' } })

    expect(wrapper.find('[aria-label="Drag tool"]').attributes('draggable')).toBe('true')
    const titleId = wrapper.find('.tool-window__title').attributes('id')
    expect(titleId).toBeTruthy()
    expect(wrapper.find('.tool-window').attributes('role')).toBe('group')
    expect(wrapper.find('.tool-window').attributes('aria-labelledby')).toBe(titleId)
    expect(wrapper.find('[aria-label="Open tool menu"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Open tool menu"]').attributes('aria-controls')).toBeTruthy()
    expect(wrapper.find('[aria-label="Maximize tool"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Float tool"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Close tool"]').exists()).toBe(true)
    expect(wrapper.find('.tool-window__drag-glyph').exists()).toBe(true)
    expect(wrapper.find('.tool-window__menu-glyph').exists()).toBe(true)
    expect(wrapper.find('.tool-window__maximize-glyph').exists()).toBe(true)
    expect(wrapper.find('.tool-window__float-glyph').exists()).toBe(true)
  expect(wrapper.find('.tool-window__close-glyph').exists()).toBe(true)
    expect(wrapper.text()).not.toMatch(/[⋮□↗×]/)
    const menuTrigger = wrapper.find('[title="Tool menu"]')
    const menuId = menuTrigger.attributes('aria-controls')
    await menuTrigger.trigger('click')
    const menu = document.getElementById(menuId)
    expect(menu).not.toBeNull()
    expect(menu?.parentElement).toBe(document.body)
    expect(menu?.getAttribute('aria-label')).toBe('Chart tool menu')
    expect(menu?.isConnected).toBe(true)
    const menuFloatElement = menu?.querySelector<HTMLElement>('[role="menuitem"]:nth-child(2)')
    expect(menuFloatElement?.textContent).toBe('Float')
    menuFloatElement?.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(document.getElementById(menuId)).not.toBeNull()
    const menuFloat = menuFloatElement ? new DOMWrapper(menuFloatElement) : undefined
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

  it('keeps labelled-region ids unique across detached tool roots', () => {
    const first = mount(ToolWindow, { props: { title: 'Chart' } })
    const second = mount(ToolWindow, { props: { title: 'Chart' } })

    const firstId = first.find('.tool-window__title').attributes('id')
    const secondId = second.find('.tool-window__title').attributes('id')
    expect(firstId).toBeTruthy()
    expect(secondId).toBeTruthy()
    expect(firstId).not.toBe(secondId)
    expect(first.find('.tool-window').attributes('aria-labelledby')).toBe(firstId)
    expect(second.find('.tool-window').attributes('aria-labelledby')).toBe(secondId)

    first.unmount()
    second.unmount()
  })

  it('keeps each detached tool menu trigger linked to its own menu', async () => {
    const first = mount(ToolWindow, { props: { title: 'Chart' } })
    const second = mount(ToolWindow, { props: { title: 'Chart' } })

    const firstTrigger = first.find('[aria-label="Open tool menu"]')
    const secondTrigger = second.find('[aria-label="Open tool menu"]')
    const firstMenuId = firstTrigger.attributes('aria-controls')
    const secondMenuId = secondTrigger.attributes('aria-controls')

    expect(firstMenuId).toBeTruthy()
    expect(secondMenuId).toBeTruthy()
    expect(firstMenuId).not.toBe(secondMenuId)
    expect(firstTrigger.attributes('aria-expanded')).toBe('false')
    expect(secondTrigger.attributes('aria-expanded')).toBe('false')

    await firstTrigger.trigger('click')
    await secondTrigger.trigger('click')

    expect(document.getElementById(firstMenuId)?.parentElement).toBe(document.body)
    expect(document.getElementById(secondMenuId)?.parentElement).toBe(document.body)
    expect(firstTrigger.attributes('aria-expanded')).toBe('true')
    expect(secondTrigger.attributes('aria-expanded')).toBe('true')

    first.unmount()
    expect(document.getElementById(firstMenuId)).toBeNull()
    expect(document.getElementById(secondMenuId)).not.toBeNull()
    second.unmount()
    expect(document.getElementById(secondMenuId)).toBeNull()
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
    const trigger = wrapper.find('[title="Tool menu"]')
    const menuId = trigger.attributes('aria-controls')
    await trigger.trigger('click')
    expect(document.getElementById(menuId)).not.toBeNull()

    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(document.getElementById(menuId)).toBeNull()
    wrapper.unmount()
  })

  it('supports keyboard navigation, activation, and return focus for the tool menu', async () => {
    const wrapper = mount(ToolWindow, { attachTo: document.body, props: { title: 'Chart', linkGroup: 'blue' } })
    const trigger = wrapper.find('[title="Tool menu"]')
    const menuId = trigger.attributes('aria-controls')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    const menu = document.getElementById(menuId)!
    const items = Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]'))
    expect(menu).not.toBeNull()
    expect(document.activeElement).toBe(items[0])

    await new DOMWrapper(items[0]).trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])
    await new DOMWrapper(items[1]).trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(items[2])
    await new DOMWrapper(items[2]).trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(document.getElementById(menuId)).toBeNull()

    await trigger.trigger('click')
    const escapeItem = document.getElementById(menuId)!.querySelector<HTMLElement>('[role="menuitem"]')!
    await new DOMWrapper(escapeItem).trigger('keydown', { key: 'Escape' })
    expect(document.getElementById(menuId)).toBeNull()
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('opens the menu on the last item when ArrowUp is pressed on its trigger', async () => {
    const wrapper = mount(ToolWindow, { attachTo: document.body, props: { title: 'Chart' } })
    const trigger = wrapper.find('[aria-label="Open tool menu"]')
    const menuId = trigger.attributes('aria-controls')

    await trigger.trigger('keydown', { key: 'ArrowUp' })

    const menu = document.getElementById(menuId)!
    const items = Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]'))
    expect(items).toHaveLength(3)
    expect(document.activeElement).toBe(items.at(-1))
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
    const menuId = wrapper.find('[title="Tool menu"]').attributes('aria-controls')
    const menu = document.getElementById(menuId) as HTMLElement
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
