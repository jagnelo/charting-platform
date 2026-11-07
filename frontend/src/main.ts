import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { router } from './router'
import App from './App.vue'
import { installAuthSessionCleanup } from './lib/authSession'
import './styles/workstation-tokens.css'

const app = createApp(App)
const pinia = createPinia()
const queryClient = new QueryClient()
app.use(pinia)
installAuthSessionCleanup(queryClient, pinia)
app.use(VueQueryPlugin, { queryClient })
app.use(router)
app.mount('#app')
