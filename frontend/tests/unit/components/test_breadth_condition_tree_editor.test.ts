import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BreadthConditionTreeEditor from '@/components/workstation/BreadthConditionTreeEditor.vue'

function leaf(kind = 'above_moving_average') {
  return { kind, params: { period: 200, average: 'sma', comparator: 'above' } }
}

describe('BreadthConditionTreeEditor', () => {
  it('serializes arbitrary nested groups and keeps NOT to one child', async () => {
    const wrapper = mount(BreadthConditionTreeEditor, {
      props: {
        modelValue: { kind: 'all', params: { conditions: [leaf()] } },
      },
    })

    await wrapper.findAll('button').find(button => button.text().includes('Condition'))!.trigger('click')
    const added = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: { conditions: unknown[] } }
    expect(added.params.conditions).toHaveLength(2)

    await wrapper.findAll('button').find(button => button.text().includes('Group'))!.trigger('click')
    const withGroup = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: { conditions: Array<{ kind: string }> } }
    expect(withGroup.params.conditions.at(-1)?.kind).toBe('all')

    const notWrapper = mount(BreadthConditionTreeEditor, {
      props: {
        modelValue: { kind: 'not', params: { conditions: [leaf(), leaf()] } },
      },
    })
    await notWrapper.get('[aria-label="Breadth group operator 1"]').setValue('not')
    const notPayload = notWrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: { conditions: unknown[] } }
    expect(notPayload.params.conditions).toHaveLength(1)
  })

  it('edits leaf parameters without mutating the input object', async () => {
    const initial = { kind: 'percentile', target_scope: 'member', params: { field: 'close', period: 252, operator: 'gte', percentile: 0.8 } }
    const wrapper = mount(BreadthConditionTreeEditor, { props: { modelValue: initial } })
    await wrapper.get('[aria-label="Breadth percentile target 1"]').setValue('0.9')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: { percentile: number } }
    expect(payload.params.percentile).toBe(0.9)
    expect(initial.params.percentile).toBe(0.8)
  })

  it('wraps a root leaf without discarding its predicate', async () => {
    const initial = { kind: 'new_high_low', params: { direction: 'low', lookback: 20 } }
    const wrapper = mount(BreadthConditionTreeEditor, { props: { modelValue: initial } })
    await wrapper.get('button.breadth-condition-tree__wrap').trigger('click')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; params: { conditions: Array<{ kind: string; params: Record<string, unknown> }> } }
    expect(payload.kind).toBe('all')
    expect(payload.params.conditions).toEqual([initial])
  })

  it('serializes the prior high/low target leaf', async () => {
    const wrapper = mount(BreadthConditionTreeEditor, {
      props: { modelValue: { kind: 'prior_high_low', params: { direction: 'high', lookback: 20, operator: 'gte', threshold: 0 } } },
    })
    await wrapper.get('[aria-label="Breadth prior high low direction 1"]').setValue('low')
    const directionPayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; params: Record<string, unknown> }
    await wrapper.setProps({ modelValue: directionPayload })
    await wrapper.get('[aria-label="Breadth prior high low lookback 1"]').setValue('30')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; params: Record<string, unknown> }
    expect(payload.kind).toBe('prior_high_low')
    expect(payload.params.direction).toBe('low')
    expect(payload.params.lookback).toBe(30)
  })

  it('serializes a member-versus-reference series target leaf', async () => {
    const wrapper = mount(BreadthConditionTreeEditor, {
      props: { modelValue: { kind: 'series_comparison', params: { field: 'return', target_field: 'return', relation: 'difference', operator: 'gte', threshold: 0 } } },
    })
    await wrapper.get('[aria-label="Breadth series relation 1"]').setValue('ratio')
    const relationPayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: Record<string, unknown> }
    await wrapper.setProps({ modelValue: relationPayload })
    await wrapper.get('[aria-label="Breadth series reference field 1"]').setValue('close')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; params: Record<string, unknown> }
    expect(payload.kind).toBe('series_comparison')
    expect(payload.params.relation).toBe('ratio')
    expect(payload.params.target_field).toBe('close')
  })
})
