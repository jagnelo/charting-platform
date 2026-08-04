import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ToolWindow from '@/components/workstation/ToolWindow.vue'

describe('ToolWindow', () => {
  it('publishes actual maximize, float, close, and link-group actions without inert header controls', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Chart', symbol: 'SPY', linkGroup: 'blue' } })

    expect(wrapper.find('[aria-label="Drag tool"]').exists()).toBe(false)
    expect(wrapper.find('[title="Tool menu"]').exists()).toBe(false)

    await wrapper.find('[title="Maximize"]').trigger('click')
    await wrapper.find('[title="Float"]').trigger('click')
    await wrapper.find('[title="Close"]').trigger('click')
    await wrapper.find('select').setValue('yellow')

    expect(wrapper.emitted('maximize')).toHaveLength(1)
    expect(wrapper.emitted('float')).toHaveLength(1)
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
})
