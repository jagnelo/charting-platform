<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <span class="logo-mark">◈</span>
        <span class="logo-name">Charting Platform</span>
      </div>

      <div class="tab-bar">
        <button :class="['tab', { active: mode === 'login' }]"    @click="mode = 'login'">Sign In</button>
        <button :class="['tab', { active: mode === 'register' }]" @click="mode = 'register'">Register</button>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <div class="field">
          <label>Username</label>
          <input v-model="form.username" type="text" autocomplete="username" required />
        </div>

        <template v-if="mode === 'register'">
          <div class="field">
            <label>Email</label>
            <input v-model="form.email" type="email" autocomplete="email" required />
          </div>
        </template>

        <div class="field">
          <label>Password</label>
          <input v-model="form.password" type="password" autocomplete="current-password" required />
        </div>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          <span v-if="loading">…</span>
          <span v-else>{{ mode === 'login' ? 'Sign In' : 'Create Account' }}</span>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router    = useRouter()

const mode    = ref<'login' | 'register'>('login')
const loading = ref(false)
const error   = ref('')
const form    = ref({ username: '', email: '', password: '' })

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await authStore.login(form.value.username, form.value.password)
    } else {
      await authStore.register(form.value.username, form.value.email, form.value.password)
    }
    router.push('/chart')
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #080808;
  background-image: radial-gradient(circle at 30% 40%, #0d1a2a 0%, transparent 60%),
                    radial-gradient(circle at 70% 70%, #0a1a0a 0%, transparent 50%);
}

.login-card {
  width: 360px;
  background: #0f0f0f;
  border: 1px solid #1e1e1e;
  border-radius: 10px;
  padding: 36px 32px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6);
}

.login-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 28px;
  justify-content: center;
}

.logo-mark { font-size: 28px; color: #64b5f6; }
.logo-name { font-size: 18px; color: #ddd; font-weight: 700; letter-spacing: 0.03em; }

.tab-bar {
  display: flex;
  background: #1a1a1a;
  border-radius: 6px;
  padding: 3px;
  margin-bottom: 24px;
}

.tab {
  flex: 1;
  background: none;
  border: none;
  color: #666;
  padding: 7px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}
.tab.active { background: #1a3a5c; color: #64b5f6; }

.login-form { display: flex; flex-direction: column; gap: 16px; }

.field { display: flex; flex-direction: column; gap: 5px; }
.field label { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.field input {
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 5px;
  padding: 9px 12px;
  color: #ddd;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}
.field input:focus { border-color: #64b5f6; }

.error-msg { color: #ef5350; font-size: 12px; text-align: center; }

.submit-btn {
  background: #1a3a5c;
  border: 1px solid #64b5f6;
  color: #64b5f6;
  border-radius: 5px;
  padding: 10px;
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
  margin-top: 4px;
  transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: #1e4a7a; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
