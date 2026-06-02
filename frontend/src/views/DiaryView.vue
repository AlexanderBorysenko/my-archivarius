<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { getEntryByDate, getEntries, getEntryRaw, updateEntry, deleteEntry } from '../api'
import { useEvents } from '../composables/useEvents'
import { injectMacros } from '../utils/macros'

const route = useRoute()
const router = useRouter()

const entry = ref<any>(null)
const prevDate = ref<string | null>(null)
const nextDate = ref<string | null>(null)
const rawMessages = ref<any[]>([])
const showRaw = ref(false)
const loading = ref(true)
const availableDates = ref<string[]>([])
const noEntry = ref(false)
const editing = ref(false)
const editContent = ref('')
const saving = ref(false)

function scrollToHeading(id: string) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function startEdit() {
  editContent.value = entry.value.content
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function saveEdit() {
  if (!entry.value) return
  saving.value = true
  try {
    const { data } = await updateEntry(entry.value.id, { content: editContent.value })
    entry.value = data
    editing.value = false
  } catch {}
  finally {
    saving.value = false
  }
}

async function removeEntry() {
  if (!entry.value) return
  if (!confirm('Видалити цей запис? Цю дію неможливо скасувати.')) return
  try {
    await deleteEntry(entry.value.id)
    if (prevDate.value) {
      router.push(`/diary/${prevDate.value}`)
    } else if (nextDate.value) {
      router.push(`/diary/${nextDate.value}`)
    } else {
      entry.value = null
      noEntry.value = true
    }
  } catch {}
}

async function loadEntry(date: string) {
  loading.value = true
  noEntry.value = false
  showRaw.value = false
  editing.value = false
  rawMessages.value = []

  try {
    const { data } = await getEntryByDate(date)
    entry.value = data.entry
    prevDate.value = data.prev_date
    nextDate.value = data.next_date
  } catch (err: any) {
    if (err.response?.status === 404) {
      entry.value = null
      noEntry.value = true
    }
  } finally {
    loading.value = false
  }
}

async function loadLatest() {
  loading.value = true
  try {
    const { data } = await getEntries({ page: 1, per_page: 1 })
    availableDates.value = data.available_dates || []
    if (data.items.length > 0) {
      await loadEntry(data.items[0].date)
    } else {
      entry.value = null
      noEntry.value = true
      loading.value = false
    }
  } catch {
    loading.value = false
    noEntry.value = true
  }
}

async function toggleRaw() {
  if (!showRaw.value && entry.value) {
    try {
      const { data } = await getEntryRaw(entry.value.id)
      rawMessages.value = data
    } catch {
      rawMessages.value = []
    }
  }
  showRaw.value = !showRaw.value
}

function goTo(date: string | null) {
  if (date) router.push(`/diary/${date}`)
}

function formatDate(isoDate: string) {
  const d = new Date(isoDate + 'T00:00:00')
  return d.toLocaleDateString('uk-UA', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

interface TocItem {
  id: string
  text: string
  level: number
}

const tocItems = computed<TocItem[]>(() => {
  if (!entry.value?.content) return []
  const headingRegex = /^(#{2,3})\s+(.+)$/gm
  const items: TocItem[] = []
  let match
  while ((match = headingRegex.exec(entry.value.content)) !== null) {
    const text = match[2].trim()
    const id = text
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s-]/gu, '')
      .replace(/\s+/g, '-')
    items.push({ id, text, level: match[1].length })
  }
  return items
})

function injectMedia(html: string, manifest: Record<string, any>): string {
  return html.replace(
    /<img[^>]*src="attach:([A-Za-z0-9_]+)"[^>]*>/g,
    (_full, code) => {
      const info = manifest?.[code]
      const src = `/api/media/${code}`
      if (!info) return `<span class="diary-media-missing">📎</span>`
      if (info.status !== 'ready') {
        const poster = info.has_poster
          ? `<img src="${src}/poster" class="diary-media" loading="lazy">`
          : ''
        return `<div class="diary-media-note">${poster}<span>Медіа недоступне</span></div>`
      }
      if (info.kind === 'photo') {
        return `<img src="${src}" class="diary-media" loading="lazy">`
      }
      const posterAttr = info.has_poster ? ` poster="${src}/poster"` : ''
      const cls = info.kind === 'video_note' ? 'diary-media diary-media--circle' : 'diary-media'
      return `<video controls class="${cls}"${posterAttr} src="${src}"></video>`
    }
  )
}

const renderedContent = computed(() => {
  if (!entry.value?.content) return ''
  const renderer = new marked.Renderer()
  renderer.heading = function ({ tokens, depth }) {
    const text = this.parser.parseInline(tokens)
    const plain = text.replace(/<[^>]*>/g, '')
    const id = plain
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s-]/gu, '')
      .replace(/\s+/g, '-')
    return `<h${depth} id="${id}">${text}</h${depth}>`
  }
  const html = marked(entry.value.content, { renderer }) as string
  const withMedia = injectMedia(html, entry.value.media || {})
  return injectMacros(withMedia, entry.value.media || {})
})

