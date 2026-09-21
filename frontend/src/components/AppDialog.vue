<script setup>
/** @author ahui — 应用内模态容器，默认取消，忙碌时拒绝重复提交与关闭。 */
import { ref, onMounted, onBeforeUnmount } from "vue";
import { X } from "lucide-vue-next";
const props = defineProps({
  title: String,
  busy: Boolean,
  error: String,
  wide: Boolean,
  submitLabel: { type: String, default: "保存" },
  hideSubmit: Boolean,
  disabled: Boolean,
});
const emit = defineEmits(["close", "submit"]);
const element = ref(null);
let previous;
function key(event) {
  if (event.key !== "Tab") return;
  const items = [
    ...element.value.querySelectorAll(
      'button:enabled,input:enabled,textarea:enabled,[tabindex="0"]',
    ),
  ];
  const first = items[0],
    last = items.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
}
onMounted(() => {
  previous = document.activeElement;
  element.value.showModal();
  element.value.querySelector(".modal-cancel")?.focus();
});
onBeforeUnmount(() => {
  element.value?.close();
  previous?.focus();
});
</script>
<template>
  <dialog
    ref="element"
    class="app-dialog"
    :class="{ wide }"
    aria-labelledby="modal-title"
    @cancel.prevent="!busy && emit('close')"
    @keydown="key"
  >
    <form @submit.prevent="!busy && !disabled && emit('submit')">
      <header>
        <h2 id="modal-title">{{ title }}</h2>
        <button
          type="button"
          class="icon-btn"
          aria-label="关闭弹窗"
          :disabled="busy"
          @click="emit('close')"
        >
          <X :size="20" />
        </button>
      </header>
      <!-- 保存期间冻结表单值，避免提交后继续编辑造成“已保存”与画面内容不一致。 -->
      <div class="modal-content"><fieldset :disabled="busy"><slot /></fieldset></div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <footer>
        <button
          type="button"
          class="secondary-btn modal-cancel"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ hideSubmit ? "关闭" : "取消" }}</button
        ><button
          v-if="!hideSubmit"
          class="primary-btn"
          type="submit"
          :disabled="busy || disabled"
        >
          {{ busy ? "处理中…" : submitLabel }}
        </button>
      </footer>
    </form>
  </dialog>
</template>
