import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import InstrumentInfoPanel from '@/components/chart/InstrumentInfoPanel.vue'

describe('InstrumentInfoPanel', () => {
  it('shows intraday time for day-range and date-only timestamps for 52-week range endpoints', async () => {
    const wrapper = mount(InstrumentInfoPanel, {
      attachTo: document.body,
      props: {
        instrument: {
          id: 1,
          symbol: 'TSLA',
          name: 'Tesla',
          currency: 'USD',
          is_active: true,
          stats: {
            week52_high: 488.4,
            week52_low: 138.8,
            field_provenance: {
              week52_high: { source: 'internal_ohlcv_52w', observed_at: '2026-03-05T00:00:00Z' },
              week52_low: { source: 'internal_ohlcv_52w', observed_at: '2025-06-11T00:00:00Z' },
            },
          },
        },
        currentPrice: 320.5,
        sessionHigh: 325.2,
        sessionLow: 312.4,
        sessionHighTime: '2026-05-05T14:30:00Z',
        sessionLowTime: '2026-05-05T10:15:00Z',
      },
      global: {
        stubs: {
          ProvenanceHint: { template: '<span class="prov-hint-stub">i</span>' },
        },
      },
    })

    const rangeRows = wrapper.findAll('.range-row')
    expect(rangeRows).toHaveLength(2)

    const tooltipAnchors = wrapper.findAll('.hover-tooltip-anchor')
    await tooltipAnchors[0].trigger('mouseenter')
    await nextTick()
    await nextTick()

    expect(document.body.textContent).toContain('Day low occurred on 2026-05-05 at 10:15 UTC')

    await tooltipAnchors[0].trigger('mouseleave')
    await nextTick()

    await tooltipAnchors[3].trigger('mouseenter')
    await nextTick()
    await nextTick()

    expect(document.body.textContent).toContain('52-week high occurred on 2026-03-05')
    expect(document.body.textContent).not.toContain('2026-03-05 at')
    wrapper.unmount()
  })

  it('renders formatted stats and equity fundamentals', () => {
    const wrapper = mount(InstrumentInfoPanel, {
      props: {
        instrument: {
          id: 2,
          symbol: 'AAPL',
          name: 'Apple Inc.',
          currency: 'USD',
          is_active: true,
          stats: {
            week52_high: 200.0,
            week52_low: 150.0,
            avg_volume_30d: 85_000_000,
            market_cap: 3_200_000_000_000,
            pe_ratio: 28.5,
            beta: 1.2,
            dividend_yield: 0.0065,
          },
          equity_detail: {
            sector: 'Technology',
            industry: 'Consumer Electronics',
            country: 'US',
            market_cap_tier: 'mega_cap',
            ipo_date: '1980-12-12',
            employees: 161_000,
            website: 'https://www.apple.com',
          },
        },
        currentPrice: 175.0,
      },
      global: {
        stubs: {
          ProvenanceHint: { template: '<span class="prov-hint-stub">i</span>' },
          HoverTooltip: { template: '<span><slot /></span>' },
        },
      },
    })

    const text = wrapper.text()
    expect(text).toContain('85.00M')
    expect(text).toContain('$3.20T')
    expect(text).toContain('0.65%')
    expect(text).toContain('Mega Cap')
    expect(text).toContain('apple.com')
    wrapper.unmount()
  })

  it('renders every canonical listing with its exchange and lifecycle state', () => {
    const wrapper = mount(InstrumentInfoPanel, {
      props: {
        instrument: {
          id: 4,
          symbol: 'DUAL',
          name: 'Dual venue issuer',
          currency: 'USD',
          is_active: true,
          listings: [
            {
              ticker: 'DUAL',
              currency: 'USD',
              is_primary: true,
              is_active: true,
              exchange: { id: 1, mic: 'XNAS', name: 'Nasdaq' },
            },
            {
              ticker: 'DUAL',
              currency: 'USD',
              is_primary: false,
              is_active: false,
              exchange: { id: 2, mic: 'XNYS', name: 'New York Stock Exchange' },
            },
          ],
        },
      },
    })

    expect(wrapper.findAll('.listing-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('XNAS')
    expect(wrapper.text()).toContain('XNYS')
    expect(wrapper.text()).toContain('primary')
    expect(wrapper.text()).toContain('inactive')
    wrapper.unmount()
  })

  it('exposes the report as a keyboard-operable disclosure region', async () => {
    const wrapper = mount(InstrumentInfoPanel, {
      props: { instrument: { id: 3, symbol: 'SPY', name: 'SPDR S&P 500 ETF', currency: 'USD', is_active: true } },
    })
    const region = wrapper.get('[role="region"][aria-label="SPY instrument report"]')
    const header = wrapper.get('.section-header[role="button"]')
    expect(header.attributes('tabindex')).toBe('0')
    expect(header.attributes('aria-expanded')).toBe('true')
    await header.trigger('keydown', { key: 'Enter' })
    expect(header.attributes('aria-expanded')).toBe('false')
    await header.trigger('keydown', { key: ' ' })
    expect(header.attributes('aria-expanded')).toBe('true')
    expect(region.exists()).toBe(true)
    wrapper.unmount()
  })

  it('publishes canonical identity when opening a synthetic constituent', async () => {
    const wrapper = mount(InstrumentInfoPanel, {
      props: {
        instrument: {
          id: 10,
          symbol: 'XLK/SPY',
          name: 'Technology relative strength',
          is_active: true,
          is_synthetic: true,
          expression: 'XLK/SPY',
          synthetic_constituents: [{ ticker_alias: 'XLK', constituent_instrument_id: 91 }],
        },
      },
    })

    await wrapper.get('.constituent-chip').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['XLK', 91]])
    wrapper.unmount()
  })
})
