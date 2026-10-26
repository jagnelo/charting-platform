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

        <div v-if="error" class="error-msg auth-error">{{ error }}</div>

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
  padding: 24px;
  background: var(--tc-shell-bg, #0d1013);
  background-image: radial-gradient(circle at 30% 40%, #68b6e91a 0%, transparent 60%),
                    radial-gradient(circle at 70% 70%, #63bd8510 0%, transparent 50%);
  color: var(--tc-text, #d5dde4);
  font-family: var(--tc-font-family, "Segoe UI", Arial, sans-serif);
}

.login-card {
  width: min(100%, 380px);
  background: var(--tc-window-bg, #15191e);
  border: 1px solid var(--tc-border, #303940);
  border-radius: var(--tc-radius, 0px);
  padding: 30px 28px;
  box-shadow: var(--tc-shadow, 0 3px 10px #000a);
}

.login-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 28px;
  justify-content: center;
}

.logo-mark { font-size: 26px; color: var(--tc-accent, #68b6e9); }
.logo-name { font-size: 17px; color: var(--tc-text, #d5dde4); font-weight: 700; letter-spacing: 0.02em; }

.tab-bar {
  display: flex;
  background: var(--tc-control-bg, #20282e);
  border: 1px solid var(--tc-border, #303940);
  border-radius: var(--tc-radius, 0px);
  padding: 3px;
  margin-bottom: 24px;
}

.tab {
  flex: 1;
  background: none;
  border: none;
  color: var(--tc-text-muted, #81909a);
  padding: 7px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}
.tab.active { background: #68b6e91a; color: var(--tc-accent-soft, #8fc7ea); }

.login-form { display: flex; flex-direction: column; gap: 16px; }

.field { display: flex; flex-direction: column; gap: 5px; }
.field label { font-size: 11px; color: var(--tc-text-muted, #81909a); text-transform: uppercase; letter-spacing: 0.05em; }
.field input {
  background: var(--tc-input-bg, #11161a);
  border: 1px solid var(--tc-border-strong, #4b5660);
  border-radius: var(--tc-radius, 0px);
  padding: 9px 12px;
  color: var(--tc-text, #d5dde4);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}
.field input:focus-visible { border-color: var(--tc-accent, #68b6e9); outline: 2px solid var(--tc-accent, #68b6e9); outline-offset: 1px; }

.error-msg { color: #ef5350; font-size: 12px; text-align: center; }

.submit-btn {
  background: var(--tc-control-bg, #20282e);
  border: 1px solid var(--tc-accent, #68b6e9);
  color: var(--tc-accent-soft, #8fc7ea);
  border-radius: var(--tc-radius, 0px);
  padding: 10px;
  cursor: pointer;
  font-size: 14px;
  font-family: inherit;
  margin-top: 4px;
  transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: #68b6e926; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 480px) {
  .login-page { padding: 16px; }
  .login-card { padding: 24px 20px; }
}
</style>
