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

  it('serializes an explicit cross-sectional group statistic target', async () => {
    const wrapper = mount(BreadthConditionTreeEditor, {
      props: { modelValue: { kind: 'cross_sectional_statistic', target_scope: 'cross_sectional', params: { field: 'close', statistic: 'mean', operator: 'gte', threshold: 0 } } },
    })
    await wrapper.get('[aria-label="Breadth group statistic function 1"]').setValue('median')
    const statisticPayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: Record<string, unknown> }
    await wrapper.setProps({ modelValue: statisticPayload })
    await wrapper.get('[aria-label="Breadth group statistic difference 1"]').setValue('0.1')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; target_scope: string; params: Record<string, unknown> }
    expect(payload.kind).toBe('cross_sectional_statistic')
    expect(payload.target_scope).toBe('cross_sectional')
    expect(payload.params.statistic).toBe('median')
    expect(payload.params.threshold).toBe(0.1)
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

  it('serializes an event target leaf with a bounded lookback', async () => {
    const wrapper = mount(BreadthConditionTreeEditor, {
      props: { modelValue: { kind: 'event', params: { event_type: 'any', lookback_days: 0, operator: 'gte', threshold: 1 } } },
    })
    await wrapper.get('[aria-label="Breadth event type 1"]').setValue('dividend')
    const typePayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: Record<string, unknown> }
    await wrapper.setProps({ modelValue: typePayload })
    await wrapper.get('[aria-label="Breadth event lookback days 1"]').setValue('7')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; params: Record<string, unknown> }
    expect(payload.kind).toBe('event')
    expect(payload.params.event_type).toBe('dividend')
    expect(payload.params.lookback_days).toBe(7)
  })

  it('serializes an owned member-level Python series leaf and exposes its asset', async () => {
    const wrapper = mount(BreadthConditionTreeEditor, {
      props: {
        modelValue: { kind: 'python_series', params: { code_version_id: 11, scope: 'member', operator: 'gte', threshold: 0 } },
        pythonSeriesAssets: [{ versionId: 11, name: 'Distance v2' }],
      },
    })
    expect(wrapper.get('[aria-label="Breadth Python series condition asset 1"]').text()).toContain('Distance v2')
    await wrapper.get('[aria-label="Breadth Python series operator 1"]').setValue('gt')
    const operatorPayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: Record<string, unknown> }
    await wrapper.setProps({ modelValue: operatorPayload })
    await wrapper.get('[aria-label="Breadth Python series threshold 1"]').setValue('1.5')
    const payload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { kind: string; params: Record<string, unknown> }
    expect(payload.kind).toBe('python_series')
    expect(payload.params.code_version_id).toBe(11)
    expect(payload.params.scope).toBe('member')
    expect(payload.params.operator).toBe('gt')
    expect(payload.params.threshold).toBe(1.5)

    await wrapper.setProps({ modelValue: payload })
    await wrapper.get('[aria-label="Breadth Python series scope 1"]').setValue('cross_sectional')
    const scopePayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: Record<string, unknown> }
    await wrapper.setProps({ modelValue: scopePayload })
    await wrapper.get('[aria-label="Breadth Python series group statistic 1"]').setValue('median')
    const crossSectionalPayload = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { params: Record<string, unknown> }
    expect(crossSectionalPayload.params.scope).toBe('cross_sectional')
    expect(crossSectionalPayload.params.statistic).toBe('median')
  })
})
