import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import Notification from '@/components/common/Notification.vue'

describe('Notification', () => {
  it('keeps the canonical indicator output visible in alert toasts', async () => {
    const wrapper = mount(Notification)

    window.dispatchEvent(new CustomEvent('chart:alert-triggered', {
      detail: {
        symbol: 'SPY',
        alert_kind: 'indicator',
        indicator: 'bb',
        output_a: 'bb_upper',
        indicator_b: 'sma',
        output_b: 'sma',
        condition: 'crosses_above',
        threshold: 500,
        value_a: 501.25,
      },
    }))
    await nextTick()

    expect(document.body.textContent).toContain('SPY — BB [bb_upper] vs SMA [sma] alert')
    expect(document.body.textContent).toContain('BB [bb_upper] vs SMA [sma] crosses above 500')
    wrapper.unmount()
  })
})
