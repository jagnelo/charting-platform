import { describe, expect, it } from 'vitest'
import { applicationRoutes } from '@/router'

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
      '/legacy/baskets',
      '/legacy/etf-holdings',
      '/legacy/screener',
      '/legacy/watchlist',
      '/legacy/settings',
    ]))
    expect(legacyPaths.every(path => path.startsWith('/legacy/'))).toBe(true)
    expect(route('/legacy/chart/:symbol(.*)')?.component).not.toBe(route('/chart/:symbol(.*)')?.component)
  })

  it('redirects pre-workstation top-level feature paths into legacy routes', () => {
    const redirects = applicationRoutes.filter(candidate => 'redirect' in candidate)

    expect(Object.fromEntries(redirects.map(candidate => [candidate.path, candidate.redirect]))).toEqual({
      '/dashboard': '/legacy/dashboard',
      '/alerts': '/legacy/alerts',
      '/radar': '/legacy/radar',
      '/strategy-lab': '/legacy/strategy-lab',
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
})
