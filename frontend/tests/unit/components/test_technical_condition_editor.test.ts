import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import TechnicalConditionEditor from '@/components/common/TechnicalConditionEditor.vue'
import { createDefaultTechnicalCondition } from '@/lib/technicalConditions'

function fieldByLabel(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper
    .findAll('.field')
    .find(field => field.find('.field-label').text() === label)
}

function selectByLabel(wrapper: ReturnType<typeof mount>, label: string) {
  return fieldByLabel(wrapper, label)?.find('select')
}

function inputByLabel(wrapper: ReturnType<typeof mount>, label: string) {
  return fieldByLabel(wrapper, label)?.find('input')
}

describe('TechnicalConditionEditor', () => {
  it('switches to broader indicator defaults and exposes dynamic params/outputs', async () => {
    const condition = createDefaultTechnicalCondition('indicator_threshold')
    const wrapper = mount(TechnicalConditionEditor, {
      props: {
        modelValue: condition,
        canRemove: true,
      },
    })

    const selects = wrapper.findAll('select')
    await selects[1].setValue('macd')

    expect(condition.indicator).toBe('macd')
    expect(condition.params?.fast).toBe(12)
    expect(condition.params?.slow).toBe(26)
    expect(condition.params?.signal).toBe(9)
    expect(condition.output).toBe('macd')
    expect(wrapper.text()).toContain('Output')
  })

  it('resets price-indicator params when the indicator type changes', async () => {
    const condition = createDefaultTechnicalCondition('price_indicator')
    const wrapper = mount(TechnicalConditionEditor, {
      props: {
        modelValue: condition,
        canRemove: false,
      },
    })

    const selects = wrapper.findAll('select')
    await selects[3].setValue('bb')

    expect(condition.indicator).toBe('bb')
    expect(condition.params?.period).toBe(20)
    expect(condition.params?.std_dev).toBe(2)
    expect(condition.output).toBe('bb_upper')
    expect(wrapper.text()).toContain('Upper band')
  })

  it('supports date-based indicator params like AVWAP anchors', async () => {
    const condition = createDefaultTechnicalCondition('indicator_threshold')
    const wrapper = mount(TechnicalConditionEditor, {
      props: {
        modelValue: condition,
        canRemove: false,
      },
    })

    const selects = wrapper.findAll('select')
    await selects[1].setValue('avwap')

    const dateInput = wrapper.find('input[type="date"]')
    await dateInput.setValue('2026-05-01')

    expect(condition.indicator).toBe('avwap')
    expect(Number(condition.params?.anchor_timestamp)).toBeGreaterThan(0)
  })

  it('supports boolean and select-based indicator params', async () => {
    const condition = createDefaultTechnicalCondition('indicator_threshold')
    const wrapper = mount(TechnicalConditionEditor, {
      props: {
        modelValue: condition,
        canRemove: false,
      },
    })

    const selects = wrapper.findAll('select')
    await selects[1].setValue('pivot_points')
    const methodSelect = wrapper.findAll('select')[2]
    await methodSelect.setValue('fibonacci')

    expect(condition.indicator).toBe('pivot_points')
    expect(condition.params?.method).toBe('fibonacci')
    expect(condition.output).toBe('pp')
  })

  it('updates string and numeric fundamental filters with the correct controls', async () => {
    const condition = createDefaultTechnicalCondition('fundamental_filter')
    const wrapper = mount(TechnicalConditionEditor, {
      props: {
        modelValue: condition,
        canRemove: false,
      },
    })

    const fieldSelect = selectByLabel(wrapper, 'Field')
    expect(fieldSelect?.exists()).toBe(true)
    await fieldSelect.setValue('employees')
    await nextTick()

    const numericInput = inputByLabel(wrapper, 'Value')
    expect(numericInput?.attributes('type')).toBe('number')
    await numericInput.setValue('2500')

    expect(condition.field).toBe('employees')
    expect(condition.value).toBe(2500)

    await fieldSelect.setValue('sector')
    await nextTick()

    const textInput = inputByLabel(wrapper, 'Value')
    expect(textInput?.attributes('type')).toBe('text')
    await textInput.setValue('Technology')

    expect(condition.field).toBe('sector')
    expect(condition.value).toBe('Technology')
  })

  it('resets left and right indicator refs in indicator-cross conditions', async () => {
    const condition = createDefaultTechnicalCondition('indicator_cross')
    const wrapper = mount(TechnicalConditionEditor, {
      props: {
        modelValue: condition,
        canRemove: false,
      },
    })

    const leftIndicatorSelect = selectByLabel(wrapper, 'Left indicator')
    expect(leftIndicatorSelect?.exists()).toBe(true)
    await leftIndicatorSelect.setValue('macd')
    await nextTick()

    const rightIndicatorSelect = selectByLabel(wrapper, 'Right indicator')
    expect(rightIndicatorSelect?.exists()).toBe(true)
    await rightIndicatorSelect.setValue('bb')

    expect(condition.indicator_a?.type).toBe('macd')
    expect(condition.indicator_a?.params.fast).toBe(12)
    expect(condition.indicator_a?.output).toBe('macd')
    expect(condition.indicator_b?.type).toBe('bb')
    expect(condition.indicator_b?.params.std_dev).toBe(2)
    expect(condition.indicator_b?.output).toBe('bb_upper')
  })
})
