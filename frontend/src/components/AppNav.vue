<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()

function logout() {
  auth.logout()
  router.push('/login')
}

function isActive(name: string) {
  return route.name === name || route.name?.toString().startsWith(name)
}
</script>

<template>
  <nav class="border-b border-sand-200 bg-sand-50">
    <div class="max-w-3xl mx-auto px-3 sm:px-4 flex items-center justify-between h-12 sm:h-14">
      <div class="flex items-center gap-0.5 sm:gap-1">
        <router-link
          to="/"
          class="mr-4 sm:mr-6 hidden sm:inline-flex items-baseline gap-1.5 group select-none"
          aria-label="my archivarius"
        >
          <span class="self-center text-accent text-[0.65rem] leading-none mr-0.5 transition-transform duration-300 group-hover:scale-125">◆</span>
          <span class="italic text-base text-sand-400 transition-colors group-hover:text-sand-500">my</span>
          <span class="text-xl text-sand-800 tracking-[0.12em] transition-colors group-hover:text-accent">archivarius</span>
        </router-link>
        <router-link
          to="/"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm"
          :class="isActive('diary') ? 'bg-sand-200 text-sand-900 font-medium' : 'text-sand-600 hover:text-sand-800'"
        >
          {{ t('nav.diary') }}
        </router-link>
        <router-link
          to="/buffer"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm"
          :class="isActive('buffer') ? 'bg-sand-200 text-sand-900 font-medium' : 'text-sand-600 hover:text-sand-800'"
        >
          {{ t('nav.buffer') }}
        </router-link>
        <router-link
          to="/highlights"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm"
          :class="isActive('highlights') ? 'bg-sand-200 text-sand-900 font-medium' : 'text-sand-600 hover:text-sand-800'"
        >
          {{ t('nav.highlights') }}
        </router-link>
        <router-link
          to="/settings"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm"
          :class="isActive('settings') ? 'bg-sand-200 text-sand-900 font-medium' : 'text-sand-600 hover:text-sand-800'"
        >
          ⚙️
        </router-link>
      </div>
      <button
        @click="logout"
        class="text-sm text-sand-500 hover:text-sand-700"
      >
        {{ t('nav.logout') }}
      </button>
    </div>
  </nav>
</template>
