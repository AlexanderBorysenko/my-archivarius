<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import draggable from 'vuedraggable'
import type { RawMessage } from '../../types/message'
import { editItemSrc } from '../../utils/media'
import { useMediaEditor } from '../../composables/useMediaEditor'
import MediaThumb from './MediaThumb.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{ message: RawMessage }>()
const emit = defineEmits<{ changed: []; cancel: [] }>()

const { items, saving, fileInput, itemKey, start, reset, onPickFiles, onPaste, removeItem, save } =
  useMediaEditor()

onMounted(() => start(props.message))
onUnmounted(reset)

async function onSave() {
  if (items.value.length === 0 && !confirm(t('message.confirmDeleteWhole'))) return
  try {
    await save(props.message.id)
    emit('changed')
  } catch (err: any) {
    alert(err.response?.data?.detail || t('message.saveFailed'))
  }
}

function onCancel() {
  reset()
  emit('cancel')
}
</script>

<template>
  <div @paste="onPaste" tabindex="0">
    <draggable
      v-model="items"
      :item-key="itemKey"
      :disabled="saving"
      class="flex flex-wrap gap-2 mb-2"
    >
      <template #item="{ element, index }">
        <div class="relative w-20 h-20 rounded-lg overflow-hidden bg-sand-100 flex items-center justify-center cursor-move">
          <MediaThumb :src="editItemSrc(element)" :kind="element.kind" />
          <button
            type="button"
            @click.stop="removeItem(index)"
            class="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white text-xs leading-none flex items-center justify-center"
          >
            ✕
          </button>
        </div>
      </template>
    </draggable>

    <button
      type="button"
      @click="fileInput?.click()"
      class="w-20 h-20 rounded-lg border-2 border-dashed border-sand-300 text-sand-400 text-2xl flex items-center justify-center"
    >
      ＋
    </button>
    <input
      ref="fileInput"
      type="file"
      multiple
      accept="image/*,video/*"
      class="hidden"
      @change="onPickFiles"
    />

    <p class="text-xs text-sand-400 mt-1">
      {{ t('message.reorderHint') }}
    </p>
    <div class="flex gap-2 mt-2">
      <button
        @click="onSave"
        :disabled="saving"
        class="px-3 py-1 text-sm bg-accent text-white rounded-md disabled:opacity-50"
      >
        {{ saving ? t('common.saving') : t('common.save') }}
      </button>
      <button
        @click="onCancel"
        :disabled="saving"
        class="px-3 py-1 text-sm text-sand-600 border border-sand-200 rounded-md disabled:opacity-50"
      >
        {{ t('common.cancel') }}
      </button>
    </div>
  </div>
</template>
