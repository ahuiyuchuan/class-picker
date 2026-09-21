<script setup>
/**
 * @author ahui
 * 抽取记录只读页：班级选择独立于课堂，按需分页读取本地保留的历史快照。
 * 切班时清空旧结果；请求序号防止慢响应覆盖新班级，卸载后不更新页面状态。
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ArrowLeft, ChevronLeft, ChevronRight, History } from "lucide-vue-next";
import ClassSelect from "../components/ClassSelect.vue";
import { call, state } from "../data";

const props = defineProps({ initialId: Number });
defineEmits(["back"]);
const selectedId = ref(props.initialId || state.classes[0]?.id);
const current = computed(() => state.classes.find((item) => item.id === selectedId.value));
const records = ref([]), total = ref(0), page = ref(1), busy = ref(false), error = ref("");
const pages = computed(() => Math.max(1, Math.ceil(total.value / 20)));
let requestSequence = 0;

/**
 * 请求指定页，成功时整体替换列表；失败保留页码并提供重试，不展示旧班级记录。
 * @param {number} target 从 1 开始的页码，后端将超出末页的请求归入末页。
 */
async function loadPage(target = 1) {
  const sequence = ++requestSequence;
  error.value = "";
  if (!current.value) {
    records.value = [];
    total.value = 0;
    busy.value = false;
    return;
  }
  busy.value = true;
  try {
    const result = await call("history_page", { class_id: current.value.id, page: target });
    if (sequence !== requestSequence) return;
    records.value = result.records;
    total.value = result.total;
    page.value = result.page;
  } catch (exception) {
    if (sequence === requestSequence) error.value = exception.message;
  } finally {
    if (sequence === requestSequence) busy.value = false;
  }
}
watch(selectedId, () => {
  records.value = [];
  total.value = 0;
  page.value = 1;
  loadPage();
}, { immediate: true });
onBeforeUnmount(() => { requestSequence += 1; });

/** 将存储的 UTC 时间转换为本机日期时间，避免不同日期仅显示时分而混淆。 */
function formatTime(value) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <div class="management-page history-page">
    <header class="page-heading">
      <button class="secondary-btn" @click="$emit('back')"><ArrowLeft :size="20" />返回课堂</button>
      <h1><History />抽取记录</h1>
      <p>回顾每一次课堂抽取</p>
    </header>
    <section class="roster-classbar panel">
      <ClassSelect v-if="current" :model-value="current.name"
        :options="state.classes.map(item => item.name)"
        @update:model-value="selectedId = state.classes.find(item => item.name === $event)?.id" />
      <span v-else class="muted">尚未创建班级</span>
      <span class="muted" aria-live="polite">共 {{ total }} 次记录</span>
    </section>
    <section class="history-panel panel" :aria-busy="busy">
      <div class="history-intro">
        <strong>抽取明细</strong>
        <span class="muted">最新记录在前 · 每页 20 次</span>
      </div>
      <p v-if="!state.settings.save_history" class="history-tip">历史记录已关闭，新的抽取不会保存；已有记录仍可查看。</p>
      <div v-if="error" class="history-empty" role="alert">
        <p>{{ error }}</p><button class="secondary-btn" :disabled="busy" @click="loadPage(page)">重新加载</button>
      </div>
      <div v-else-if="busy" class="history-empty" role="status">正在加载记录…</div>
      <div v-else-if="!records.length" class="history-empty">
        <History :size="40" /><h2>暂无抽取记录</h2>
        <p>{{ current ? '开启保存历史后，完成抽取即可在这里查看。' : '创建班级并完成抽取后，记录会显示在这里。' }}</p>
      </div>
      <div v-else class="history-list">
        <article v-for="record in records" :key="record.id" class="history-record">
          <div class="history-record-heading">
            <time :datetime="record.time">{{ formatTime(record.time) }}</time>
            <span>{{ record.results.length }} 人</span>
          </div>
          <ul class="history-students">
            <li v-for="(student, index) in record.results" :key="index">
              <strong>{{ student.name }}</strong><span v-if="student.no">学号 {{ student.no }}</span>
            </li>
          </ul>
        </article>
      </div>
      <footer class="history-footer">
        <span class="muted">显示抽取时的姓名和学号</span>
        <div>
          <button class="icon-btn" aria-label="上一页记录" :disabled="busy || page <= 1" @click="loadPage(page - 1)"><ChevronLeft :size="20" /></button>
          <span>{{ page }} / {{ pages }}</span>
          <button class="icon-btn" aria-label="下一页记录" :disabled="busy || page >= pages" @click="loadPage(page + 1)"><ChevronRight :size="20" /></button>
        </div>
      </footer>
    </section>
  </div>
</template>
