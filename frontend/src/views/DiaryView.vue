<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getEntryByDate, getEntries, getEntryRaw, updateEntry, deleteEntry, rebakeEntry } from '../api'
import { useEvents } from '../composables/useEvents'
import BlockRenderer from '../components/blocks/BlockRenderer.vue'
import { useI18n } from 'vue-i18n'
import { bcp47, type Language } from '../i18n'
const { t, locale } = useI18n()

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
const rebaking = ref(false)
const bakeLabel = ref('')

function scrollToHeading(id: string) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function startEdit() {
  editContent.value = JSON.stringify(entry.value.blocks || [], null, 2)
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function saveEdit() {
  if (!entry.value) return
  let blocks: any[]
  try {
    blocks = JSON.parse(editContent.value)
  } catch {
    alert(t('diary.invalidJson'))
    return
  }
  if (!Array.isArray(blocks)) {
    alert(t('diary.jsonMustBeArray'))
    return
  }
  saving.value = true
  try {
    const { data } = await updateEntry(entry.value.id, { blocks })
    entry.value = data
    editing.value = false
  } catch {} finally {
    saving.value = false
  }
}

async function removeEntry() {
  if (!entry.value) return
  if (!confirm(t('diary.confirmDelete'))) return
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

async function rebake() {
  if (!entry.value) return
  if (!confirm(t('diary.confirmRebake'))) return
  try {
    await rebakeEntry(entry.value.id)
    rebaking.value = true
    bakeLabel.value = t('diary.rebakeStarting')
  } catch (err: any) {
    if (err.response?.status === 409) {
      alert(t('diary.rebakeInProgress'))
    } else {
      alert(t('diary.rebakeFailed'))
    }
  }
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
  return d.toLocaleDateString(bcp47(locale.value as Language), {
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
  const blocks = entry.value?.blocks || []
  const items: TocItem[] = []
  const headingRegex = /^(#{2,3})\s+(.+)$/gm
  for (const b of blocks) {
    if (b.type !== 'markdown' || typeof b.text !== 'string') continue
    let match
    while ((match = headingRegex.exec(b.text)) !== null) {
      const text = match[2].trim()
      const id = text
        .toLowerCase()
        .replace(/[^\p{L}\p{N}\s-]/gu, '')
        .replace(/\s+/g, '-')
      items.push({ id, text, level: match[1].length })
    }
  }
  return items
})


useEvents({
  'bake:started': () => { rebaking.value = true },
  'bake:progress': (data: any) => {
    rebaking.value = true
    bakeLabel.value = data.phase === 'highlights' ? t('buffer.extractingHighlights') : (data.label || t('diary.rebaking'))
  },
  'bake:complete': (data: any) => {
    rebaking.value = false
    bakeLabel.value = ''
    if (data.entries?.[0]?.date) {
      loadEntry(data.entries[0].date)
    } else {
      loadLatest()
    }
  },
  'bake:error': (data: any) => {
    rebaking.value = false
    bakeLabel.value = ''
    alert(t('diary.bakeError', { detail: data?.detail || '' }))
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
      <p class="text-sand-500 mt-3">{{ t('diary.loading') }}</p>
    </div>

    <!-- No entries -->
    <div v-else-if="noEntry && !entry" class="text-center py-16">
      <p class="text-sand-500 text-lg mb-2">{{ t('diary.noEntries') }}</p>
      <p class="text-sand-400">
        {{ t('diary.noEntriesHint') }}
      </p>
      <router-link to="/buffer" class="inline-block mt-4 text-accent hover:underline">
        {{ t('diary.goToBuffer') }}
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
            <span class="hidden sm:inline">{{ t('diary.prev') }}</span>
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
            <span class="hidden sm:inline">{{ t('diary.next') }}</span>
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
          <span class="hidden sm:inline">{{ t('diary.edit') }}</span>
        </button>
        <button
          v-if="!editing"
          @click="removeEntry"
          class="px-2.5 sm:px-3 py-1.5 rounded-md text-sm border border-sand-200 text-red-500 hover:bg-red-50 hover:border-red-200"
        >
          <span class="sm:hidden">🗑️</span>
          <span class="hidden sm:inline">{{ t('diary.delete') }}</span>
        </button>
      </div>

      <!-- Edit mode -->
      <div v-if="editing" class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6 mb-4">
        <p class="text-xs text-sand-400 mb-2">{{ t('diary.editHelper') }}</p>
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
            {{ saving ? t('diary.saving') : t('diary.save') }}
          </button>
          <button
            @click="cancelEdit"
            class="px-4 py-2 text-sm text-sand-600 border border-sand-200 rounded-md hover:bg-sand-100"
          >
            {{ t('diary.cancel') }}
          </button>
        </div>
      </div>

      <!-- Entry content (read mode) -->
      <div v-else class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6 mb-4">
        <!-- Table of Contents -->
        <nav v-if="tocItems.length > 1" class="mb-6 pb-4 border-b border-sand-200">
          <p class="text-xs font-semibold uppercase tracking-wider text-sand-400 mb-2">{{ t('diary.toc') }}</p>
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
        <BlockRenderer :blocks="entry.blocks || []" :media="entry.media || {}" />
      </div>

      <!-- Highlights -->
      <div v-if="entry.highlights?.length" class="mb-4">
        <h3 class="text-sm font-medium text-sand-600 mb-2">{{ t('diary.highlights') }}</h3>
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
        {{ showRaw ? t('diary.hideRaw') : t('diary.showRaw', { count: entry.source_messages_count }) }}
      </button>

      <div v-if="showRaw" class="mt-3 space-y-2">
        <div
          v-for="msg in rawMessages"
          :key="msg.id"
          class="bg-sand-100 rounded-lg p-3 text-sm"
        >
          <div class="flex items-center gap-2 text-sand-500 mb-1">
            <span>{{ msg.source_type === 'voice' ? '🎙️' : '✏️' }}</span>
            <span>{{ new Date(msg.created_at).toLocaleTimeString(bcp47(locale as Language), { hour: '2-digit', minute: '2-digit' }) }}</span>
          </div>
          <p class="text-sand-800">{{ msg.content }}</p>
        </div>

        <div class="pt-2">
          <button
            @click="rebake"
            :disabled="rebaking"
            class="px-3 py-2 text-sm rounded-md border border-sand-200 text-sand-700 hover:bg-sand-100 disabled:opacity-40"
          >
            {{ rebaking ? (bakeLabel || t('diary.rebaking')) : t('diary.rebake') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

