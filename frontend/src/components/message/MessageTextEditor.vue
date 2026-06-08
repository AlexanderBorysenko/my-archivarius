<script setup lang="ts">
import { ref } from 'vue'
import type { RawMessage } from '../../types/message'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{ message: RawMessage }>()
const emit = defineEmits<{ save: [content: string]; cancel: [] }>()

const content = ref(props.message.content)
</script>

<template>
  <div>
    <textarea
      v-model="content"
      class="w-full border border-sand-200 rounded-lg p-3 text-sm text-sand-800 resize-none focus:outline-none focus:ring-2 focus:ring-accent/30"
      rows="3"
    ></textarea>
    <div class="flex gap-2 mt-2">
      <button
        @click="emit('save', content)"
        class="px-3 py-1 text-sm bg-accent text-white rounded-md"
      >
        {{ t('common.save') }}
      </button>
      <button
        @click="emit('cancel')"
        class="px-3 py-1 text-sm text-sand-600 border border-sand-200 rounded-md"
      >
        {{ t('common.cancel') }}
      </button>
    </div>
  </div>
</template>
