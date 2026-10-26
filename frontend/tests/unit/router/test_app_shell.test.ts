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

const page = { template: '<section>Route content</section>' }

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...sharedShellNavigation.map(({ path }) => ({ path, component: page })),
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
    expect(appSource).toContain('* { box-sizing: border-box; margin: 0; padding: 0; }')
    expect(appSource).toContain('[class*="--active"]')
    expect(appSource).toContain('[class*="status"]')
    for (const teleportedSurface of ['.editor-box', '.indicator-settings-dialog', '.row-dropdown', '.quick-link-menu', '[class*="-results"]', '[role="tooltip"]', '.notification']) {
      expect(appSource, `teleported surface ${teleportedSurface}`).toContain(teleportedSurface)
    }
  })

  it('keeps selected buttons, cards, rows, and tabs distinguishable from neutral controls', () => {
    const style = document.createElement('style')
    style.textContent = `${workstationTokens}\n${appStyles}`
    document.head.append(style)
    document.body.innerHTML = `
      <div id="app" class="tc-legacy-app">
        <div class="tc-app-route-frame">
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
      </div>`

    try {
      const frame = document.querySelector('.tc-app-route-frame')!
      const computed = (selector: string, property: 'backgroundColor' | 'color') =>
        getComputedStyle(frame.querySelector(selector) as Element)[property]
      expect(computed('.holding-row:not(.holding-row--selected)', 'backgroundColor'))
        .not.toBe(computed('.holding-row--selected[aria-selected="true"]', 'backgroundColor'))
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
    } finally {
      document.body.innerHTML = ''
      style.remove()
    }
  })

  it('renders the shared labeled navigation on legacy routes and keeps active state and account controls', async () => {
    const wrapper = await mountAt('/legacy/chart/QQQ')

    expect(wrapper.get('#app').classes()).toContain('tc-legacy-app')
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
    expect(workstation.get('#app').classes()).not.toContain('tc-legacy-app')
    expect(workstation.find('nav[aria-label="Main navigation"]').exists()).toBe(false)
    workstation.unmount()

    const login = await mountAt('/login')
    expect(login.get('#app').classes()).not.toContain('tc-legacy-app')
    expect(login.find('nav[aria-label="Main navigation"]').exists()).toBe(false)
    login.unmount()
  })
})
