<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getHighlights,
  getHighlightCategories,
  deleteHighlight,
} from '../api'
import { useEvents } from '../composables/useEvents'

const router = useRouter()

interface HighlightItem {
  id: string
  title: string
  category: string
  content: string
  source_date?: string
  created_at: string
}

interface Category {
  name: string
  icon: string
  enabled: boolean
}

const highlights = ref<HighlightItem[]>([])
const categories = ref<Category[]>([])
const selectedCategory = ref<string | null>(null)
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const perPage = 20

const totalPages = computed(() => Math.ceil(total.value / perPage))

const categoryIcons = computed(() => {
  const map: Record<string, string> = {}
  for (const cat of categories.value) {
    map[cat.name] = cat.icon
  }
  return map
})

async function loadHighlights() {
  loading.value = true
  try {
    const params: any = { page: page.value, per_page: perPage }
    if (selectedCategory.value) params.category = selectedCategory.value
    const { data } = await getHighlights(params)
    highlights.value = data.items
    total.value = data.total
  } catch {
    highlights.value = []
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    const { data } = await getHighlightCategories()
    categories.value = data
  } catch {}
}

function selectCategory(name: string | null) {
  selectedCategory.value = selectedCategory.value === name ? null : name
  page.value = 1
  loadHighlights()
}

function getIcon(category: string) {
  return categoryIcons.value[category] || '🏷️'
}

function formatDate(iso: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString('uk-UA', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function goToEntry(date: string) {
  router.push({ name: 'diary-date', params: { date } })
}

async function removeHighlight(id: string) {
  try {
    await deleteHighlight(id)
    highlights.value = highlights.value.filter(h => h.id !== id)
    total.value--
  } catch {}
}

function goPage(p: number) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  loadHighlights()
}

useEvents({
  'bake:complete': () => {
    loadCategories()
    loadHighlights()
  },
})

onMounted(async () => {
  await Promise.all([loadCategories(), loadHighlights()])
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-medium text-sand-800">Хайлайти</h1>
      <router-link
        to="/settings"
        class="text-sm text-sand-500 hover:text-accent transition-colors"
      >
        Налаштувати категорії →
      </router-link>
    </div>

    <!-- Category filters -->
    <div class="flex flex-wrap gap-2 mb-6">
      <button
        @click="selectCategory(null)"
        class="px-3 py-1.5 rounded-full text-sm border transition-colors"
        :class="!selectedCategory
          ? 'bg-accent text-sand-50 border-accent'
          : 'text-sand-600 border-sand-200 hover:border-sand-300'"
      >
        Всі
      </button>
      <button
        v-for="cat in categories.filter(c => c.enabled)"
        :key="cat.name"
        @click="selectCategory(cat.name)"
        class="px-3 py-1.5 rounded-full text-sm border transition-colors"
        :class="selectedCategory === cat.name
          ? 'bg-accent text-sand-50 border-accent'
          : 'text-sand-600 border-sand-200 hover:border-sand-300'"
      >
        {{ cat.icon }} {{ cat.name }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block w-6 h-6 border-2 border-sand-300 border-t-accent rounded-full animate-spin"></div>
    </div>

    <!-- Empty -->
    <div v-else-if="highlights.length === 0" class="text-center py-12">
      <p class="text-sand-500">Хайлайтів поки немає</p>
      <p class="text-sand-400 text-sm mt-1">Вони з'являться автоматично після запікання записів</p>
    </div>

    <!-- Highlights list -->
    <div v-else class="space-y-3">
      <div
        v-for="h in highlights"
        :key="h.id"
        class="bg-white rounded-xl border border-sand-200 p-3 sm:p-5"
      >
        <div class="flex items-start gap-3">
          <span class="text-xl mt-0.5">{{ getIcon(h.category) }}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-start sm:items-center gap-1.5 sm:gap-2 mb-1 flex-wrap">
              <h3 class="font-medium text-sand-800 text-sm sm:text-base">{{ h.title }}</h3>
              <span class="text-xs px-2 py-0.5 rounded-full bg-sand-100 text-sand-500">
                {{ h.category }}
              </span>
            </div>
            <p class="text-sm text-sand-600">{{ h.content }}</p>
            <div class="flex items-center justify-between mt-2 sm:mt-3 gap-2">
              <button
                v-if="h.source_date"
                @click="goToEntry(h.source_date)"
                class="text-xs text-sand-400 hover:text-accent transition-colors"
              >
                з запису від {{ formatDate(h.source_date) }}
              </button>
              <span v-else></span>
              <button
                @click="removeHighlight(h.id)"
                class="text-xs text-sand-300 hover:text-red-400 transition-colors"
              >
                Видалити
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-6">
      <button
        @click="goPage(page - 1)"
        :disabled="page <= 1"
        class="px-3 py-1.5 rounded-md text-sm border border-sand-200 disabled:opacity-30 transition-colors"
        :class="page > 1 ? 'text-sand-700 hover:bg-sand-100' : 'text-sand-400'"
      >
        ←
      </button>
      <span class="text-sm text-sand-600 px-2">
        {{ page }} / {{ totalPages }}
      </span>
      <button
        @click="goPage(page + 1)"
        :disabled="page >= totalPages"
        class="px-3 py-1.5 rounded-md text-sm border border-sand-200 disabled:opacity-30 transition-colors"
        :class="page < totalPages ? 'text-sand-700 hover:bg-sand-100' : 'text-sand-400'"
      >
        →
      </button>
    </div>
  </div>
</template>
