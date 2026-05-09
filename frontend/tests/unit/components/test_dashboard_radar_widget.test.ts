import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardRadarWidget from '@/components/dashboard/DashboardRadarWidget.vue'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/lib/api'

describe('DashboardRadarWidget', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    push.mockReset()
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((_url: string, params: Record<string, any>) => {
      if (_url === '/radar/detections/9') {
        return Promise.resolve(buildDetection())
      }
      if (params?.setup_type === 'breakdown') {
        return Promise.resolve([
          buildDetection({
            id: 11,
            instrument_symbol: 'TSLA',
            instrument_name: 'Tesla',
            setup_type: 'breakdown',
            score: 0.79,
            summary: 'TSLA is showing a breakdown setup.',
          }),
        ])
      }
      return Promise.resolve([buildDetection()])
    })
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

  it('supports multiple setup filters without free-text guessing', async () => {
    const wrapper = mount(DashboardRadarWidget, {
      props: {
        config: {
          timeframe: 'D1',
          state: 'confirmed',
          min_score: 0.6,
          limit: 6,
          active_only: true,
          setup_types: ['breakout_retest', 'breakdown'],
        },
      },
    })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('AAPL')
      expect(wrapper.text()).toContain('TSLA')
    })

    expect(api.get).toHaveBeenCalledTimes(2)
    expect(api.get).toHaveBeenNthCalledWith(1, '/radar/detections', {
      timeframe: 'D1',
      state: 'confirmed',
      min_score: 0.6,
      limit: 6,
      active_only: true,
      symbol: undefined,
      setup_type: 'breakout_retest',
    })
    expect(api.get).toHaveBeenNthCalledWith(2, '/radar/detections', {
      timeframe: 'D1',
      state: 'confirmed',
      min_score: 0.6,
      limit: 6,
      active_only: true,
      symbol: undefined,
      setup_type: 'breakdown',
    })
    expect(wrapper.text()).toContain('2 setups')
  })

  it('opens an in-widget detail overlay instead of redirecting on row click', async () => {
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
    })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('AAPL')
    })

    await wrapper.get('.radar-widget-row').trigger('click')

    await vi.waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/radar/detections/9')
    })

    expect(push).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Open chart')
    expect(wrapper.text()).toContain('Close back below 181.20.')
  })
})

function buildDetection(overrides: Record<string, any> = {}) {
  return {
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
    ...overrides,
  }
}
