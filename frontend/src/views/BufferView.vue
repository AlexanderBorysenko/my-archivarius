<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getBuffer, bake } from '../api'
import { useEvents } from '../composables/useEvents'
import type { RawMessage } from '../types/message'
import MessageCard from '../components/message/MessageCard.vue'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

interface AudioJob {
  id: string
  duration: number
  status: string
}

interface ActiveBake {
  id: string
  status: string
  total_steps: number
  completed_steps: number
  current_label: string | null
  phase: string | null
  started_at: string
}

const messages = ref<RawMessage[]>([])
const processingAudio = ref<AudioJob[]>([])
const canBake = ref(false)
const loading = ref(true)
const activeBake = ref<ActiveBake | null>(null)
const isBaking = computed(() => activeBake.value !== null)
const bakeResult = ref<any>(null)
const openId = ref<string | null>(null)

async function loadBuffer(showSpinner = false) {
  if (showSpinner) loading.value = true
  try {
    const { data } = await getBuffer()
    messages.value = data.messages
    processingAudio.value = data.processing_audio
    canBake.value = data.can_bake
    activeBake.value = data.active_bake
  } catch {
    messages.value = []
  } finally {
    loading.value = false
  }
}

function onChanged() {
  openId.value = null
  loadBuffer()
}

async function doBake() {
  bakeResult.value = null
  try {
    const { data } = await bake()
    activeBake.value = data
  } catch (err: any) {
    if (err.response?.status === 409 || err.response?.status === 422) {
      alert(err.response.data.detail)
    }
  }
}

useEvents({
  'buffer:update': () => loadBuffer(),
  'bake:started': (data: ActiveBake) => {
    activeBake.value = data
  },
  'bake:progress': (data: any) => {
    if (activeBake.value) {
      activeBake.value = {
        ...activeBake.value,
        completed_steps: data.completed,
        total_steps: data.total,
        current_label: data.label,
        phase: data.phase,
      }
    } else {
      loadBuffer()
    }
  },
  'bake:complete': (data: any) => {
    activeBake.value = null
    bakeResult.value = data
    loadBuffer()
  },
  'bake:error': (data: any) => {
    activeBake.value = null
    alert(data.detail || t('buffer.error'))
    loadBuffer()
  },
})

onMounted(() => loadBuffer(true))
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 sm:mb-6 gap-3">
      <h1 class="text-lg sm:text-xl font-medium text-sand-800">{{ t('buffer.title') }}</h1>
      <button
        @click="doBake"
        :disabled="!canBake || messages.length === 0 || isBaking"
        class="px-3 sm:px-4 py-2 rounded-lg text-sm font-medium text-white bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:hover:bg-accent shrink-0"
      >
        {{ isBaking ? t('buffer.baking') : t('buffer.bake', { count: messages.length }) }}
      </button>
    </div>

    <!-- Bake progress -->
    <div v-if="activeBake" class="bg-accent/5 border border-accent/30 rounded-lg p-4 mb-4">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
        <p class="text-sm text-sand-800 font-medium">
          <template v-if="activeBake.phase === 'highlights'">{{ t('buffer.extractingHighlights') }}</template>
          <template v-else>
            {{ t('buffer.progress', { current: Math.min(activeBake.completed_steps + 1, activeBake.total_steps), total: activeBake.total_steps }) }}
            <span v-if="activeBake.current_label" class="text-sand-500">— {{ activeBake.current_label }}</span>
          </template>
        </p>
      </div>
      <div class="w-full h-2 bg-sand-100 rounded-full overflow-hidden">
        <div
          class="h-full bg-accent transition-all duration-300"
          :style="{ width: activeBake.total_steps > 0 ? `${(activeBake.completed_steps / activeBake.total_steps) * 100}%` : '0%' }"
        ></div>
      </div>
      <p class="text-xs text-sand-400 mt-2">{{ t('buffer.locked') }}</p>
    </div>

    <!-- Processing audio warning -->
    <div v-if="processingAudio.length > 0" class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
        <p class="text-sm text-amber-800">
          {{ t('buffer.processing', processingAudio.length) }}
        </p>
      </div>
    </div>

    <!-- Bake result -->
    <div v-if="bakeResult" class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
      <p class="text-sm text-green-800">
        {{ t('buffer.created', bakeResult.entries_created) }}
        <router-link
          v-if="bakeResult.entries?.[0]"
          :to="`/diary/${bakeResult.entries[0].date}`"
          class="text-accent hover:underline ml-1"
        >
          {{ t('buffer.view') }}
        </router-link>
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block w-6 h-6 border-2 border-sand-300 border-t-accent rounded-full animate-spin"></div>
    </div>

    <!-- Empty buffer -->
    <div v-else-if="messages.length === 0 && processingAudio.length === 0" class="text-center py-12">
      <p class="text-sand-500">{{ t('buffer.empty') }}</p>
      <p class="text-sand-400 text-sm mt-1">{{ t('buffer.emptyHint') }}</p>
    </div>

    <!-- Messages list -->
    <div v-else class="space-y-3" :class="{ 'opacity-60 pointer-events-none': isBaking }">
      <MessageCard
        v-for="msg in messages"
        :key="msg.id"
        :message="msg"
        :disabled="isBaking"
        :open="openId === msg.id"
        @open="openId = msg.id"
        @close="openId = null"
        @changed="onChanged"
      />
    </div>
  </div>
</template>
