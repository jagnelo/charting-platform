import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useScreenerAlertsStore } from '@/stores/screener_alerts'

function alert(id: number, screenerId = 7) {
  return {
    id,
    screener_id: screenerId,
    screener_name: 'Breakout Radar',
    trigger_type: 'both',
    status: 'active',
    repeat: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('useScreenerAlertsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('loads and creates screener alerts', async () => {
    const store = useScreenerAlertsStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([alert(1)])
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(alert(2, 9))

    await store.loadAlerts()
    expect(store.alerts).toHaveLength(1)

    await store.createAlert(9, 'entered', true, 'watch closely')
    expect(store.alerts[0].id).toBe(2)
  })

  it('updates, rearms, deletes, and finds alerts by screener', async () => {
    const store = useScreenerAlertsStore()
    store.alerts = [alert(1), { ...alert(2, 9), status: 'triggered' }] as any

    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ...alert(1), repeat: true })
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(alert(2, 9))
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    await store.updateAlert(1, { repeat: true })
    expect(store.alerts.find(a => a.id === 1)?.repeat).toBe(true)

    await store.rearmAlert(2)
    expect(store.alerts.find(a => a.id === 2)?.status).toBe('active')

    expect(store.forScreener(7)?.id).toBe(1)

    await store.deleteAlert(1)
    expect(store.alerts.some(a => a.id === 1)).toBe(false)
  })

  it('returns null from createAlert when the API fails', async () => {
    const store = useScreenerAlertsStore()
    ;(api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'))

    await expect(store.createAlert(11)).resolves.toBeNull()
  })
})
