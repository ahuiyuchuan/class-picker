<script setup>
/** @author ahui — 齿轮悬浮菜单，延迟关闭保持鼠标移动通道；键盘与触屏同样可用。 */
import { ref, nextTick, onBeforeUnmount } from "vue";
import { Settings, UsersRound, SlidersHorizontal, Info } from "lucide-vue-next";
const props = defineProps({ disabled: Boolean });
const emit = defineEmits(["navigate", "open-change"]);
const root = ref(null),
  trigger = ref(null),
  open = ref(false);
let timer;
function show() {
  clearTimeout(timer);
  if (!props.disabled) {
    open.value = true;
    emit("open-change", true);
  }
}
function close(focus = false) {
  clearTimeout(timer);
  open.value = false;
  emit("open-change", false);
  if (focus) trigger.value?.focus();
}
function leave() {
  // 鼠标离开触发器和浮层后延迟收起，给用户移动到菜单项的时间。
  timer = setTimeout(() => close(), 180);
}
function outside(e) {
  if (!root.value?.contains(e.target)) close();
}
async function key(e) {
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    close(true);
  }
  if (["ArrowDown", "ArrowUp"].includes(e.key)) {
    e.preventDefault();
    show();
    await nextTick();
    const items = [...root.value.querySelectorAll("[role=menuitem]")],
      i = items.indexOf(document.activeElement);
    // 焦点尚在齿轮按钮时，向上应进入最后一项，向下进入第一项。
    const next = i < 0
      ? (e.key === "ArrowDown" ? 0 : items.length - 1)
      : (i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  }
}
document.addEventListener("pointerdown", outside, true);
onBeforeUnmount(() => {
  clearTimeout(timer);
  document.removeEventListener("pointerdown", outside, true);
});
</script>
<template>
  <div
    ref="root"
    class="settings-menu"
    @mouseenter="show"
    @mouseleave="leave"
    @keydown="key"
    @focusout="
      (e) => {
        if (!root.contains(e.relatedTarget)) close();
      }
    "
  >
    <button
      ref="trigger"
      class="icon-btn gear-button"
      aria-label="设置菜单"
      aria-haspopup="menu"
      :aria-expanded="open"
      :disabled="disabled"
      @click="show"
    >
      <Settings :size="23" />
    </button>
    <div v-if="open" class="settings-popover" role="menu" aria-label="管理入口">
      <button
        role="menuitem"
        @click="
          close();
          emit('navigate', 'roster');
        "
      >
        <UsersRound :size="22" />班级名单</button
      ><button
        role="menuitem"
        @click="
          close();
          emit('navigate', 'settings');
        "
      >
        <SlidersHorizontal :size="22" />应用设置
      </button><button
        role="menuitem"
        @click="
          close();
          emit('navigate', 'about');
        "
      >
        <Info :size="22" />关于
      </button>
    </div>
  </div>
</template>