useEvents({
  'bake:complete': (data: any) => {
    if (data.entries?.[0]?.date) {
      loadEntry(data.entries[0].date)
    } else {
      loadLatest()
    }
  },
})

onMounted(() => {
  const dateParam = route.params.date as string
  if (dateParam) {
    loadEntry(dateParam)
  } else {
    loadLatest()
  }
})

watch(() => route.params.date, (newDate) => {
  if (newDate) loadEntry(newDate as string)
})
</script>

<template>
  <div>
    <!-- Loading -->
    <div v-if="loading" class="text-center py-16">
      <div class="inline-block w-6 h-6 border-2 border-sand-300 border-t-accent rounded-full animate-spin"></div>
      <p class="text-sand-500 mt-3">Завантаження...</p>
    </div>

    <!-- No entries -->
    <div v-else-if="noEntry && !entry" class="text-center py-16">
      <p class="text-sand-500 text-lg mb-2">Записів поки немає</p>
      <p class="text-sand-400">
        Надсилай повідомлення в Telegram-бот і натискай /bake
      </p>
      <router-link to="/buffer" class="inline-block mt-4 text-accent hover:underline">
        Перейти до буфера →
      </router-link>
    </div>

    <!-- Entry -->
    <div v-else-if="entry">
      <!-- Navigation -->
      <div class="mb-4 sm:mb-6">
        <h1 class="text-base sm:text-xl font-medium text-sand-800 text-center mb-2 sm:mb-0 sm:hidden">
          {{ formatDate(entry.date) }}
        </h1>
        <div class="flex items-center justify-between">
          <button
            @click="goTo(prevDate)"
            :disabled="!prevDate"
            class="px-2 sm:px-3 py-1.5 rounded-md text-sm border border-sand-200 disabled:opacity-30"
            :class="prevDate ? 'text-sand-700 hover:bg-sand-100 cursor-pointer' : 'text-sand-400'"
          >
            <span class="sm:hidden">←</span>
            <span class="hidden sm:inline">← Попередній</span>
          </button>
          <h1 class="text-xl font-medium text-sand-800 hidden sm:block">
            {{ formatDate(entry.date) }}
          </h1>
          <button
            @click="goTo(nextDate)"
            :disabled="!nextDate"
            class="px-2 sm:px-3 py-1.5 rounded-md text-sm border border-sand-200 disabled:opacity-30"
            :class="nextDate ? 'text-sand-700 hover:bg-sand-100 cursor-pointer' : 'text-sand-400'"
          >
            <span class="sm:hidden">→</span>
            <span class="hidden sm:inline">Наступний →</span>
          </button>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex gap-2 mb-4 justify-end">
        <button
          v-if="!editing"
          @click="startEdit"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm border border-sand-200 text-sand-600 hover:bg-sand-100"
        >
          <span class="sm:hidden">✏️</span>
          <span class="hidden sm:inline">✏️ Редагувати</span>
        </button>
        <button
          v-if="!editing"
          @click="removeEntry"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm border border-sand-200 text-red-500 hover:bg-red-50 hover:border-red-200"
        >
          <span class="sm:hidden">🗑️</span>
          <span class="hidden sm:inline">🗑️ Видалити</span>
        </button>
      </div>

      <!-- Edit mode -->
      <div v-if="editing" class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6 mb-4">
        <textarea
          v-model="editContent"
          class="w-full min-h-[300px] border border-sand-200 rounded-lg p-4 text-sm text-sand-800 resize-y focus:outline-none focus:ring-2 focus:ring-accent/30"
          rows="12"
        ></textarea>
        <div class="flex gap-2 mt-3">
          <button
            @click="saveEdit"
            :disabled="saving"
            class="px-4 py-2 text-sm bg-accent text-white rounded-md hover:bg-accent-hover disabled:opacity-40"
          >
            {{ saving ? 'Збереження...' : 'Зберегти' }}
          </button>
          <button
            @click="cancelEdit"
            class="px-4 py-2 text-sm text-sand-600 border border-sand-200 rounded-md hover:bg-sand-100"
          >
            Скасувати
          </button>
        </div>
      </div>

      <!-- Entry content (read mode) -->
      <div v-else class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6 mb-4">
        <!-- Table of Contents -->
        <nav v-if="tocItems.length > 1" class="mb-6 pb-4 border-b border-sand-200">
          <p class="text-xs font-semibold uppercase tracking-wider text-sand-400 mb-2">Зміст</p>
          <ul class="space-y-1">
            <li v-for="item in tocItems" :key="item.id" :class="item.level === 3 ? 'ml-4' : ''">
              <a
                :href="'#' + item.id"
                class="text-sm text-sand-600 hover:text-accent transition-colors"
                @click.prevent="scrollToHeading(item.id)"
              >
                {{ item.text }}
              </a>
            </li>
          </ul>
        </nav>
        <div class="diary-content" v-html="renderedContent"></div>
      </div>

      <!-- Highlights -->
      <div v-if="entry.highlights?.length" class="mb-4">
        <h3 class="text-sm font-medium text-sand-600 mb-2">Хайлайти</h3>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="h in entry.highlights"
            :key="h.id"
            class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-sand-100 text-sand-700"
          >
            <span v-if="h.category === 'idea'">💡</span>
            <span v-else-if="h.category === 'story'">📖</span>
            <span v-else-if="h.category === 'mood'">🧠</span>
            <span v-else-if="h.category === 'insight'">⚡</span>
            {{ h.title }}
          </span>
        </div>
      </div>

      <!-- Raw messages toggle -->
      <button
        @click="toggleRaw"
        class="text-sm text-sand-500 hover:text-sand-700"
      >
        {{ showRaw ? 'Сховати оригінали' : `Показати оригінали (${entry.source_messages_count})` }}
      </button>

      <div v-if="showRaw && rawMessages.length" class="mt-3 space-y-2">
        <div
          v-for="msg in rawMessages"
          :key="msg.id"
          class="bg-sand-100 rounded-lg p-3 text-sm"
        >
          <div class="flex items-center gap-2 text-sand-500 mb-1">
            <span>{{ msg.source_type === 'voice' ? '🎙️' : '✏️' }}</span>
            <span>{{ new Date(msg.created_at).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' }) }}</span>
          </div>
          <p class="text-sand-800">{{ msg.content }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diary-content :deep(h2) {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-sand-800);
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--color-sand-200);
}

.diary-content :deep(h2:first-child) {
  margin-top: 0;
}

.diary-content :deep(h3) {
  font-size: 1.1rem;
  font-weight: 500;
  color: var(--color-sand-700);
  margin-top: 1rem;
  margin-bottom: 0.375rem;
}

.diary-content :deep(p) {
  margin-bottom: 0.75rem;
  line-height: 1.7;
  color: var(--color-sand-800);
}

.diary-content :deep(strong) {
  font-weight: 600;
}

.diary-content :deep(ul),
.diary-content :deep(ol) {
  margin-bottom: 0.75rem;
  padding-left: 1.5rem;
}

.diary-content :deep(li) {
  margin-bottom: 0.25rem;
  line-height: 1.6;
}

.diary-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-sand-200);
  margin: 1.25rem 0;
}

