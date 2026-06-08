<script setup lang="ts">
import type { RawMessage } from '../../types/message'
import { existingThumbSrc } from '../../utils/media'
import MediaThumb from './MediaThumb.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
defineProps<{ message: RawMessage }>()
</script>

<template>
  <div v-if="message.source_type === 'media'">
    <div class="flex flex-wrap gap-2 mb-2">
      <div
        v-for="f in message.media_files"
        :key="f.shortcode"
        class="w-20 h-20 rounded-lg overflow-hidden bg-sand-100 flex items-center justify-center"
      >
        <MediaThumb :src="existingThumbSrc(f)" :kind="f.kind" />
      </div>
    </div>
    <p class="text-sand-700 text-sm italic">{{ message.descriptive || t('message.noDescription') }}</p>
  </div>
  <p v-else class="text-sand-800 text-sm">{{ message.content }}</p>
</template>
