<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps<{ block: any; media: Record<string, any> }>()

const info = computed(() => props.media?.[props.block?.media] || null)
const src = computed(() => `/api/media/${props.block?.media}`)
const align = computed(() =>
  ['left', 'right', 'center', 'full'].includes(props.block?.align) ? props.block.align : 'left'
)
const width = computed(() =>
  [25, 33, 50, 100].includes(props.block?.width) ? props.block.width : 33
)
const widthStyle = computed(() =>
  align.value === 'full' ? undefined : { width: `${width.value}%` }
)
</script>

<template>
  <figure
    v-if="info"
    class="diary-figure"
    :class="`diary-figure--${align}`"
    :style="widthStyle"
  >
    <template v-if="info.status === 'ready'">
      <img v-if="info.kind === 'photo'" :src="src" loading="lazy" />
      <video
        v-else
        controls
        :class="{ 'diary-figure__circle': info.kind === 'video_note' }"
        :poster="info.has_poster ? `${src}/poster` : undefined"
        :src="src"
      ></video>
    </template>
    <div v-else class="diary-figure__unavailable">
      <img v-if="info.has_poster" :src="`${src}/poster`" loading="lazy" />
      <span>{{ t('block.mediaUnavailable') }}</span>
    </div>
    <figcaption v-if="block.caption" class="diary-figure__caption">{{ block.caption }}</figcaption>
  </figure>
</template>

<style scoped>
.diary-figure { margin: 0.25rem 0 1rem; }
.diary-figure img,
.diary-figure video { width: 100%; height: auto; border-radius: 0.5rem; display: block; }
.diary-figure--left { float: left; margin-right: 1rem; }
.diary-figure--right { float: right; margin-left: 1rem; }
.diary-figure--center { margin-left: auto; margin-right: auto; }
.diary-figure--full { width: 100% !important; }
.diary-figure__circle { width: 240px; height: 240px; border-radius: 50%; object-fit: cover; }
.diary-figure__caption {
  text-align: center;
  font-size: 0.85rem;
  color: var(--color-sand-500);
  margin-top: 0.4rem;
}
.diary-figure__unavailable {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-sand-500);
  font-size: 0.875rem;
}
@media (max-width: 640px) {
  .diary-figure { float: none !important; width: 100% !important; }
}
</style>
