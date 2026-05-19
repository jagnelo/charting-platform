import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyRuleTreeEditor from '@/components/strategy/StrategyRuleTreeEditor.vue'
import type { TechnicalConditionDraft } from '@/lib/technicalConditions'

function makeConditionDraft(): TechnicalConditionDraft {
  return {
    type: 'indicator_threshold',
    indicator: 'rsi',
    params: { period: 14 },
    op: 'lt',
    value: 30,
  }
}

describe('StrategyRuleTreeEditor', () => {
  it('emits add/remove actions for group nodes', async () => {
    const wrapper = mount(StrategyRuleTreeEditor, {
      props: {
        node: {
          id: 'root',
          kind: 'group',
          type: 'all',
          children: [],
        },
        depth: 0,
        canRemove: false,
        typeOptions: [
          { value: 'indicator_threshold', label: 'Indicator vs Value' },
        ],
      },
    })

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')
    await buttons[3].trigger('click')

    expect(wrapper.emitted('add-group')).toEqual([
      ['root', 'all'],
      ['root', 'any'],
      ['root', 'not'],
    ])
    expect(wrapper.emitted('add-condition')).toEqual([['root']])
  })

  it('forwards nested child actions from not groups', async () => {
    const wrapper = mount(StrategyRuleTreeEditor, {
      props: {
        node: {
          id: 'neg',
          kind: 'not',
          condition: {
            id: 'child-condition',
            kind: 'condition',
            condition: makeConditionDraft(),
          },
        },
        depth: 1,
        canRemove: true,
        typeOptions: [
          { value: 'indicator_threshold', label: 'Indicator vs Value' },
        ],
      },
    })

    const removeButtons = wrapper.findAll('button[aria-label="Remove condition"], button[aria-label="Remove group"]')
    await removeButtons[0].trigger('click')
    expect(wrapper.emitted('remove')).toEqual([['neg']])

    const child = wrapper.findComponent(StrategyRuleTreeEditor)
    child.vm.$emit('remove', 'child-condition')
    child.vm.$emit('add-condition', 'child-condition')
    child.vm.$emit('add-group', 'child-condition', 'any')

    expect(wrapper.emitted('remove')).toContainEqual(['child-condition'])
    expect(wrapper.emitted('add-condition')).toContainEqual(['child-condition'])
    expect(wrapper.emitted('add-group')).toContainEqual(['child-condition', 'any'])
  })
})
