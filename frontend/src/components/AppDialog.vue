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
  // 多表导入只校验已选工作表；未选表当前展示的输入不应触发浏览器原生拦截。
  customValidation: Boolean,
});
const emit = defineEmits(["close", "submit"]);
const element = ref(null);
let previous;
function key(event) {
  if (event.key !== "Tab") return;
  const items = [
    ...element.value.querySelectorAll(
      'button:enabled,input:enabled,select:enabled,textarea:enabled,[tabindex="0"]',
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
    <form :novalidate="customValidation" @submit.prevent="!busy && !disabled && emit('submit')">
      <header>
        <div class="modal-heading">
          <h2 id="modal-title">{{ title }}</h2>
          <slot name="subtitle" />
        </div>
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
        <!-- 可选摘要槽与操作保持同一固定栏；调用方自行按 busy 冻结槽内控件。 -->
        <slot name="footer-summary" />
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
