<script setup>
/** @author ahui — 统一分段控件，选项值保持真实类型，避免原生 select 样式。 */
const props = defineProps({
  modelValue: [String, Number],
  options: Array,
  disabled: Boolean,
  label: String,
});
const emit = defineEmits(["update:modelValue"]);
</script>
<template>
  <div class="segmented" role="group" :aria-label="label">
    <button
      v-for="option in options"
      :key="String(option[0])"
      type="button"
      :aria-pressed="modelValue === option[0]"
      :disabled="disabled"
      @click="emit('update:modelValue', option[0])"
    >
      {{ option[1] }}
    </button>
  </div>
</template>
