import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import StudyDashboard from '@/components/workstation/StudyDashboard.vue'

describe('StudyDashboard', () => {
  it('keeps Space keydown local and emits the selected event on activation', async () => {
    const event = { symbol: 'SPY', timestamp: '2026-01-04T00:00:00Z', kind: 'breakdown' }
    const wrapper = mount(StudyDashboard, {
      props: {
        name: 'Research overview',
        panels: [{ artifact: 'occurrences', title: 'Recent occurrences', span: 12 }],
        artifacts: [{ id: 5, name: 'occurrences', artifact_type: 'events', payload: { value: [event] } }],
      },
    })
    const bubbledKeydown = vi.fn()
    wrapper.element.addEventListener('keydown', bubbledKeydown)
    const occurrence = wrapper.get('button')

    expect(occurrence.attributes('aria-label')).toBe('SPY 2026-01-04T00:00:00Z breakdown')
    await occurrence.trigger('keydown', { key: ' ' })
    expect(bubbledKeydown).not.toHaveBeenCalled()

    await occurrence.trigger('click')
    expect(wrapper.emitted('occurrence')?.[0]?.[0]).toEqual(event)
  })
})
