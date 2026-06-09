<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import draggable from 'vuedraggable'
import { useStoryPoints, type StoryPoint } from '../../composables/useStoryPoints'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ entryId: string }>()
const emit = defineEmits<{ (e: 'changed'): void }>()
const { t } = useI18n()
const sp = useStoryPoints()

const points = ref<StoryPoint[]>([])
const newTitle = ref('')
const creating = ref(false)
const busyIds = ref<Set<string>>(new Set())

async function load() {
  try {
    points.value = await sp.loadForEntry(props.entryId)
  } catch {
    // keep the current list on a load failure
  }
}

async function add() {
  const title = newTitle.value.trim()
  if (!title || creating.value) return // guard double-submit
  creating.value = true
  try {
    await sp.addPoint(props.entryId, title)
    newTitle.value = ''
    await load()
    emit('changed')
  } catch {
    await load()
  } finally {
    creating.value = false
  }
}

async function rename(p: StoryPoint) {
  const title = p.title.trim()
  if (!title) {
    await load() // revert empty edit
    return
  }
  try {
    await sp.renamePoint(p.id, title)
    await load() // keep local in sync with server-normalized values
    emit('changed')
  } catch {
    await load()
  }
}

async function remove(p: StoryPoint) {
  if (busyIds.value.has(p.id)) return // guard double-delete
  busyIds.value = new Set(busyIds.value).add(p.id)
  try {
    await sp.removePoint(p.id)
    await load()
    emit('changed')
  } catch {
    await load()
  } finally {
    const next = new Set(busyIds.value)
    next.delete(p.id)
    busyIds.value = next
  }
}

async function onReorder() {
  try {
    await sp.reorder(props.entryId, points.value.map(p => p.id))
    emit('changed')
  } catch {
    await load() // restore server order on failure
  }
}

onMounted(load)
watch(() => props.entryId, load)
</script>

<template>
  <div class="bg-white rounded-xl border border-sand-200 p-4 mb-4">
    <h3 class="text-sm font-medium text-sand-600 mb-3">{{ t('storyPoints.timelineTitle') }}</h3>

    <draggable
      v-model="points"
      item-key="id"
      handle=".sp-drag"
      class="space-y-2"
      @end="onReorder"
    >
      <template #item="{ element }">
        <div class="flex items-center gap-2">
          <span class="sp-drag cursor-grab text-sand-300 select-none">⠿</span>
          <input
            v-model="element.title"
            @blur="rename(element)"
            @keyup.enter="($event.target as HTMLInputElement).blur()"
            class="flex-1 border border-sand-200 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
          <button
            class="text-sand-300 hover:text-red-400 text-sm disabled:cursor-not-allowed w-4 text-center"
            :disabled="busyIds.has(element.id)"
            @click="remove(element)"
            aria-label="delete"
          >
            <span
              v-if="busyIds.has(element.id)"
              class="inline-block w-3 h-3 border-2 border-sand-300 border-t-red-400 rounded-full animate-spin align-middle"
            ></span>
            <span v-else>✕</span>
          </button>
        </div>
      </template>
    </draggable>

    <div class="flex items-center gap-2 mt-3">
      <input
        v-model="newTitle"
        @keyup.enter="add"
        :disabled="creating"
        :placeholder="t('storyPoints.placeholder')"
        class="flex-1 border border-sand-200 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:opacity-60"
      />
      <button
        class="px-3 py-1 text-sm bg-accent text-white rounded-md hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center min-w-14"
        :disabled="creating || !newTitle.trim()"
        @click="add"
      >
        <span
          v-if="creating"
          class="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin"
        ></span>
        <span v-else>{{ t('storyPoints.addPoint') }}</span>
      </button>
    </div>

    <!-- Future: ✨ Generate button slot — calls useStoryPoints.generateWithAI(entryId) -->
  </div>
</template>
