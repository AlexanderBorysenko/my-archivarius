<script setup lang="ts">
import { updateMessage, deleteMessage } from '../../api'
import type { RawMessage } from '../../types/message'
import MessageHeader from './MessageHeader.vue'
import MessageDisplay from './MessageDisplay.vue'
import MessageTextEditor from './MessageTextEditor.vue'
import MessageMediaEditor from './MessageMediaEditor.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{ message: RawMessage; disabled: boolean; open: boolean }>()
const emit = defineEmits<{ open: []; close: []; changed: [] }>()

async function onRemove() {
  if (!confirm(t('message.confirmDelete'))) return
  try {
    await deleteMessage(props.message.id)
    emit('changed')
  } catch {}
}

async function onSaveText(content: string) {
  try {
    await updateMessage(props.message.id, { content })
    emit('changed')
  } catch {}
}
</script>

<template>
  <div class="bg-white rounded-xl border border-sand-200 p-3 sm:p-4">
    <MessageHeader
      :message="message"
      :disabled="disabled"
      :open="open"
      @edit="emit('open')"
      @remove="onRemove"
    />

    <MessageMediaEditor
      v-if="open && message.source_type === 'media'"
      :message="message"
      @changed="emit('changed')"
      @cancel="emit('close')"
    />
    <MessageTextEditor
      v-else-if="open"
      :message="message"
      @save="onSaveText"
      @cancel="emit('close')"
    />
    <MessageDisplay v-else :message="message" />
  </div>
</template>
