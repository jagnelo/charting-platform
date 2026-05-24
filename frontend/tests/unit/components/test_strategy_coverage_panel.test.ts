import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyCoveragePanel from '@/components/strategy/StrategyCoveragePanel.vue'

const baseCoverage = {
  timeframe: 'D1',
  requested_date_from: '2026-01-01T00:00:00Z',
  requested_date_to: '2026-05-01T00:00:00Z',
  universe: {
    preview_mode: 'resolved',
    preview_note: null,
    instrument_count: 2,
    instruments_with_data: 2,
    instruments_with_requested_data: 2,
    instruments_with_full_requested_coverage: 1,
    instruments_with_partial_requested_coverage: 1,
    instruments_without_requested_coverage: 0,
    total_bars: 220,
    requested_first_bar_at: '2026-01-01T00:00:00Z',
    requested_last_bar_at: '2026-05-01T00:00:00Z',
    any_coverage_from: '1990-01-01T00:00:00Z',
    any_coverage_to: '2026-05-01T00:00:00Z',
    collective_coverage_from: '2026-02-15T00:00:00Z',
    collective_coverage_to: '2026-05-01T00:00:00Z',
    requested_fits_collective_range: false,
    resolved_symbols: ['AAPL', 'MSFT'],
    limiting_instruments: [],
    instruments: [
      {
        instrument_id: 1,
        symbol: 'AAPL',
        available_from: '1990-01-01T00:00:00Z',
        available_to: '2026-05-01T00:00:00Z',
        requested_first_bar_at: '2026-01-01T00:00:00Z',
        requested_last_bar_at: '2026-05-01T00:00:00Z',
        total_bars: 9000,
        requested_bars: 120,
        requested_status: 'full',
        note: null,
        ipo_date: null,
      },
      {
        instrument_id: 2,
        symbol: 'MSFT',
        available_from: '2026-02-15T00:00:00Z',
        available_to: '2026-05-01T00:00:00Z',
        requested_first_bar_at: '2026-02-15T00:00:00Z',
        requested_last_bar_at: '2026-05-01T00:00:00Z',
        total_bars: 55,
        requested_bars: 55,
        requested_status: 'partial',
        note: 'Coverage begins after the requested start; earlier local history may be missing.',
        ipo_date: null,
      },
    ],
  },
  benchmark: {
    symbol: 'SPY',
    preview_note: 'Coverage begins after the requested start; earlier benchmark bars are unavailable.',
    requested_status: 'partial',
    available_from: '2026-02-01T00:00:00Z',
    available_to: '2026-05-01T00:00:00Z',
    requested_first_bar_at: '2026-02-01T00:00:00Z',
    requested_last_bar_at: '2026-05-01T00:00:00Z',
    total_bars: 75,
    requested_bars: 75,
    requested_fits_range: false,
  },
  warnings: [],
}

describe('StrategyCoveragePanel', () => {
  it('shows only requested-range coverage issues in the timeline', async () => {
    const wrapper = mount(StrategyCoveragePanel, {
      props: { coverage: baseCoverage },
    })

    await wrapper.get('.coverage-list-toggle').trigger('click')

    expect(wrapper.text()).toContain('Coverage issues')
    expect(wrapper.text()).toContain('2 issues')
    expect(wrapper.find('.coverage-filter').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Full 1')
    const timelineAxisText = wrapper.get('.coverage-timeline-axis').text()
    expect(timelineAxisText).toContain('01/01/2026')
    expect(timelineAxisText).toContain('01/05/2026')
    expect(timelineAxisText).not.toContain('01/01/1990')
    expect(wrapper.text()).toContain('MSFT')
    expect(wrapper.text()).toContain('SPY')
    expect(wrapper.text()).not.toContain('AAPL')
  })

  it('uses an informative empty message when there are no coverage issues', async () => {
    const cleanCoverage = {
      ...baseCoverage,
      universe: {
        ...baseCoverage.universe,
        instruments_with_full_requested_coverage: 2,
        instruments_with_partial_requested_coverage: 0,
        requested_fits_collective_range: true,
        instruments: baseCoverage.universe.instruments.map(instrument => ({
          ...instrument,
          requested_status: 'full',
          requested_first_bar_at: '2026-01-01T00:00:00Z',
          requested_last_bar_at: '2026-05-01T00:00:00Z',
          note: null,
        })),
      },
      benchmark: {
        ...baseCoverage.benchmark,
        preview_note: null,
        requested_status: 'full',
        requested_first_bar_at: '2026-01-01T00:00:00Z',
        requested_last_bar_at: '2026-05-01T00:00:00Z',
        requested_fits_range: true,
      },
    }
    const wrapper = mount(StrategyCoveragePanel, {
      props: { coverage: cleanCoverage },
    })

    await wrapper.get('.coverage-list-toggle').trigger('click')

    expect(wrapper.text()).toContain('0 issues')
    expect(wrapper.text()).toContain('Requested range is fully covered by every selected instrument and benchmark.')
  })
})
