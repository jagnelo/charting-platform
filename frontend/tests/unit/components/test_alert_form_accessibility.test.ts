import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import AlertForm from '@/components/alerts/AlertForm.vue'

describe('AlertForm accessibility', () => {
  it('names the close control and exposes the active condition', () => {
    const wrapper = mount(AlertForm, {
      props: { instrumentId: 1, symbol: 'SPY' },
      global: { plugins: [createPinia()] },
    })

    const close = wrapper.get('button.form-close')
    expect(close.attributes('type')).toBe('button')
    expect(close.attributes('aria-label')).toBe('Close alert form')

    const conditions = wrapper.findAll('button.cond-btn')
    expect(conditions.length).toBeGreaterThan(1)
    expect(conditions.every(button => button.attributes('aria-label')?.startsWith('Alert condition: '))).toBe(true)
    expect(conditions.filter(button => button.attributes('aria-pressed') === 'true')).toHaveLength(1)
  })
})
