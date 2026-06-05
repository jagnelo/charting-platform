import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import TagPicker from '@/components/common/TagPicker.vue'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('TagPicker', () => {
  it('normalizes created tags and keeps suggestions available after duplicate attempts', async () => {
    const wrapper = mount(TagPicker, {
      props: {
        modelValue: ['strategy'],
        options: ['strategy', 'momentum', 'swing trade'],
        placeholder: 'Add tag',
      },
    })

    const input = wrapper.get('input')

    await input.trigger('focus')
    await input.setValue('swing trade')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['strategy', 'swing-trade']])

    await wrapper.setProps({ modelValue: ['strategy', 'swing-trade'] })
    await flushPromises()

    await input.setValue('strategy')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
    expect(wrapper.find('.tag-dropdown').exists()).toBe(true)
    expect(wrapper.findAll('.tag-option').map(node => node.text())).toContain('momentum')
  })
})
