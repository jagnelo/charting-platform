import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardRadarWidget from '@/components/dashboard/DashboardRadarWidget.vue'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/lib/api'

describe('DashboardRadarWidget', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 9,
        run_id: 1,
        instrument_id: 7,
        instrument_symbol: 'AAPL',
        instrument_name: 'Apple',
        timeframe: 'D1',
        setup_type: 'breakout_retest',
        state: 'confirmed',
        score: 0.87,
        observed_at: '2026-05-07T00:00:00Z',
        signal_at: '2026-05-07T00:00:00Z',
        context_at: '2026-05-06T00:00:00Z',
        fresh_until: '2026-05-12T00:00:00Z',
        outcome_status: 'open',
        outcome_last_evaluated_at: '2026-05-07T00:00:00Z',
        bars_since_signal: 0,
        max_favorable_excursion_pct: null,
        max_adverse_excursion_pct: null,
        target_hit_at: null,
        invalidated_at: null,
        summary: 'AAPL is showing a breakout retest setup.',
        invalidation_hint: 'Close back below 181.20.',
        score_factors: { normalized_score: 0.87 },
      },
    ])
  })

  it('loads and renders radar detections', async () => {
    const wrapper = mount(DashboardRadarWidget, {
      props: {
        config: {
          timeframe: 'D1',
          state: 'confirmed',
          min_score: 0.6,
          limit: 6,
          active_only: true,
        },
      },
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a><slot /></a>',
          },
        },
      },
    })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('AAPL')
    })

    expect(api.get).toHaveBeenCalledWith('/radar/detections', {
      timeframe: 'D1',
      setup_type: undefined,
      state: 'confirmed',
      min_score: 0.6,
      limit: 6,
      active_only: true,
      symbol: undefined,
    })
    expect(wrapper.text()).toContain('Technical Radar')
    expect(wrapper.text()).toContain('AAPL')
    expect(wrapper.text()).toContain('breakout retest')
    expect(wrapper.text()).toContain('confirmed')
  })
})
