<script setup>
/** @author ahui
 * 搜索式班级选择。焦点留在搜索框，通过 active-descendant 导航列表；
 * Escape/选择恢复触发器焦点，外部点击保留用户新焦点，Tab 正常离开。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { GraduationCap, ChevronDown, Search, Check } from "lucide-vue-next";
const props = defineProps({
  modelValue: String,
  options: Array,
  disabled: Boolean,
  // 可选的关联操作区域；名单页工具栏及其弹窗属于同一次班级操作，不作为外部点击。
  interactionScope: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue", "open-change"]);
const root = ref(null);
const trigger = ref(null);
const search = ref(null);
const open = ref(false);
const query = ref("");
const active = ref(0);
// 候选项仅在键盘导航时显示焦点框；只有 modelValue 对应的行显示选中底色和勾选。
const keyboardActive = ref(false);
const filtered = computed(() =>
  props.options.filter((item) => item.includes(query.value.trim())),
);
watch([filtered, () => props.modelValue], () => {
  // 排序、重命名或筛选后重新定位当前班级，不能沿用旧下标高亮另一个班级。
  active.value = Math.max(0, filtered.value.indexOf(props.modelValue));
  keyboardActive.value = false;
});
watch(
  () => props.disabled,
  (value) => {
    // 名单写入期间保持列表可见，但 choose 仍拒绝切换，避免异步写入串班。
    if (value && !props.interactionScope) close(false);
  },
);
/** 判断焦点或指针是否仍在选择器及其关联操作区内。空目标视为离开。 */
function isInside(target) {
  return !!(
    target &&
    (root.value?.contains(target) ||
      (props.interactionScope && target.closest?.(props.interactionScope)))
  );
}
function outside(event) {
  if (!isInside(event.target)) close(false);
}
function close(restore = true) {
  open.value = false;
  emit("open-change", false);
  document.removeEventListener("pointerdown", outside, true);
  document.removeEventListener("focusin", outside, true);
  if (restore) trigger.value?.focus();
}
async function expand() {
  if (props.disabled) return;
  if (open.value) {
    close();
    return;
  }
  await ensureOpen();
}
/**
 * 幂等展开列表；重复调用保留筛选与焦点，不切换关闭。
 * @param {boolean} focusSearch 是否聚焦搜索框；外部按钮传 false，避免抢走弹窗或按钮焦点。
 * @returns {Promise<void>} Vue 完成列表渲染后兑现；禁用时不展开。
 */
async function ensureOpen(focusSearch = true) {
  if (open.value || props.disabled) return;
  query.value = "";
  active.value = Math.max(0, props.options.indexOf(props.modelValue));
  keyboardActive.value = false;
  open.value = true;
  emit("open-change", true);
  document.addEventListener("pointerdown", outside, true);
  // 外部按钮展开时焦点不在组件内，也需识别随后通过 Tab 离开关联区域。
  document.addEventListener("focusin", outside, true);
  await nextTick();
  if (focusSearch) search.value?.focus();
}
function choose(item) {
  if (!item || props.disabled) return;
  emit("update:modelValue", item);
  close();
}
async function key(event) {
  if (event.isComposing) return; // 中文输入法确认候选时不提交班级。
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    close();
  } else if (event.key === "Enter") {
    event.preventDefault();
    choose(filtered.value[active.value]);
  } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    keyboardActive.value = true;
    const last = filtered.value.length - 1;
    active.value =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? Math.max(0, last)
          : Math.max(
              0,
              Math.min(
                last,
                active.value + (event.key === "ArrowDown" ? 1 : -1),
              ),
            );
    await nextTick();
    root.value
      ?.querySelector(".option-active")
      ?.scrollIntoView({ block: "nearest" });
  }
}
async function focusOut(event) {
  // 原生 dialog.showModal() 可能暂时给出空 relatedTarget，等焦点落定后再判断。
  const target = event.relatedTarget;
  await nextTick();
  if (open.value && !isInside(target || document.activeElement)) close(false);
}
defineExpose({ expand, ensureOpen, close });
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", outside, true);
  document.removeEventListener("focusin", outside, true);
});
</script>
<template>
  <div ref="root" class="class-select" @focusout="focusOut">
    <button
      ref="trigger"
      class="class-trigger"
      aria-label="当前班级"
      aria-haspopup="listbox"
      :aria-expanded="open"
      aria-controls="class-options"
      :disabled="disabled"
      @click="expand"
      @keydown.down.prevent="expand"
      @keydown.up.prevent="expand"
    >
      <GraduationCap :size="24" aria-hidden="true" /><span>{{
        modelValue
      }}</span
      ><ChevronDown :size="18" :class="{ rotated: open }" aria-hidden="true" />
    </button>
    <div v-if="open" class="class-popover" @keydown="key">
      <label class="class-search"
        ><Search :size="18" aria-hidden="true" /><input
          ref="search"
          v-model="query"
          role="combobox"
          aria-label="搜索班级"
          aria-autocomplete="list"
          aria-expanded="true"
          aria-controls="class-options"
          :aria-activedescendant="
            filtered.length ? `class-option-${active}` : undefined
          "
          placeholder="搜索班级"
          autocomplete="off"
      /></label>
      <div
        id="class-options"
        role="listbox"
        aria-label="班级列表"
        class="class-options"
      >
        <div
          v-for="(item, index) in filtered"
          :id="`class-option-${index}`"
          :key="item"
          role="option"
          :aria-selected="item === modelValue"
          class="class-option"
          :class="{ 'option-active': keyboardActive && index === active }"
          @pointermove="active = index; keyboardActive = false"
          @mousedown.prevent
          @click="choose(item)"
        >
          <span>{{ item }}</span
          ><Check v-if="item === modelValue" :size="18" aria-hidden="true" />
        </div>
      </div>
      <div v-if="!filtered.length" class="select-empty" role="status">
        未找到匹配的班级
      </div>
      <div class="select-hint">↑ ↓ 选择 · Enter 确认 · Esc 关闭</div>
    </div>
  </div>
</template>
