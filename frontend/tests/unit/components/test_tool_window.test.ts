import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ToolWindow from '@/components/workstation/ToolWindow.vue'

describe('ToolWindow', () => {
  it('publishes actual maximize, float, and link-group actions without inert header controls', async () => {
    const wrapper = mount(ToolWindow, { props: { title: 'Chart', symbol: 'SPY', linkGroup: 'blue' } })

    expect(wrapper.find('[aria-label="Drag tool"]').exists()).toBe(false)
    expect(wrapper.find('[title="Tool menu"]').exists()).toBe(false)

    await wrapper.find('[title="Maximize"]').trigger('click')
    await wrapper.find('[title="Float"]').trigger('click')
    await wrapper.find('select').setValue('yellow')

    expect(wrapper.emitted('maximize')).toHaveLength(1)
    expect(wrapper.emitted('float')).toHaveLength(1)
    expect(wrapper.emitted('update:linkGroup')?.[0]).toEqual(['yellow'])
  })
})
