import { describe, expect, it } from 'vitest'
import { applicationRoutes, isSharedNavigationItemActive, sharedShellNavigation, usesSharedAppShell } from '@/router'

function route(path: string) {
  return applicationRoutes.find(candidate => candidate.path === path)
}

describe('application route contract', () => {
  it('makes the workstation the authenticated default and symbol entry point', () => {
    const root = route('/')
    const chart = route('/chart')
    const symbolChart = route('/chart/:symbol(.*)')

    expect(root?.component).toBe(chart?.component)
    expect(chart?.component).toBe(symbolChart?.component)
    expect(root?.meta?.public).not.toBe(true)
  })

  it('keeps the legacy interface behind an explicit legacy namespace', () => {
    const legacyPaths = applicationRoutes
      .filter(candidate => candidate.path.startsWith('/legacy/'))
      .map(candidate => candidate.path)

    expect(legacyPaths).toEqual(expect.arrayContaining([
      '/legacy/dashboard',
      '/legacy/chart',
      '/legacy/chart/:symbol(.*)',
      '/legacy/alerts',
      '/legacy/radar',
      '/legacy/strategy-lab',
      '/legacy/strategy-lab-v2',
      '/legacy/baskets',
      '/legacy/etf-holdings',
      '/legacy/screener',
      '/legacy/watchlist',
      '/legacy/settings',
    ]))
    expect(legacyPaths.every(path => path.startsWith('/legacy/'))).toBe(true)
    expect(route('/legacy/chart/:symbol(.*)')?.component).not.toBe(route('/chart/:symbol(.*)')?.component)
    expect(route('/legacy/strategy-lab-v2')?.meta?.public).not.toBe(true)
  })

  it('redirects pre-workstation top-level feature paths into legacy routes', () => {
    const redirects = applicationRoutes.filter(candidate => 'redirect' in candidate)

    expect(Object.fromEntries(redirects.map(candidate => [candidate.path, candidate.redirect]))).toEqual({
      '/dashboard': '/legacy/dashboard',
      '/alerts': '/legacy/alerts',
      '/radar': '/legacy/radar',
      '/strategy-lab': '/legacy/strategy-lab',
      '/strategy-lab-v2': '/legacy/strategy-lab-v2',
      '/baskets': '/legacy/baskets',
      '/etf-holdings': '/legacy/etf-holdings',
      '/screener': '/legacy/screener',
      '/watchlist': '/legacy/watchlist',
      '/settings': '/legacy/settings',
      '/study-lab': { path: '/', query: { tab: 'study-lab' } },
    })
  })

  it('keeps the Study Lab deep link inside the workstation shell', () => {
    expect(route('/study-lab')?.redirect).toEqual({ path: '/', query: { tab: 'study-lab' } })
    expect(route('/study-lab')?.component).toBeUndefined()
  })

  it('routes authenticated legacy screens through the shared shell and keeps workstation, popout, and login frames intact', () => {
    expect(usesSharedAppShell('/legacy/settings')).toBe(true)
    expect(usesSharedAppShell('/legacy/chart/QQQ')).toBe(true)
    expect(usesSharedAppShell('/settings')).toBe(true)
    expect(usesSharedAppShell('/')).toBe(false)
    expect(usesSharedAppShell('/chart/QQQ')).toBe(false)
    expect(usesSharedAppShell('/popout/window-1')).toBe(false)
    expect(usesSharedAppShell('/login')).toBe(false)
    expect(sharedShellNavigation.map(({ path }) => path)).toEqual([
      '/legacy/dashboard', '/legacy/chart', '/legacy/watchlist', '/legacy/screener',
      '/legacy/radar', '/legacy/alerts', '/legacy/baskets', '/legacy/etf-holdings',
      '/legacy/strategy-lab', '/legacy/strategy-lab-v2', '/legacy/settings',
    ])
    expect(isSharedNavigationItemActive('/legacy/chart/QQQ', '/legacy/chart')).toBe(true)
    expect(isSharedNavigationItemActive('/legacy/chart', '/legacy/chart')).toBe(true)
    expect(isSharedNavigationItemActive('/legacy/charting', '/legacy/chart')).toBe(false)
  })

  it('keeps every shared navigation destination backed by one concrete application route', () => {
    const paths = sharedShellNavigation.map(({ path }) => path)
    expect(new Set(paths).size).toBe(paths.length)
    for (const item of sharedShellNavigation) {
      expect(route(item.path), `${item.key} navigation target`).toBeDefined()
      expect(route(item.path), `${item.key} is not a redirect-only target`).not.toHaveProperty('redirect')
    }
    expect(sharedShellNavigation.find(item => item.key === 'etf')?.path).toBe('/legacy/etf-holdings')
    expect(sharedShellNavigation.find(item => item.key === 'strategy-v2')?.path).toBe('/legacy/strategy-lab-v2')
  })
})
