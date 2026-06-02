<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getBuffer, updateMessage, deleteMessage, bake } from '../api'
import { useEvents } from '../composables/useEvents'

interface MediaFileRef {
  shortcode: string
  kind: string
  status: string
  has_poster: boolean
}

interface RawMsg {
  id: string
  source_type: string
  content: string
  descriptive?: string | null
  media_files?: MediaFileRef[]
  classified_date: string
  created_at: string
}

interface AudioJob {
  id: string
  duration: number
  status: string
}

const messages = ref<RawMsg[]>([])
const processingAudio = ref<AudioJob[]>([])
const canBake = ref(false)
const loading = ref(true)
const baking = ref(false)
const bakeResult = ref<any>(null)
const editingId = ref<string | null>(null)
const editContent = ref('')

async function loadBuffer(showSpinner = false) {
  if (showSpinner) loading.value = true
  try {
    const { data } = await getBuffer()
    messages.value = data.messages
    processingAudio.value = data.processing_audio
    canBake.value = data.can_bake
  } catch {
    messages.value = []
  } finally {
    loading.value = false
  }
}

function startEdit(msg: RawMsg) {
  editingId.value = msg.id
  editContent.value = msg.content
}

async function saveEdit(id: string) {
  try {
    await updateMessage(id, { content: editContent.value })
    editingId.value = null
    await loadBuffer()
  } catch {}
}

function cancelEdit() {
  editingId.value = null
}

async function remove(id: string) {
  if (!confirm('Видалити повідомлення?')) return
  try {
    await deleteMessage(id)
    await loadBuffer()
  } catch {}
}

async function doBake() {
  baking.value = true
  bakeResult.value = null
  try {
    await bake()
  } catch (err: any) {
    baking.value = false
    if (err.response?.status === 409) {
      alert(err.response.data.detail)
    } else if (err.response?.status === 422) {
      alert(err.response.data.detail)
    }
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' })
}

useEvents({
  'buffer:update': () => loadBuffer(),
  'bake:complete': (data: any) => {
    bakeResult.value = data
    baking.value = false
    loadBuffer()
  },
  'bake:error': (data: any) => {
    baking.value = false
    alert(data.detail || 'Помилка запікання')
    loadBuffer()
  },
})

onMounted(() => loadBuffer(true))
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 sm:mb-6 gap-3">
      <h1 class="text-lg sm:text-xl font-medium text-sand-800">Буфер повідомлень</h1>
      <button
        @click="doBake"
        :disabled="!canBake || messages.length === 0 || baking"
        class="px-3 sm:px-4 py-2 rounded-lg text-sm font-medium text-white bg-accent hover:bg-accent-hover disabled:opacity-40 disabled:hover:bg-accent shrink-0"
      >
        {{ baking ? 'Запікаю...' : `🔥 Запікти (${messages.length})` }}
      </button>
    </div>

    <!-- Processing audio warning -->
    <div v-if="processingAudio.length > 0" class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
      <div class="flex items-center gap-2">
        <div class="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
        <p class="text-sm text-amber-800">
          {{ processingAudio.length }} голосових повідомлень в процесі транскрибації.
          Запікання заблоковано до завершення.
        </p>
      </div>
    </div>

    <!-- Bake result -->
    <div v-if="bakeResult" class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
      <p class="text-sm text-green-800">
        ✅ Створено {{ bakeResult.entries_created }} запис(ів)!
        <router-link
          v-if="bakeResult.entries?.[0]"
          :to="`/diary/${bakeResult.entries[0].date}`"
          class="text-accent hover:underline ml-1"
        >
          Переглянути →
        </router-link>
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block w-6 h-6 border-2 border-sand-300 border-t-accent rounded-full animate-spin"></div>
    </div>

    <!-- Empty buffer -->
    <div v-else-if="messages.length === 0 && processingAudio.length === 0" class="text-center py-12">
      <p class="text-sand-500">Буфер порожній</p>
      <p class="text-sand-400 text-sm mt-1">Надсилай повідомлення в Telegram-бот</p>
    </div>

    <!-- Messages list -->
    <div v-else class="space-y-3">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="bg-white rounded-xl border border-sand-200 p-3 sm:p-4"
      >
        <div class="flex items-start justify-between">
          <div class="flex items-center gap-2 text-sm text-sand-500 mb-2">
            <span>{{ msg.source_type === 'voice' ? '🎙️' : msg.source_type === 'media' ? '📎' : '✏️' }}</span>
            <span>{{ formatTime(msg.created_at) }}</span>
            <span class="px-2 py-0.5 rounded-full bg-sand-100 text-xs">
              {{ formatDate(msg.classified_date) }}
            </span>
          </div>
          <div class="flex gap-1">
            <button
              v-if="editingId !== msg.id"
              @click="startEdit(msg)"
              class="text-sand-400 hover:text-sand-600 text-sm px-2"
            >
              ✏️
            </button>
            <button
              @click="remove(msg.id)"
              class="text-sand-400 hover:text-red-500 text-sm px-2"
            >
              🗑️
            </button>
          </div>
        </div>

        <!-- Edit mode -->
        <div v-if="editingId === msg.id">
          <textarea
            v-model="editContent"
            class="w-full border border-sand-200 rounded-lg p-3 text-sm text-sand-800 resize-none focus:outline-none focus:ring-2 focus:ring-accent/30"
            rows="3"
          ></textarea>
          <div class="flex gap-2 mt-2">
            <button
              @click="saveEdit(msg.id)"
              class="px-3 py-1 text-sm bg-accent text-white rounded-md"
            >
              Зберегти
            </button>
            <button
              @click="cancelEdit"
              class="px-3 py-1 text-sm text-sand-600 border border-sand-200 rounded-md"
            >
              Скасувати
            </button>
          </div>
        </div>

        <!-- Display mode -->
        <template v-else>
          <div v-if="msg.source_type === 'media'">
            <div class="flex flex-wrap gap-2 mb-2">
              <div
                v-for="f in msg.media_files"
                :key="f.shortcode"
                class="w-20 h-20 rounded-lg overflow-hidden bg-sand-100 flex items-center justify-center"
              >
                <img
                  v-if="f.status === 'ready' && f.kind === 'photo'"
                  :src="`/api/media/${f.shortcode}`"
                  class="w-full h-full object-cover"
                />
                <img
                  v-else-if="f.has_poster"
                  :src="`/api/media/${f.shortcode}/poster`"
                  class="w-full h-full object-cover"
                />
                <span v-else class="text-2xl">{{ f.kind === 'photo' ? '🖼️' : '🎬' }}</span>
              </div>
            </div>
            <p class="text-sand-700 text-sm italic">
              {{ msg.descriptive || 'Без опису' }}
            </p>
          </div>
          <p v-else class="text-sand-800 text-sm">{{ msg.content }}</p>
        </template>
      </div>
    </div>
  </div>
</template>
