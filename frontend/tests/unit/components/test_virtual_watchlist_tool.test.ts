import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiDelete, apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiDelete: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { delete: apiDelete, get: apiGet, post: apiPost, put: apiPut } }))

import VirtualWatchlistTool from '@/components/workstation/VirtualWatchlistTool.vue'

const rows = [
  { instrumentId: 1, symbol: 'XLK', name: 'Technology', values: { relative_1m: 0.12 } },
  { instrumentId: 2, symbol: 'XLE', name: 'Energy', values: { relative_1m: -0.03 } },
  { instrumentId: 3, symbol: 'XLV', name: 'Health Care', values: { relative_1m: 0.02 } },
]

beforeEach(() => { apiGet.mockResolvedValue([]); apiPost.mockReset(); apiPut.mockReset(); apiDelete.mockReset() })
afterEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPut.mockReset(); apiDelete.mockReset() })

describe('VirtualWatchlistTool', () => {
  it('keeps a 10,000-row universe virtualized instead of creating one DOM row per instrument', () => {
    const largeRows = Array.from({ length: 10_000 }, (_, index) => ({
      instrumentId: index + 1,
      symbol: `SYM${index + 1}`,
      name: `Instrument ${index + 1}`,
    }))
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Large universe', rows: largeRows },
    })

    expect(wrapper.find('.watchlist__controls b').text()).toBe('10000')
    expect(wrapper.findAll('.watchlist__row').length).toBeLessThan(100)
    expect(wrapper.find('.watchlist__scroll > div').attributes('style')).toContain('height:')
  })

  it('filters canonical rows and publishes the selected canonical row', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors',
        rows,
        columns: [
          { key: 'symbol', label: 'Symbol', width: '60px' },
          { key: 'name', label: 'Name', width: '1fr' },
        ],
      },
    })

    expect(wrapper.text()).toContain('XLK')
    await wrapper.find('input').setValue('energy')
    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')
    expect(wrapper.emitted('update:filterText')?.at(-1)).toEqual(['energy'])

    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([rows[1]])
  })

  it('restores a persisted filter and follows a workspace-state update', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows, filterText: 'technology' },
    })

    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('technology')
    expect(wrapper.text()).toContain('XLK')
    expect(wrapper.text()).not.toContain('XLE')

    await wrapper.setProps({ filterText: 'energy' })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('energy')
    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')
  })

  it('applies a saved condition from its latest retained local scan result', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 91, name: 'Close above threshold' }])
      if (path === '/screeners/91/results') return Promise.resolve([{ matched_ids: [2], run_at: '2026-07-30T00:00:00Z' }])
      return Promise.resolve([])
    })
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await vi.waitFor(() => expect(wrapper.findAll('option')).toHaveLength(2))
    await wrapper.find('select').setValue('91')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Saved condition active'))

    expect(wrapper.text()).toContain('XLE')
    expect(wrapper.text()).not.toContain('XLK')
    expect(wrapper.emitted('update:conditionScreenerId')?.at(-1)).toEqual([91])
  })

  it('keeps a saved condition configured while inactive and clears it only when off', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 91, name: 'Close above threshold' }])
      if (path === '/screeners/91/results') return Promise.resolve([{ matched_ids: [2], run_at: '2026-07-30T00:00:00Z' }])
      return Promise.resolve([])
    })
    const wrapper = mount(VirtualWatchlistTool, { props: { label: 'Sectors', rows } })
    await vi.waitFor(() => expect(wrapper.findAll('option')).toHaveLength(2))
    await wrapper.find('select').setValue('91')
    await vi.waitFor(() => expect(wrapper.findAll('select')).toHaveLength(2))
    await wrapper.findAll('select')[1].setValue('inactive')

    expect(wrapper.text()).toContain('inactive')
    expect(wrapper.find('.watchlist__controls b').text()).toBe('3')
    expect(wrapper.emitted('update:conditionFilterMode')?.at(-1)).toEqual(['inactive'])
    expect(wrapper.emitted('update:conditionScreenerId')?.at(-1)).toEqual([91])

    await wrapper.findAll('select')[1].setValue('off')
    expect(wrapper.emitted('update:conditionFilterMode')?.at(-1)).toEqual(['off'])
    expect(wrapper.emitted('update:conditionScreenerId')?.at(-1)).toEqual([null])
  })

  it('shows no rows rather than silently ignoring an unrun saved condition', async () => {
    apiGet.mockImplementation((path: string) => path === '/screeners'
      ? Promise.resolve([{ id: 92, name: 'Unrun condition' }])
      : Promise.resolve([]))
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await vi.waitFor(() => expect(wrapper.findAll('option')).toHaveLength(2))
    await wrapper.find('select').setValue('92')
    await vi.waitFor(() => expect(wrapper.text()).toContain('has not been run yet'))

    expect(wrapper.findAll('.watchlist__row')).toHaveLength(0)
  })

  it('sorts a selected column without losing row identity', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows },
    })
    await wrapper.findAll('.watchlist__header button')[0].trigger('click')
    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ instrumentId: 3, symbol: 'XLV' })
  })

  it('publishes a persisted visible-column set without allowing an empty table', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'name', label: 'Name' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    const choices = wrapper.findAll('.watchlist__column-menu input[type="checkbox"]')
    await choices[1].setValue(false)
    expect(wrapper.emitted('update:visibleColumnKeys')?.[0]).toEqual([['symbol']])

    await wrapper.setProps({ visibleColumnKeys: ['symbol'] })
    await choices[0].setValue(false)
    expect(wrapper.emitted('update:visibleColumnKeys')).toHaveLength(1)
  })

  it('renders explicitly numeric technical columns without percentage scaling', () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows: [{ instrumentId: 1, symbol: 'XLK', name: 'Technology', values: { rsi14: 67.2, performance_1m: 0.12 } }],
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'rsi14', label: 'RSI', format: 'number' }, { key: 'performance_1m', label: '1M' }],
      },
    })
    expect(wrapper.text()).toContain('67.20')
    expect(wrapper.text()).toContain('12.00%')
  })

  it('pins true Boolean rows ahead of the secondary sort and persists the pin choice', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'above_ma50', label: '>50', kind: 'boolean' }],
        pinnedBooleanKeys: ['above_ma50'],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await wrapper.find('.watchlist__pin-button').trigger('click')
    expect(wrapper.emitted('update:pinnedBooleanKeys')?.at(-1)).toEqual([[]])
  })

  it('persists column grouping without changing virtualized canonical row identity', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'relative_1m', label: '1M relative' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    const groupInput = wrapper.find('input[aria-label="1M relative group"]')
    await groupInput.setValue('Momentum')

    expect(wrapper.emitted('update:columnGroups')?.at(-1)).toEqual([{ relative_1m: 'Momentum' }])
    await wrapper.setProps({ columnGroups: { relative_1m: 'Momentum' } })
    expect(wrapper.find('.watchlist__header em').text()).toBe('Momentum')
    await wrapper.find('.watchlist__row').trigger('click')
    expect(wrapper.emitted('select')?.at(-1)?.[0]).toMatchObject({ instrumentId: 2, symbol: 'XLE' })
  })

  it('stacks saved columns in one dense cell without duplicating their canonical row', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows,
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'relative_1m', label: '1M relative' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await wrapper.find('.watchlist__stack-button').trigger('click')
    expect(wrapper.emitted('update:stackedColumnKeys')?.at(-1)).toEqual([['symbol']])

    await wrapper.setProps({ stackedColumnKeys: ['symbol', 'relative_1m'] })
    expect(wrapper.findAll('.watchlist__row')).toHaveLength(1)
    expect(wrapper.find('.watchlist__stack-cell').text()).toContain('Symbol')
    expect(wrapper.find('.watchlist__stack-cell').text()).toContain('1M relative')
  })

  it('reorders persisted visible columns without changing the selected row identity', async () => {
    const wrapper = mount(VirtualWatchlistTool, {
      props: {
        label: 'Sectors', rows, selected: 'XLE',
        columns: [{ key: 'symbol', label: 'Symbol' }, { key: 'name', label: 'Name' }, { key: 'relative_1m', label: '1M relative' }],
      },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await wrapper.find('button[aria-label="Move Name left"]').trigger('click')

    expect(wrapper.emitted('update:visibleColumnKeys')?.at(-1)).toEqual([['name', 'symbol', 'relative_1m']])
    await wrapper.setProps({ visibleColumnKeys: ['name', 'symbol', 'relative_1m'] })
    expect(wrapper.find('.watchlist__header button').text()).toContain('Name')
    expect(wrapper.find('.watchlist__row--active').exists()).toBe(true)
  })

  it('saves and applies a user-isolated column set using only compatible columns', async () => {
    const saved = { stable_key: 'technical-1', name: 'Technical', version: 1, payload: { configuration: {
      column_keys: ['rsi14', 'symbol', 'unknown'], pinned_boolean_keys: ['above_ma50', 'unknown'],
      column_groups: { rsi14: 'Momentum', unknown: 'Ignore' }, stacked_column_keys: ['rsi14', 'unknown'],
    } } }
    apiGet.mockImplementation((path: string, params?: { kind?: string }) => params?.kind === 'column_set' ? Promise.resolve([saved]) : Promise.resolve([]))
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows, columns: [
        { key: 'symbol', label: 'Symbol' }, { key: 'rsi14', label: 'RSI' }, { key: 'above_ma50', label: '>50', kind: 'boolean' },
      ] },
    })
    await vi.waitFor(() => expect(wrapper.get('button[aria-label="Column sets"]').exists()).toBe(true))
    await wrapper.get('button[aria-label="Column sets"]').trigger('click')
    await wrapper.get('input[aria-label="Column set name"]').setValue('Momentum')
    await wrapper.findAll('button').find(button => button.text() === 'Save set')!.trigger('click')
    expect(apiPut).toHaveBeenCalledWith(expect.stringMatching(/^\/workspaces\/library\/items\/column_set\//), expect.objectContaining({
      kind: 'column_set', name: 'Momentum', payload: expect.objectContaining({ configuration: expect.objectContaining({ column_keys: ['symbol', 'rsi14', 'above_ma50'] }) }),
    }))

    await vi.waitFor(() => expect(wrapper.text()).toContain('Technical'))
    await wrapper.findAll('button').find(button => button.text().includes('Technical'))!.trigger('click')
    expect(wrapper.emitted('update:visibleColumnKeys')?.at(-1)).toEqual([['rsi14', 'symbol']])
    expect(wrapper.emitted('update:pinnedBooleanKeys')?.at(-1)).toEqual([['above_ma50']])
    expect(wrapper.emitted('update:columnGroups')?.at(-1)).toEqual([{ rsi14: 'Momentum' }])
    expect(wrapper.emitted('update:stackedColumnKeys')?.at(-1)).toEqual([['rsi14']])
  })

  it('adds a saved Python column and renders isolated batch cells', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'column', name: 'Last close', versions: [{ id: 77, version_number: 1 }] }])
      if (path === '/research/runs/8/batch-results') return Promise.resolve({ status: 'completed', cells: [{ symbol: 'XLK', status: 'completed', value: 12.5 }, { symbol: 'XLE', status: 'completed', value: 9.5 }, { symbol: 'XLV', status: 'completed', value: 10.5 }] })
      return Promise.resolve([])
    })
    apiPost.mockResolvedValue({ id: 8 })
    const wrapper = mount(VirtualWatchlistTool, { props: { label: 'Sectors', rows } })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('select[aria-label="Python column asset"]').exists()).toBe(true))
    await wrapper.find('select[aria-label="Python column asset"]').setValue('77')
    await wrapper.findAll('.watchlist__python button')[0].trigger('click')
    await vi.waitFor(() => expect(wrapper.emitted('update:pythonColumns')?.at(-1)).toEqual([[{ code_version_id: 77, name: 'Last close v1' }]]))
    await wrapper.setProps({ pythonColumns: [{ code_version_id: 77, name: 'Last close v1' }] })
    await vi.waitFor(() => expect(wrapper.text()).toContain('9.5000'))
    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({ code_version_id: 77, run_config: { symbols: ['XLK', 'XLE', 'XLV'] } }))
  })

  it('runs a persisted Boolean Python condition as a watchlist filter without changing saved screener state', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Positive close', versions: [{ id: 88, version_number: 2 }] }])
      if (path === '/research/runs/9/batch-results') return Promise.resolve({ status: 'completed', cells: [
        { symbol: 'XLK', status: 'completed', value: true },
        { symbol: 'XLE', status: 'completed', value: false },
        { symbol: 'XLV', status: 'completed', value: true },
      ] })
      return Promise.resolve([])
    })
    apiPost.mockResolvedValue({ id: 9 })
    const wrapper = mount(VirtualWatchlistTool, { props: { label: 'Sectors', rows } })
    await vi.waitFor(() => expect(wrapper.find('select[aria-label="Sectors Python condition filter"]').exists()).toBe(true))
    const condition = wrapper.get('select[aria-label="Sectors Python condition filter"]')
    await condition.setValue('88')
    await vi.waitFor(() => expect(wrapper.emitted('update:pythonCondition')?.at(-1)).toEqual([{ code_version_id: 88, name: 'Positive close v2', mode: 'active' }]))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Python condition active · 2/3 match.'))
    expect(wrapper.find('.watchlist__controls b').text()).toBe('2')
    expect(wrapper.text()).toContain('XLK')
    expect(wrapper.text()).not.toContain('XLE')
    expect(wrapper.emitted('update:conditionScreenerId')).toBeUndefined()
    expect(apiPost).toHaveBeenCalledWith('/research/runs', expect.objectContaining({ code_version_id: 88, run_config: { symbols: ['XLK', 'XLE', 'XLV'] } }))
  })

  it('shows a working cancellation control while a persisted Python column batch is running', async () => {
    let resolveBatch: ((value: unknown) => void) | undefined
    apiGet.mockImplementation((path: string) => {
      if (path === '/research/runs/10/batch-results') return new Promise(resolve => { resolveBatch = resolve })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => path === '/research/runs'
      ? Promise.resolve({ id: 10 })
      : Promise.resolve({ status: 'canceled' }))
    const wrapper = mount(VirtualWatchlistTool, {
      props: { label: 'Sectors', rows, pythonColumns: [{ code_version_id: 77, name: 'Last close v1' }] },
    })
    await wrapper.find('.watchlist__columns-button').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('button[aria-label="Cancel Last close v1"]').exists()).toBe(true))
    await wrapper.get('button[aria-label="Cancel Last close v1"]').trigger('click')
    expect(apiPost).toHaveBeenCalledWith('/research/runs/10/cancel', {})
    resolveBatch?.({ status: 'canceled', cells: [] })
  })

  it('traverses canonical rows with Ctrl+wheel in the focused list', async () => {
    const wrapper = mount(VirtualWatchlistTool, { props: { label: 'Sectors', rows, selected: 'XLE' } })
    wrapper.find('.watchlist__scroll').element.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: 1, bubbles: true, cancelable: true }))
    expect(wrapper.emitted('select')?.at(-1)?.[0]).toMatchObject({ symbol: 'XLK', instrumentId: 1 })
  })

  it('traverses backward with Shift+Space', async () => {
    const wrapper = mount(VirtualWatchlistTool, { props: { label: 'Sectors', rows, selected: 'XLK' } })
    await wrapper.find('.watchlist__scroll').trigger('keydown', { key: ' ', shiftKey: true })
    expect(wrapper.emitted('select')?.at(-1)?.[0]).toMatchObject({ symbol: 'XLE', instrumentId: 2 })
  })
})
