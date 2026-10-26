import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { sharedShellNavigation } from '@/router'

const stores = vi.hoisted(() => ({
  auth: {
    isAuthenticated: true,
    user: { username: 'analyst' },
    logout: vi.fn(),
  },
  alerts: {
    unviewedCount: 120,
    connectWebSocket: vi.fn(),
    disconnectWebSocket: vi.fn(),
  },
}))

vi.mock('@/stores/auth', () => ({ useAuthStore: () => stores.auth }))
vi.mock('@/stores/alerts', () => ({ useAlertsStore: () => stores.alerts }))

import App from '@/App.vue'

const appSource = readFileSync(resolve(process.cwd(), 'src/App.vue'), 'utf8')
const appStyles = appSource.match(/<style>\s*([\s\S]*?)<\/style>/)?.[1] ?? ''
const workstationTokens = readFileSync(resolve(process.cwd(), 'src/styles/workstation-tokens.css'), 'utf8')
const componentStyles = (path: string) => {
  const source = readFileSync(resolve(process.cwd(), path), 'utf8')
  return Array.from(source.matchAll(/<style(?:\s[^>]*)?>([\s\S]*?)<\/style>/g), match => match[1]).join('\n')
}

const page = { template: '<section>Route content</section>' }

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...sharedShellNavigation.map(({ path }) => ({ path, component: page })),
      { path: '/chart/:symbol(.*)', component: page },
      { path: '/popout/:windowKey', component: page },
      { path: '/legacy/chart/:symbol(.*)', component: page },
      { path: '/', component: page },
      { path: '/login', component: page },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [router],
      stubs: { StatusBar: true, Notification: true },
    },
  })
  await router.isReady()
  return wrapper
}

