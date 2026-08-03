import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const LoginView = () => import('@/views/LoginView.vue')
const WorkstationView = () => import('@/views/WorkstationView.vue')
const DashboardView = () => import('@/views/DashboardView.vue')
const ChartView = () => import('@/views/ChartView.vue')
const AlertsView = () => import('@/views/AlertsView.vue')
const SettingsView = () => import('@/views/SettingsView.vue')
const ScreenerView = () => import('@/views/ScreenerView.vue')
const WatchlistView = () => import('@/views/WatchlistView.vue')
const RadarView = () => import('@/views/RadarView.vue')
const StrategyLabView = () => import('@/views/StrategyLabView.vue')
const BasketsView = () => import('@/views/BasketsView.vue')
const ETFHoldingsView = () => import('@/views/ETFHoldingsView.vue')

/**
 * The route table is exported as a contract so the workstation/legacy boundary
 * can be verified without mounting every lazy-loaded view. Keep the ordering
 * stable: the parameterized workstation route must remain after `/chart`.
 */
export const applicationRoutes = [
  { path: '/login', component: LoginView, meta: { public: true } },
  { path: '/', component: WorkstationView },
  { path: '/chart', component: WorkstationView },
  { path: '/chart/:symbol(.*)', component: WorkstationView },
  { path: '/popout/:windowKey', component: WorkstationView },
  // Study Lab is a workstation tool, not a second application shell. Keep the
  // deep link, but land it in the persisted factory tab so symbol/link/layout
  // state has one owner.
  { path: '/study-lab', redirect: { path: '/', query: { tab: 'study-lab' } } },
  { path: '/legacy/dashboard', component: DashboardView },
  { path: '/legacy/chart', component: ChartView },
  { path: '/legacy/chart/:symbol(.*)', component: ChartView },
  { path: '/legacy/alerts', component: AlertsView },
  { path: '/legacy/radar', component: RadarView },
  { path: '/legacy/strategy-lab', component: StrategyLabView },
  { path: '/legacy/baskets', component: BasketsView },
  { path: '/legacy/etf-holdings', component: ETFHoldingsView },
  { path: '/legacy/screener', component: ScreenerView },
  { path: '/legacy/watchlist', component: WatchlistView },
  { path: '/legacy/settings', component: SettingsView },
  { path: '/dashboard', redirect: '/legacy/dashboard' },
  { path: '/alerts', redirect: '/legacy/alerts' },
  { path: '/radar', redirect: '/legacy/radar' },
  { path: '/strategy-lab', redirect: '/legacy/strategy-lab' },
  { path: '/baskets', redirect: '/legacy/baskets' },
  { path: '/etf-holdings', redirect: '/legacy/etf-holdings' },
  { path: '/screener', redirect: '/legacy/screener' },
  { path: '/watchlist', redirect: '/legacy/watchlist' },
  { path: '/settings', redirect: '/legacy/settings' },
] as const

export const router = createRouter({
  history: createWebHistory(),
  routes: applicationRoutes,
})

// Navigation guard — redirect to /login if not authenticated
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const auth = useAuthStore()
  if (!auth.isAuthenticated) return '/login'
  // Fetch user profile if not loaded
  if (!auth.user) await auth.fetchMe()
  return true
})
