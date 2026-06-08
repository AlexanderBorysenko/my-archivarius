<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const error = ref('')
const loading = ref(false)

const botId = import.meta.env.VITE_TELEGRAM_BOT_ID

function getTelegramAuthUrl() {
  const origin = encodeURIComponent(window.location.origin)
  const returnTo = encodeURIComponent(window.location.origin + '/login')
  return `https://oauth.telegram.org/auth?bot_id=${botId}&origin=${origin}&return_to=${returnTo}&request_access=write`
}

async function handleTelegramRedirect() {
  const hash = window.location.hash
  if (!hash.includes('tgAuthResult=')) return

  const encoded = hash.split('tgAuthResult=')[1]
  if (!encoded) return

  try {
    loading.value = true
    const decoded = atob(encoded)
    const authData = JSON.parse(decoded)
    if (!authData || typeof authData !== 'object') {
      throw new Error('Telegram auth declined')
    }
    await auth.loginWithTelegram(authData)
    window.location.hash = ''
    router.push('/')
  } catch (e) {
    error.value = t('login.error')
    window.location.hash = ''
  } finally {
    loading.value = false
  }
}

onMounted(handleTelegramRedirect)
</script>

<template>
  <div class="flex flex-col items-center justify-center min-h-[80vh]">
    <div class="text-center mb-12">
      <h1 class="text-4xl font-light text-sand-800 mb-3">{{ t('login.title') }}</h1>
      <p class="text-sand-500 text-lg">
        {{ t('login.subtitle') }}
      </p>
    </div>

    <div class="bg-white rounded-2xl shadow-sm border border-sand-200 p-8 w-full max-w-sm">
      <p class="text-sand-600 text-center mb-6">
        {{ t('login.prompt') }}
      </p>

      <div v-if="loading" class="flex justify-center mb-4">
        <p class="text-sand-500">{{ t('login.authorizing') }}</p>
      </div>

      <div v-else class="flex justify-center mb-4">
        <a
          :href="getTelegramAuthUrl()"
          class="bg-[#54a9eb] text-white px-6 py-3 rounded-lg hover:bg-[#4a96d1] flex items-center gap-2 font-medium no-underline"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.03-1.99 1.27-5.63 3.72-.53.36-1.01.54-1.44.53-.47-.01-1.38-.27-2.06-.49-.83-.27-1.49-.42-1.43-.88.03-.24.37-.49 1.02-.74 3.99-1.74 6.65-2.89 7.99-3.45 3.81-1.58 4.6-1.86 5.12-1.87.11 0 .37.03.53.14.14.1.18.23.2.33.02.12.01.28-.01.4z"/>
          </svg>
          {{ t('login.signIn') }}
        </a>
      </div>

      <p v-if="error" class="text-xs text-red-500 text-center mb-2">{{ error }}</p>

      <p class="text-xs text-sand-400 text-center">
        {{ t('login.privacy') }}
      </p>
    </div>
  </div>
</template>