describe('application shell', () => {
  it('keeps shell theme selectors aligned with actual routed view roots and preserves workstation reset', () => {
    const routedViews = [
      'DashboardView.vue', 'ChartView.vue', 'AlertsView.vue', 'SettingsView.vue',
      'ScreenerView.vue', 'WatchlistView.vue', 'RadarView.vue', 'StrategyLabView.vue',
      'StrategyLabV2View.vue', 'BasketsView.vue', 'ETFHoldingsView.vue',
    ]

    for (const view of routedViews) {
      const source = readFileSync(resolve(process.cwd(), 'src/views', view), 'utf8')
      const rootClass = source.match(/<template>\s*<(?:div|main)\b[^>]*?\bclass="([^"]+)"/s)?.[1]?.split(/\s+/)[0]
      expect(rootClass, `${view} root class`).toBeTruthy()
      expect(appSource, `${view} root theme selector`).toContain(`.${rootClass}`)
    }

    const etfSource = readFileSync(resolve(process.cwd(), 'src/views/ETFHoldingsView.vue'), 'utf8')
    expect(etfSource.match(/<template>\s*<div\b[^>]*?\bclass="([^"]+)"/s)?.[1]).toBe('holdings-view')
    expect(appSource).toContain('.holdings-view')
    expect(appSource).not.toContain('.etf-holdings-view')
    const radarSource = readFileSync(resolve(process.cwd(), 'src/views/RadarView.vue'), 'utf8')
    expect(radarSource).toContain("'radar-view--busy': runningScan")
    expect(appSource).toContain('.radar-view')
    const strategyV2 = readFileSync(resolve(process.cwd(), 'src/views/StrategyLabV2View.vue'), 'utf8')
    expect(strategyV2).toContain('.strategy-lab-v2__item.is-selected')
    expect(strategyV2).toContain('font-family: var(--tc-font-family)')
    const dashboard = readFileSync(resolve(process.cwd(), 'src/views/DashboardView.vue'), 'utf8')
    expect(dashboard).toContain('.tab-bar { gap: 0; padding: 0 8px;')
    expect(dashboard).toContain('.widget-catalog { border-color: var(--tc-border)')
    const watchlist = readFileSync(resolve(process.cwd(), 'src/views/WatchlistView.vue'), 'utf8')
    const screener = readFileSync(resolve(process.cwd(), 'src/views/ScreenerView.vue'), 'utf8')
    expect(watchlist).toMatch(/\.watchlist-view\s*\{[^}]*font-family:\s*var\(--tc-font-family\)/s)
    expect(screener).toContain('.screener-view { display: flex; height: 100%; min-width: 0; color: var(--tc-text); font-size: 12px; overflow: hidden; position: relative; font-family: var(--tc-font-family); background: var(--tc-window-bg); }')
    expect(screener).toContain('.td-num  { color: var(--tc-text-muted); font-family: monospace; font-variant-numeric: tabular-nums; }')
    expect(strategyV2).toContain('font-size: 12px;')
    expect(watchlist).toContain('.wlm-placeholder')
    expect(watchlist).toContain('color: var(--tc-text-muted);')
    expect(readFileSync(resolve(process.cwd(), 'src/views/BasketsView.vue'), 'utf8')).toContain('.basket-panel, .basket-card')
    expect(readFileSync(resolve(process.cwd(), 'src/views/SettingsView.vue'), 'utf8')).toContain('.provider-summary-card, .usage-meta-card')
    expect(appStyles).toContain('border-radius: var(--tc-radius);\n  background-color: var(--tc-window-bg);')
    expect(appStyles).not.toContain('[aria-current="true"]')
    expect(appSource).toContain('* { box-sizing: border-box; margin: 0; padding: 0; }')
    expect(appSource).not.toMatch(/<div\s+id="app"/)
    expect(appStyles).toContain('body:has(#app .tc-legacy-app)')
    expect(appStyles).toContain('grid-template-columns: minmax(0, 1fr);')
    expect(appStyles).toContain('.tc-app-route-frame > * { width: 100%; max-width: 100%; height: 100%; min-width: 0; min-height: 0; }')
    expect(appStyles).toContain('.tc-app-route-frame { width: 100%; flex: 1; min-width: 0; min-height: 0; overflow: hidden; font-size: 12px; }')
    expect(appStyles).toContain('font-size: 12px;')
    const settings = readFileSync(resolve(process.cwd(), 'src/views/SettingsView.vue'), 'utf8')
    expect(settings).toContain('.availability-row { grid-template-columns: minmax(0, 1fr); gap: 5px; }')
    expect(appSource).toContain('[class*="--active"]')
    expect(appSource).toContain('[class*="status"]')
    for (const teleportedSurface of ['.editor-box', '.indicator-settings-dialog', '.row-dropdown', '.quick-link-menu', '.config-modal', '[class*="-results"]', '[role="tooltip"]', '.notification']) {
      expect(appSource, `teleported surface ${teleportedSurface}`).toContain(teleportedSurface)
    }
    expect(appSource).toContain('.config-modal .config-field > :is(input,select,textarea)')
    expect(appSource).toContain('background-color: var(--tc-input-bg);')
  })

  it('keeps selected buttons, cards, rows, and tabs distinguishable from neutral controls', () => {
    const style = document.createElement('style')
    style.textContent = `${workstationTokens}\n${appStyles}`
    document.head.append(style)
    document.body.innerHTML = `
      <div id="app">
        <div class="tc-legacy-app">
          <div class="tc-app-route-frame">
          <section class="strategy-lab-v2">
            <button class="strategy-lab-v2__item">Ordinary Strategy resource</button>
            <button class="strategy-lab-v2__item is-selected" aria-current="true">Selected Strategy resource</button>
          </section>
          <button class="holding-row">Ordinary holding</button>
          <button class="holding-row holding-row--selected" aria-selected="true">IWM</button>
          <div class="basket-card">Ordinary basket</div>
          <div class="basket-card basket-card--active">Selected basket</div>
          <table><tbody>
            <tr><td>Ordinary row</td></tr>
            <tr class="holding-row--selected" aria-selected="true"><td>Selected row</td></tr>
          </tbody></table>
          <button role="tab">Ordinary tab</button>
          <button role="tab" class="workstation__tab--active" aria-selected="true">Selected tab</button>
          <button disabled>Disabled</button>
          <button class="provider-status-warning">Provider status</button>
          </div>
        </div>
      </div>`

    try {
      const frame = document.querySelector('.tc-app-route-frame')!
      const computed = (selector: string, property: 'backgroundColor' | 'color') =>
        getComputedStyle(frame.querySelector(selector) as Element)[property]
      expect(getComputedStyle(document.body).fontSize).toBe('12px')
      expect(computed('.holding-row:not(.holding-row--selected)', 'backgroundColor'))
        .not.toBe(computed('.holding-row--selected[aria-selected="true"]', 'backgroundColor'))
      expect(computed('.strategy-lab-v2__item:not(.is-selected)', 'backgroundColor'))
        .not.toBe(computed('.strategy-lab-v2__item.is-selected[aria-current="true"]', 'backgroundColor'))
      expect(computed('.strategy-lab-v2__item:not(.is-selected)', 'color'))
        .not.toBe(computed('.strategy-lab-v2__item.is-selected[aria-current="true"]', 'color'))
      expect(computed('.holding-row:not(.holding-row--selected)', 'color'))
        .not.toBe(computed('.holding-row--selected[aria-selected="true"]', 'color'))
      expect(computed('.basket-card', 'backgroundColor')).not.toBe(computed('.basket-card--active', 'backgroundColor'))
      expect(computed('tr:not([aria-selected="true"]) > td', 'backgroundColor'))
        .not.toBe(computed('tr[aria-selected="true"] > td', 'backgroundColor'))
      expect(computed('[role="tab"]:not([aria-selected="true"])', 'color'))
        .not.toBe(computed('[role="tab"][aria-selected="true"]', 'color'))
      expect(computed('.provider-status-warning', 'backgroundColor'))
        .not.toBe(computed('.holding-row:not(.holding-row--selected)', 'backgroundColor'))

      const disabled = frame.querySelector('button:disabled')!
      expect(getComputedStyle(disabled).opacity).toBe('0.58')
      expect(getComputedStyle(disabled).cursor).toBe('not-allowed')

      const rules = Array.from(style.sheet?.cssRules ?? [])
        .filter((rule): rule is CSSStyleRule => 'selectorText' in rule && 'style' in rule)
      const buttonHover = rules.find(rule => rule.selectorText.includes(':where') && rule.selectorText.endsWith(':hover'))
      expect(buttonHover?.style.length).toBe(1)
      expect(buttonHover?.style.getPropertyValue('border-color')).toBe('var(--tc-accent)')
      expect(buttonHover?.style.getPropertyValue('background-color')).toBe('')
      expect(buttonHover?.style.getPropertyValue('color')).toBe('')
      expect(rules.some(rule => rule.selectorText.includes('tr:is(') && rule.selectorText.includes(':hover > td'))).toBe(true)
      expect(rules.some(rule => rule.selectorText.includes('[class*="is-selected"]'))).toBe(true)
    } finally {
      document.body.innerHTML = ''
      style.remove()
    }
  })

  it('renders dense readable route states and tokenized inner panels from their owning components', () => {
    const styles = [
      'src/views/StrategyLabV2View.vue',
      'src/views/WatchlistView.vue',
      'src/views/ScreenerView.vue',
      'src/views/RadarView.vue',
      'src/views/BasketsView.vue',
      'src/views/ETFHoldingsView.vue',
      'src/views/SettingsView.vue',
      'src/views/DashboardView.vue',
      'src/components/etf/ETFHoldingsPanel.vue',
      'src/components/chart/IndicatorPanel.vue',
      'src/components/watchlist/WatchlistPanel.vue',
      'src/components/strategy/StrategyRuleTreeEditor.vue',
      'src/components/common/SearchBar.vue',
      'src/components/common/TagPicker.vue',
    ].map(componentStyles).join('\n')
    const style = document.createElement('style')
    style.textContent = `${workstationTokens}\n${appStyles}\n${styles}`
    document.head.append(style)
    document.body.innerHTML = `
      <div id="app">
        <div class="tc-legacy-app">
          <div class="tc-app-route-frame">
          <section class="strategy-lab-v2"><p class="strategy-lab-v2__subtitle">Study details</p></section>
          <section class="watchlist-view"><div class="wls-empty">No watchlists yet</div></section>
          <section class="screener-view"><div class="empty-list">No screeners yet</div></section>
          <section class="radar-view"><div class="empty-row">No detections</div></section>
          <section class="basket-view"><section class="basket-panel">New basket</section></section>
          <section class="holdings-view"><aside class="holding-detail">Selected holding</aside></section>
          <section class="settings-view"><div class="provider-summary-card"><span>Unknown quota</span></div></section>
          <section class="etf-holdings-panel"><div class="holdings-table">Holdings</div></section>
          <section class="side-panel"><div class="empty-hint">No alerts</div></section>
          <section class="strategy-lab-view"><div class="group-card">Rule group</div></section>
          </div>
        </div>
      </div>`
    document.body.insertAdjacentHTML('beforeend', `
      <div class="config-modal">
        <label class="config-field">Notes mode <select><option>Notes</option></select></label>
        <small class="config-help">Choose how the widget stores items.</small>
      </div>`)

    try {
      const frame = document.querySelector('.tc-app-route-frame')!
      const styleOf = (selector: string) => getComputedStyle(frame.querySelector(selector)!)
      expect(styleOf('.strategy-lab-v2__subtitle').fontSize).toBe('12px')
      expect(getComputedStyle(document.querySelector('.config-modal .config-field')!).color).toBe('var(--tc-text-muted)')
      expect(getComputedStyle(document.querySelector('.config-modal .config-help')!).color).toBe('var(--tc-text-muted)')
      expect(getComputedStyle(document.querySelector('.config-modal select')!).backgroundColor).toBe('var(--tc-input-bg)')
      for (const selector of ['.wls-empty', '.empty-list', '.empty-row', '.empty-hint']) {
        expect(styleOf(selector).color, `${selector} uses a readable token color`).not.toBe('rgb(51, 51, 51)')
      }
      expect(getComputedStyle(document.documentElement).getPropertyValue('--tc-radius').trim()).toBe('0px')
      for (const selector of ['.basket-panel', '.holding-detail', '.provider-summary-card', '.group-card']) {
        expect(styleOf(selector).borderRadius, `${selector} uses the shared radius token`).toBe('var(--tc-radius)')
      }
    } finally {
      document.body.innerHTML = ''
      style.remove()
    }
  })

  it('renders the shared labeled navigation on legacy routes and keeps active state and account controls', async () => {
    const wrapper = await mountAt('/legacy/chart/QQQ')

    expect(wrapper.classes()).toContain('tc-legacy-app')
    expect(wrapper.get('nav[aria-label="Main navigation"]').text()).toContain('ETF Holdings')
    expect(wrapper.get('nav[aria-label="Main navigation"]').text()).toContain('Strategy Lab v2')
    expect(wrapper.get('a[href="/legacy/chart"]').attributes('aria-current')).toBe('page')
    expect(wrapper.text()).toContain('99+')
    expect(wrapper.get('.tc-app-account-name').text()).toBe('analyst')
    expect(wrapper.get('.tc-app-signout').attributes('aria-label')).toBe('Sign out analyst')
    wrapper.unmount()
  })

  it('leaves workstation and login routes outside the legacy navigation wrapper', async () => {
    const workstation = await mountAt('/')
    expect(workstation.classes()).not.toContain('tc-legacy-app')
    expect(workstation.find('nav[aria-label="Main navigation"]').exists()).toBe(false)
    workstation.unmount()

    const login = await mountAt('/login')
    expect(login.classes()).not.toContain('tc-legacy-app')
    expect(login.find('nav[aria-label="Main navigation"]').exists()).toBe(false)
    login.unmount()
  })

  it('keeps canonical chart and popout inside a definite height-bearing application root', async () => {
    expect(appStyles).toMatch(/#app\s+\.tc-application-root\s*\{[^}]*height:\s*100%/s)

    for (const path of ['/chart/SPY', '/popout/workspace-window']) {
      const wrapper = await mountAt(path)
      expect(wrapper.classes()).toContain('tc-application-root')
      expect(wrapper.classes()).not.toContain('tc-legacy-app')
      expect(wrapper.findAll('[id="app"]')).toHaveLength(0)
      wrapper.unmount()
    }

    const legacy = await mountAt('/legacy/chart/SPY')
    expect(legacy.classes()).toEqual(['tc-application-root', 'tc-legacy-app'])
    legacy.unmount()
  })
})
