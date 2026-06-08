<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { marked } from 'marked'
import { useI18n } from 'vue-i18n'
import { setLocale, type Language } from '../i18n'
import {
  getSettings,
  updateSettings,
  previewStyle,
  getHighlightCategories,
  createCategory,
  updateCategory,
  deleteCategory,
} from '../api'

const { t, locale } = useI18n()
const language = ref<Language>(locale.value as Language)

async function saveLanguage() {
  await updateSettings({ language: language.value })
  setLocale(language.value)
}

const BUILTIN = ['idea', 'story', 'mood', 'insight']
function catLabel(cat: { name: string; is_system: boolean }) {
  return cat.is_system && BUILTIN.includes(cat.name) ? t(`categories.${cat.name}.label`) : cat.name
}
function catDesc(cat: { name: string; description: string; is_system: boolean }) {
  return cat.is_system && BUILTIN.includes(cat.name) ? t(`categories.${cat.name}.description`) : cat.description
}

// --- Diary Style ---
const stylePrompt = ref('')
const defaultStylePrompt = ref('')
const saving = ref(false)
const saveSuccess = ref(false)
const previewing = ref(false)
const previewText = ref('')
const previewError = ref('')

const renderedPreview = computed(() => {
  if (!previewText.value) return ''
  return marked(previewText.value) as string
})

async function loadSettings() {
  try {
    const { data } = await getSettings()
    stylePrompt.value = data.bake_style_prompt || ''
    defaultStylePrompt.value = data.default_style_prompt || ''
    language.value = (data.language as Language) ?? language.value
  } catch {}
}

async function saveStyle() {
  saving.value = true
  saveSuccess.value = false
  try {
    const value = stylePrompt.value.trim() || null
    await updateSettings({ bake_style_prompt: value })
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2000)
  } catch {}
  finally {
    saving.value = false
  }
}

function resetStyle() {
  stylePrompt.value = ''
  saveStyle()
}

async function testStyle() {
  previewing.value = true
  previewText.value = ''
  previewError.value = ''
  try {
    const value = stylePrompt.value.trim() || null
    const { data } = await previewStyle({ style_prompt: value })
    previewText.value = data.preview
  } catch {
    previewError.value = t('settings.style.previewError')
  } finally {
    previewing.value = false
  }
}

// --- Highlight Categories ---
interface Category {
  name: string
  description: string
  prompt: string
  icon: string
  is_system: boolean
  enabled: boolean
}

const categories = ref<Category[]>([])
const editingCategory = ref<string | null>(null)
const editForm = ref({ description: '', prompt: '', icon: '' })
const showNewForm = ref(false)
const newForm = ref({ name: '', description: '', prompt: '', icon: '' })
const savingCategory = ref(false)

async function loadCategories() {
  try {
    const { data } = await getHighlightCategories()
    categories.value = data
  } catch {}
}

function startEditCategory(cat: Category) {
  editingCategory.value = cat.name
  editForm.value = {
    description: cat.description,
    prompt: cat.prompt || '',
    icon: cat.icon,
  }
}

function cancelEdit() {
  editingCategory.value = null
}

async function saveEditCategory(cat: Category) {
  savingCategory.value = true
  try {
    const body: any = { prompt: editForm.value.prompt }
    if (!cat.is_system) {
      body.description = editForm.value.description
      body.icon = editForm.value.icon
    }
    await updateCategory(cat.name, body)
    await loadCategories()
    editingCategory.value = null
  } catch {}
  finally {
    savingCategory.value = false
  }
}

async function toggleCategory(cat: Category) {
  try {
    await updateCategory(cat.name, { enabled: !cat.enabled })
    await loadCategories()
  } catch {}
}

function openNewForm() {
  newForm.value = { name: '', description: '', prompt: '', icon: '' }
  showNewForm.value = true
}

async function saveNewCategory() {
  if (!newForm.value.name || !newForm.value.description) return
  savingCategory.value = true
  try {
    await createCategory({
      name: newForm.value.name,
      description: newForm.value.description,
      prompt: newForm.value.prompt,
      icon: newForm.value.icon || undefined,
    })
    await loadCategories()
    showNewForm.value = false
  } catch {}
  finally {
    savingCategory.value = false
  }
}

async function removeCategory(name: string) {
  if (!confirm(t('settings.categories.deleteConfirm'))) return
  try {
    await deleteCategory(name)
    await loadCategories()
  } catch {}
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadCategories()])
})
</script>

