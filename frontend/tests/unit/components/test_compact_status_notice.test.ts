import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CompactStatusNotice from '@/components/common/CompactStatusNotice.vue'

describe('CompactStatusNotice', () => {
  it('keeps the visible summary short and exposes the complete status detail', () => {
    const detail = 'The data source is temporarily at its request capacity. It will resume at 14:37. Your current view remains usable.'
    const wrapper = mount(CompactStatusNotice, {
      props: { summary: 'History waiting · 14:37', detail },
    })

    const summary = wrapper.get('summary')
    expect(summary.get('.compact-status__summary').text()).toBe('History waiting · 14:37')
    expect(summary.attributes('title')).toBe(detail)
    expect(summary.attributes('aria-label')).toBe(`History waiting · 14:37. ${detail}`)
    expect(summary.attributes('aria-describedby')).toBe(wrapper.get('.compact-status__sr-only').attributes('id'))
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.get('[role="status"]').text()).toBe(detail)
    expect(wrapper.get('.compact-status__detail').text()).toBe(detail)
    wrapper.unmount()
  })

  it('keeps failure details available through an alert disclosure', () => {
    const detail = 'Current data-source credentials are unavailable for this request.'
    const wrapper = mount(CompactStatusNotice, {
      props: { summary: 'Holdings source unavailable', detail, kind: 'alert' },
    })

    expect(wrapper.get('.compact-status__summary').text()).toBe('Holdings source unavailable')
    expect(wrapper.get('[role="alert"]').text()).toBe(detail)
    expect(wrapper.get('[role="alert"]').attributes('aria-live')).toBe('assertive')
    expect(wrapper.get('summary').attributes('title')).toBe(detail)
    expect(wrapper.get('.compact-status__detail').text()).toBe(detail)
    wrapper.unmount()
  })

  it('opens and closes the full status disclosure with its native summary control', async () => {
    const wrapper = mount(CompactStatusNotice, {
      props: { summary: 'History waiting', detail: 'The admitted history request resumes at 14:37.' },
    })
    const details = wrapper.get('details')
    const summary = wrapper.get('summary')

    expect((details.element as HTMLDetailsElement).open).toBe(false)
    await summary.trigger('click')
    expect((details.element as HTMLDetailsElement).open).toBe(true)
    await details.trigger('toggle')
    expect(wrapper.get('.compact-status').classes()).toContain('compact-status--open')
    expect(wrapper.get('.compact-status__detail').text()).toBe('The admitted history request resumes at 14:37.')

    await summary.trigger('click')
    expect((details.element as HTMLDetailsElement).open).toBe(false)
    await details.trigger('toggle')
    expect(wrapper.get('.compact-status').classes()).not.toContain('compact-status--open')
    wrapper.unmount()
  })
})
