import { vi } from 'vitest'

// Mock uPlot — it requires a real canvas which jsdom doesn't support
vi.mock('uplot', () => ({
  default: vi.fn().mockImplementation((_options, data) => ({
    destroy: vi.fn(),
    setData: vi.fn(),
    setSize: vi.fn(),
    setCursor: vi.fn(),
    valToPos: vi.fn().mockReturnValue(100),
    posToVal: vi.fn().mockReturnValue(150.0),
    scales: { x: {}, y: {} },
    cursor: { idx: null, left: 0, top: 0 },
    data: data ?? [[], [], [], [], [], []],
    width: 900,
    height: 500,
    ctx: {
      save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(),
      fillText: vi.fn(), strokeStyle: '', lineWidth: 1,
      setLineDash: vi.fn(), fillStyle: '',
    },
  })),
}))

// Mock window.localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// Mock fetch globally
global.fetch = vi.fn()
