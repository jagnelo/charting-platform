import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LoginView     from '@/views/LoginView.vue'
import ChartView     from '@/views/ChartView.vue'
import AlertsView    from '@/views/AlertsView.vue'
import SettingsView  from '@/views/SettingsView.vue'
import ScreenerView  from '@/views/ScreenerView.vue'
import WatchlistView from '@/views/WatchlistView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/',              redirect: '/chart' },
    { path: '/chart',         component: ChartView },
    { path: '/chart/:symbol(.*)', component: ChartView },
    { path: '/alerts',        component: AlertsView },
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
