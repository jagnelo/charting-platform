import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const LoginView = () => import('@/views/LoginView.vue')
const DashboardView = () => import('@/views/DashboardView.vue')
const ChartView = () => import('@/views/ChartView.vue')
const AlertsView = () => import('@/views/AlertsView.vue')
const SettingsView = () => import('@/views/SettingsView.vue')
const ScreenerView = () => import('@/views/ScreenerView.vue')
const WatchlistView = () => import('@/views/WatchlistView.vue')
const RadarView = () => import('@/views/RadarView.vue')
const StrategyLabView = () => import('@/views/StrategyLabView.vue')

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/',              redirect: '/dashboard' },
    { path: '/dashboard',     component: DashboardView },
    { path: '/chart',         component: ChartView },
    { path: '/chart/:symbol(.*)', component: ChartView },
    { path: '/alerts',        component: AlertsView },
    { path: '/radar',         component: RadarView },
    { path: '/strategy-lab',  component: StrategyLabView },
    { path: '/screener',      component: ScreenerView },
    { path: '/watchlist',     component: WatchlistView },
    { path: '/settings',      component: SettingsView },
  ],
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