.diary-content :deep(.diary-media) {
  max-width: 100%;
  border-radius: 0.75rem;
  margin: 0.75rem 0;
  display: block;
}

.diary-content :deep(.diary-media--circle) {
  width: 240px;
  height: 240px;
  border-radius: 50%;
  object-fit: cover;
}

.diary-content :deep(.diary-media-note) {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-sand-500);
  font-size: 0.875rem;
  margin: 0.75rem 0;
}

.diary-content :deep(.diary-gallery) { margin: 1rem 0; }
.diary-content :deep(.diary-gallery__grid) { columns: 3 200px; column-gap: 8px; }
.diary-content :deep(.diary-gallery__item) {
  display: block;
  break-inside: avoid;
  margin-bottom: 8px;
}
.diary-content :deep(.diary-gallery__item img) {
  width: 100%;
  height: auto;
  border-radius: 0.5rem;
  display: block;
}
.diary-content :deep(.diary-gallery__caption),
.diary-content :deep(.diary-figure__caption) {
  text-align: center;
  font-size: 0.85rem;
  color: var(--color-sand-500);
  margin-top: 0.4rem;
}

.diary-content :deep(.diary-figure) { margin: 0.25rem 0 1rem; }
.diary-content :deep(.diary-figure img) {
  width: 100%;
  height: auto;
  border-radius: 0.5rem;
  display: block;
}
.diary-content :deep(.diary-figure--left) { float: left; margin-right: 1rem; }
.diary-content :deep(.diary-figure--right) { float: right; margin-left: 1rem; }
.diary-content :deep(.diary-figure--center) { margin-left: auto; margin-right: auto; }
.diary-content :deep(.diary-figure--full) { width: 100% !important; }

.diary-content :deep(h2),
.diary-content :deep(h3) { clear: both; }

@media (max-width: 640px) {
  .diary-content :deep(.diary-figure) { float: none !important; width: 100% !important; }
  .diary-content :deep(.diary-gallery__grid) { columns: 2 140px; }
}
</style>