<template>
  <div>
    <h1 class="text-xl font-medium text-sand-800 mb-6">{{ t('settings.title') }}</h1>

    <!-- Interface Language Section -->
    <section class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6 mb-6">
      <label class="text-base font-medium text-sand-800 mb-2 block">{{ t('settings.language.label') }}</label>
      <select
        v-model="language"
        @change="saveLanguage"
        class="px-3 py-2 text-sm border border-sand-200 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/30"
      >
        <option value="en">English</option>
        <option value="uk">Українська</option>
        <option value="ru">Русский</option>
      </select>
    </section>

    <!-- Diary Style Section -->
    <section class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6 mb-6">
      <h2 class="text-base font-medium text-sand-800 mb-2">{{ t('settings.style.header') }}</h2>
      <p class="text-sm text-sand-500 mb-4">
        {{ t('settings.style.desc') }}
      </p>

      <textarea
        v-model="stylePrompt"
        :placeholder="defaultStylePrompt"
        rows="5"
        class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md resize-y focus:outline-none focus:ring-2 focus:ring-accent/30 mb-3"
      ></textarea>

      <div class="flex flex-wrap gap-2 mb-4">
        <button
          @click="saveStyle"
          :disabled="saving"
          class="px-4 py-2 text-sm bg-accent text-white rounded-md hover:bg-accent-hover disabled:opacity-40 transition-colors"
        >
          {{ saving ? t('settings.style.saving') : t('settings.style.save') }}
        </button>
        <button
          @click="resetStyle"
          :disabled="saving"
          class="px-4 py-2 text-sm text-sand-600 border border-sand-200 rounded-md hover:bg-sand-100 disabled:opacity-40 transition-colors"
        >
          {{ t('settings.style.reset') }}
        </button>
        <button
          @click="testStyle"
          :disabled="previewing"
          class="px-4 py-2 text-sm text-sand-600 border border-sand-200 rounded-md hover:bg-sand-100 disabled:opacity-40 transition-colors"
        >
          {{ previewing ? t('settings.style.generating') : t('settings.style.test') }}
        </button>
        <span
          v-if="saveSuccess"
          class="self-center text-sm text-green-600"
        >
          {{ t('settings.style.saved') }}
        </span>
      </div>

      <!-- Preview result -->
      <div v-if="previewing" class="text-center py-8">
        <div class="inline-block w-6 h-6 border-2 border-sand-300 border-t-accent rounded-full animate-spin"></div>
        <p class="text-sm text-sand-400 mt-2">{{ t('settings.style.previewLoading') }}</p>
      </div>

      <div v-else-if="previewError" class="bg-red-50 border border-red-200 rounded-lg p-4">
        <p class="text-sm text-red-600">{{ previewError }}</p>
      </div>

      <div v-else-if="previewText" class="bg-sand-50 border border-sand-200 rounded-lg p-4">
        <h3 class="text-sm font-medium text-sand-600 mb-2">{{ t('settings.style.previewHeader') }}</h3>
        <div class="diary-content text-sm text-sand-800" v-html="renderedPreview"></div>
      </div>
    </section>

    <!-- Highlight Categories Section -->
    <section class="bg-white rounded-xl border border-sand-200 p-4 sm:p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-medium text-sand-800">{{ t('settings.categories.header') }}</h2>
        <button
          @click="openNewForm"
          class="px-3 py-1.5 rounded-md text-sm bg-accent text-white hover:bg-accent-hover transition-colors"
        >
          {{ t('settings.categories.new') }}
        </button>
      </div>
      <p class="text-sm text-sand-500 mb-4">
        {{ t('settings.categories.desc') }}
      </p>

      <!-- New category form -->
      <div v-if="showNewForm" class="border border-accent/30 rounded-lg p-4 mb-4 bg-sand-50">
        <div class="grid gap-3">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              v-model="newForm.name"
              :placeholder="t('settings.categories.namePlaceholder')"
              class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
            <input
              v-model="newForm.icon"
              :placeholder="t('settings.categories.iconPlaceholder')"
              class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
          </div>
          <input
            v-model="newForm.description"
            :placeholder="t('settings.categories.descPlaceholder')"
            class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
          <textarea
            v-model="newForm.prompt"
            :placeholder="t('settings.categories.promptPlaceholder')"
            rows="2"
            class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md resize-y focus:outline-none focus:ring-2 focus:ring-accent/30"
          ></textarea>
          <div class="flex gap-2">
            <button
              @click="saveNewCategory"
              :disabled="savingCategory || !newForm.name || !newForm.description"
              class="px-4 py-2 text-sm bg-accent text-white rounded-md hover:bg-accent-hover disabled:opacity-40 transition-colors"
            >
              {{ t('settings.categories.create') }}
            </button>
            <button
              @click="showNewForm = false"
              class="px-4 py-2 text-sm text-sand-600 border border-sand-200 rounded-md hover:bg-sand-100 transition-colors"
            >
              {{ t('settings.categories.cancel') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Category list -->
      <div class="space-y-3">
        <div
          v-for="cat in categories"
          :key="cat.name"
          class="border border-sand-200 rounded-lg p-3 sm:p-4 transition-colors"
          :class="cat.enabled ? 'bg-white' : 'bg-sand-50 opacity-60'"
        >
          <!-- View mode -->
          <div v-if="editingCategory !== cat.name">
            <div class="flex items-start justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-lg">{{ cat.icon }}</span>
                <div>
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="font-medium text-sm text-sand-800">{{ catLabel(cat) }}</span>
                    <span v-if="cat.is_system" class="text-xs px-1.5 py-0.5 rounded bg-sand-100 text-sand-400">{{ t('settings.categories.system') }}</span>
                  </div>
                  <p class="text-xs text-sand-500 mt-0.5">{{ catDesc(cat) }}</p>
                </div>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button
                  @click="toggleCategory(cat)"
                  class="w-8 h-8 rounded-md text-sm flex items-center justify-center transition-colors"
                  :class="cat.enabled ? 'text-green-600 hover:bg-green-50' : 'text-sand-300 hover:bg-sand-100'"
                  :title="cat.enabled ? t('settings.categories.enabled') : t('settings.categories.disabled')"
                >
                  {{ cat.enabled ? '✓' : '○' }}
                </button>
                <button
                  @click="startEditCategory(cat)"
                  class="w-8 h-8 rounded-md text-sm text-sand-400 hover:text-sand-600 hover:bg-sand-100 flex items-center justify-center transition-colors"
                >
                  ✏️
                </button>
                <button
                  v-if="!cat.is_system"
                  @click="removeCategory(cat.name)"
                  class="w-8 h-8 rounded-md text-sm text-sand-300 hover:text-red-400 hover:bg-red-50 flex items-center justify-center transition-colors"
                >
                  🗑️
                </button>
              </div>
            </div>
            <p v-if="cat.prompt" class="text-xs text-sand-400 mt-2 pl-8 italic">
              {{ t('settings.categories.promptLabel') }} {{ cat.prompt }}
            </p>
          </div>

          <!-- Edit mode -->
          <div v-else class="space-y-3">
            <div class="flex items-center gap-2">
              <span class="text-lg">{{ cat.icon }}</span>
              <span class="font-medium text-sm text-sand-800">{{ catLabel(cat) }}</span>
              <span v-if="cat.is_system" class="text-xs px-1.5 py-0.5 rounded bg-sand-100 text-sand-400">{{ t('settings.categories.system') }}</span>
            </div>
            <div v-if="!cat.is_system" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                v-model="editForm.description"
                :placeholder="t('settings.categories.descPlaceholderShort')"
                class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
              <input
                v-model="editForm.icon"
                :placeholder="t('settings.categories.iconPlaceholderShort')"
                class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <textarea
              v-model="editForm.prompt"
              :placeholder="t('settings.categories.promptPlaceholderShort')"
              rows="2"
              class="w-full px-3 py-2 text-sm border border-sand-200 rounded-md resize-y focus:outline-none focus:ring-2 focus:ring-accent/30"
            ></textarea>
            <div class="flex gap-2">
              <button
                @click="saveEditCategory(cat)"
                :disabled="savingCategory"
                class="px-4 py-1.5 text-sm bg-accent text-white rounded-md hover:bg-accent-hover disabled:opacity-40 transition-colors"
              >
                {{ t('settings.style.save') }}
              </button>
              <button
                @click="cancelEdit"
                class="px-4 py-1.5 text-sm text-sand-600 border border-sand-200 rounded-md hover:bg-sand-100 transition-colors"
              >
                {{ t('settings.categories.cancel') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
