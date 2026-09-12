import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import DashboardAlertsWidget from '@/components/dashboard/DashboardAlertsWidget.vue'
import { useAlertsStore } from '@/stores/alerts'
import { useScreenerAlertsStore } from '@/stores/screener_alerts'

describe('DashboardAlertsWidget', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps canonical multi-output selections visible in the dashboard summary', () => {
    const alertsStore = useAlertsStore()
    const screenerAlertsStore = useScreenerAlertsStore()
    alertsStore.indicatorAlerts = [{
      id: 7,
      instrument_id: 42,
      instrument_symbol: 'SPY',
      timeframe: 'D1',
      indicator_a_type: 'bb',
      indicator_a_params: { period: 20, std_dev: 2, output: 'bb_upper' },
      condition: 'crosses_above',
      threshold_value: 0,
      indicator_b_type: null,
      indicator_b_params: null,
      status: 'active',
      repeat: false,
      notes: null,
      triggered_at: null,
      trigger_count: 0,
      last_value_a: null,
      last_value_b: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }]
    screenerAlertsStore.alerts = []

    const wrapper = mount(DashboardAlertsWidget)

    expect(wrapper.text()).toContain('BB(20,2) [bb_upper] crosses above 0')
    wrapper.unmount()
  })
})
