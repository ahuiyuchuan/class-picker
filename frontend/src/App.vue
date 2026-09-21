<script setup>
/** @author ahui
 * 各页面共享窗口外壳。课堂数据以 SQLite 快照为准；管理页的班级选择不改课堂上下文。
 * 抽样先在 Python 事务提交，再播放纯展示动画。关闭重开可恢复最后一次结果。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  UserRound,
  UsersRound,
  Maximize,
  Minimize,
  CheckCircle2,
  History,
  ChevronRight,
  ShieldCheck,
  RotateCcw,
  Keyboard,
  Minus,
  Square,
  Copy,
  X,
} from "lucide-vue-next";
import ClassSelect from "./components/ClassSelect.vue";
import SettingsMenu from "./components/SettingsMenu.vue";
import AppDialog from "./components/AppDialog.vue";
import RosterPage from "./pages/RosterPage.vue";
import SettingsPage from "./pages/SettingsPage.vue";
import AboutPage from "./pages/AboutPage.vue";
import HistoryPage from "./pages/HistoryPage.vue";
import { state, apply, call, change } from "./data";
const page = ref("classroom"),
  settingsPage = ref(null),
  rosterPage = ref(null),
  currentId = ref(null);
const nativeState = ref({ maximized: false, fullscreen: false }),
  commandBusy = ref(false),
  drawing = ref(false),
  busy = ref(false);
const notice = ref(""),
  loadError = ref(""),
  selectOpen = ref(false),
  menuOpen = ref(false),
  modal = ref(""),
  modalError = ref(""),
  restoreExcluded = ref(true),
  exclusionIds = ref([]),
  exclusionSearch = ref("");
// 动画槽位只属于当前请求，不复用上次结果的数量、学号或记录 ID。
const previewResults = ref([]);
const current = computed(
  () => state.classes.find((c) => c.id === currentId.value) || state.classes[0],
);
const classes = computed(() => state.classes.map((c) => c.name));
const students = computed(() => current.value?.students || []);
// 重名判定随名单变化一次构建，避免多人结果每次渲染都逐个扫描完整名单。
const nameCounts = computed(() => {
  const counts = new Map();
  for (const student of students.value)
    counts.set(student.name, (counts.get(student.name) || 0) + 1);
  return counts;
});
const config = computed(() => ({
  ...state.defaults,
  ...state.settings,
  ...current.value?.rules,
}));
const full = computed(() => nativeState.value.fullscreen);
const available = computed(() =>
  students.value.filter((s) => s.enabled && !s.excluded),
);
const remaining = computed(
  () =>
    available.value.filter((s) => config.value.mode === "random" || !s.drawn)
      .length,
);
const drawnCount = computed(
  () => available.value.filter((s) => s.drawn).length,
);
const excludedCount = computed(
  () => students.value.filter((s) => s.excluded).length,
);
const results = computed(
  () => drawing.value ? previewResults.value : current.value?.latest ?? [],
);
// 长内容优先完整可读；滚动期间按候选集固定布局，避免逐帧字号忽大忽小。
const longResult = computed(() => results.value.length === 1 && (
  drawing.value
    ? available.value.some((student) => student.name.length > 16)
    : results.value[0].name.length > 16 ||
      (needsNumber(results.value[0]) && String(results.value[0].no).length > 32)
));
const lastRecord = computed(() => current.value?.history[0]);
const filteredExclusions = computed(() =>
  students.value.filter((s) =>
    `${s.name} ${s.no || ""}`.includes(exclusionSearch.value),
  ),
);
let ticker,
  noticeTimer,
  requestId = null,
  loading = false,
  initialized = false;
function showNotice(message) {
  notice.value = message;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => (notice.value = ""), 6000);
}
async function load() {
  // 挂载与 pywebviewready 可能紧邻触发，失败重试也不能同时发起多次初始化。
  if (initialized || loading) return;
  loading = true;
  try {
    await change("load");
    currentId.value = state.last_class;
    initialized = true;
    loadError.value = "";
    await syncWindow();
    if (state.settings.start_fullscreen && !full.value)
      await windowCommand("fullscreen");
  } catch (e) {
    loadError.value = e.message;
  } finally {
    loading = false;
  }
}
async function switchClass(name) {
  if (drawing.value || busy.value) return;
  // 切班写入完成前禁止抽取和再次切班，防止迟到快照覆盖当前课堂结果。
  busy.value = true;
  try {
    const id = state.classes.find((c) => c.name === name).id;
    await change("last_class", { class_id: id });
    currentId.value = id;
    requestId = null;
  } catch (e) {
    showNotice(e.message);
  } finally {
    busy.value = false;
  }
}
function navigate(target) {
  if (!drawing.value && !busy.value) {
    page.value = target;
    menuOpen.value = false;
  }
}
function back() {
  page.value = "classroom";
  if (!state.classes.some((c) => c.id === currentId.value))
    currentId.value = state.classes[0]?.id;
}
function requestClose() {
  if (page.value === "settings")
    settingsPage.value?.leave(() => windowCommand("close"));
  // 新增草稿尚未入库时沿用管理页确认流程，避免窗口关闭静默丢失输入。
  else if (page.value === "roster")
    rosterPage.value?.leave(() => windowCommand("close"));
  else windowCommand("close");
}
function needsNumber(result) {
  // 留空学号不显示占位值，也不以内部记录 ID 冒充学号。
  return (
    !!result.no &&
    (config.value.show_number ||
      (nameCounts.value.get(result.name) || 0) > 1)
  );
}
/**
 * 不足人数不静默截断；请求开始即按本次配置建立动画槽位。
 * 动画只采样本轮可抽名单，不影响后端真实抽样；保留请求 ID 直到成功。
 * 失败时撤销动画，显示仍未被覆盖的上次结果；成功后统一发布完整快照。
 */
async function draw() {
  if (
    drawing.value ||
    busy.value ||
    modal.value ||
    menuOpen.value ||
    selectOpen.value ||
    page.value !== "classroom"
  )
    return;
  if (!current.value || !students.value.length) {
    navigate("roster");
    return;
  }
  if (remaining.value < config.value.count) {
    showNotice(
      `当前可抽 ${remaining.value} 人，不足 ${config.value.count} 人，请重置本轮或调整规则。`,
    );
    return;
  }
  // 固定本次配置和候选，避免异步期间用旧结果长度决定新一轮的卡片布局。
  const drawConfig = { ...config.value };
  const candidates = available.value.filter(
    (student) => drawConfig.mode === "random" || !student.drawn,
  );
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  previewResults.value = Array.from({ length: drawConfig.count }, (_, index) => ({
    id: `pending-${index}`,
    name: "抽取中…",
    no: null,
  }));
  /** 每帧使用局部洗牌分配不同学生，槽位键固定，避免全部卡片刷同一姓名。
   * 这里只控制视觉效果；同名学生允许同名显示，最终结果始终来自 Python。
   */
  function refreshPreview() {
    const pool = [...candidates];
    previewResults.value = previewResults.value.map((slot, index) => {
      const pick = index + Math.floor(Math.random() * (pool.length - index));
      [pool[index], pool[pick]] = [pool[pick], pool[index]];
      return { ...slot, name: pool[index].name };
    });
  }
  drawing.value = true;
  if (drawConfig.effect === "rolling" && !reduce) {
    refreshPreview();
    ticker = setInterval(refreshPreview, 90);
  }
  try {
    requestId ||= crypto.randomUUID();
    const response = await call("draw", {
      class_id: current.value.id,
      request: requestId,
    });
    // 后端已事务提交，但整份前端快照延迟到动画结束再发布，
    // 避免最近记录、统计和学号先于主结果揭晓；此时关闭仍可从数据库恢复。
    requestId = null;
    if (drawConfig.effect !== "direct" && !reduce) {
      await new Promise((resolve) =>
        setTimeout(resolve, drawConfig.duration * 1000),
      );
    }
    apply(response);
  } catch (e) {
    showNotice(e.message);
  } finally {
    clearInterval(ticker);
    previewResults.value = [];
    drawing.value = false;
  }
}
function openModal(type) {
  if (drawing.value || busy.value || !current.value) return;
  modal.value = type;
  modalError.value = "";
  restoreExcluded.value = true;
  exclusionIds.value = students.value
    .filter((s) => s.excluded)
    .map((s) => s.id);
  exclusionSearch.value = "";
}
async function submitModal() {
  if (busy.value) return;
  busy.value = true;
  modalError.value = "";
  try {
    if (modal.value === "reset") {
      await change("reset", {
        class_id: current.value.id,
        restore_excluded: restoreExcluded.value,
      });
      requestId = null;
    } else
      await change("exclusions", {
        class_id: current.value.id,
        ids: exclusionIds.value,
      });
    modal.value = "";
  } catch (e) {
    modalError.value = e.message;
  } finally {
    busy.value = false;
  }
}
// 每次命令或状态查询递增，丢弃晚到的旧响应，防止焦点/resize 改回旧按钮状态。
let windowStateRevision = 0;
/** 窗口状态来自 WinForms，错误保留当前布局；命令期间禁止重复操作。 */
async function windowCommand(command) {
  if (commandBusy.value) return;
  windowStateRevision += 1;
  commandBusy.value = true;
  try {
    if (window.pywebview?.api) {
      const s = await window.pywebview.api[command]();
      if (s) nativeState.value = s;
    } else if (command === "fullscreen")
      nativeState.value.fullscreen = !full.value;
  } catch (e) {
    showNotice("窗口操作失败，请重试");
  } finally {
    commandBusy.value = false;
  }
}
/** 同步系统触发的窗口变化；只接受最新查询且查询期间未发生窗口命令的响应。 */
async function syncWindow() {
  if (window.pywebview?.api && !commandBusy.value) {
    const revision = ++windowStateRevision;
    try {
      const state = await window.pywebview.api.state();
      if (revision === windowStateRevision && !commandBusy.value)
        nativeState.value = state;
    } catch {
      /* 关闭期间无需显示错误。 */
    }
  }
}
function onKey(event) {
  if (
    event.repeat ||
    event.defaultPrevented ||
    document.querySelector("dialog[open]") ||
    selectOpen.value ||
    menuOpen.value
  )
    return;
  if (event.key === "F11") {
    event.preventDefault();
    windowCommand("fullscreen");
    return;
  }
  if (event.key === "Escape" && full.value) {
    event.preventDefault();
    windowCommand("fullscreen");
    return;
  }
  // 全屏快捷键属于窗口；只有空格抽取限制在课堂页，子页面也能安全退出全屏。
  if (page.value !== "classroom") return;
  if (event.target.closest?.('button,input,textarea,[contenteditable="true"]'))
    return;
  if (event.code === "Space") {
    event.preventDefault();
    draw();
  }
}
onMounted(() => {
  window.addEventListener("keydown", onKey);
  window.addEventListener("pywebviewready", load);
  window.addEventListener("resize", syncWindow);
  window.addEventListener("focus", syncWindow);
  if (window.pywebview?.api) load();
});
onUnmounted(() => {
  clearInterval(ticker);
  clearTimeout(noticeTimer);
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("pywebviewready", load);
  window.removeEventListener("resize", syncWindow);
  window.removeEventListener("focus", syncWindow);
});
</script>
<template>
  <main
    class="app-shell"
    :class="{ 'is-fullscreen': full, 'is-management': page !== 'classroom' }"
  >
    <header v-show="!full" class="topbar">
      <!-- 真实拖拽区和系统按钮是同级节点，按钮不会触发 pywebview 拖拽。 -->
      <div
        class="brand window-drag-region"
        @dblclick="windowCommand('maximize')"
      >
        <img src="/app-icon.png" alt="" class="brand-mark" draggable="false" />
        <span>班级随机抽人</span>
      </div>
      <div class="window-actions" @mousedown.stop @dblclick.stop>
        <button
          title="最小化"
          aria-label="最小化"
          :disabled="commandBusy"
          @click="windowCommand('minimize')"
        >
          <Minus :size="16" />
        </button>
        <button
          :title="nativeState.maximized ? '还原' : '最大化'"
          :aria-label="nativeState.maximized ? '还原' : '最大化'"
          :disabled="commandBusy"
          @click="windowCommand('maximize')"
        >
          <Copy v-if="nativeState.maximized" :size="14" /><Square
            v-else
            :size="14"
          />
        </button>
        <button
          class="close-button"
          title="关闭"
          aria-label="关闭"
          :disabled="commandBusy"
          @click="requestClose()"
        >
          <X :size="18" />
        </button>
      </div>
    </header>

    <template v-if="page === 'classroom'">
      <section class="contextbar">
        <ClassSelect
          v-if="current"
          :model-value="current.name"
          :options="classes"
          :disabled="drawing || busy"
          @update:model-value="switchClass"
          @open-change="selectOpen = $event"
        /><span v-else class="empty-class">尚未创建班级</span>
        <div class="total">
          <UsersRound :size="22" /><span>共 {{ students.length }} 人</span>
        </div>
        <div class="classroom-actions">
          <SettingsMenu
            :disabled="drawing || busy"
            @navigate="navigate"
            @open-change="menuOpen = $event"
          /><button
            class="full-btn"
            :disabled="commandBusy"
            @click="windowCommand('fullscreen')"
          >
            <Minimize v-if="full" :size="20" /><Maximize v-else :size="20" />{{
              full ? "退出全屏" : "全屏"
            }}
          </button>
        </div>
      </section>
      <section class="hero">
        <div
          class="result-card"
          :class="[
            'size-' + (config.font_size || 'auto'),
            {
              'is-revealing': drawing && config.effect === 'reveal',
              multiple: results.length > 1,
              'long-result': longResult,
            },
          ]"
          aria-live="polite"
          :aria-busy="drawing"
        >
          <div class="result-label">
            <UserRound :size="18" />{{
              drawing
                ? "正在抽取"
                : results.length
                  ? "本次抽取结果"
                  : current
                    ? "准备开始抽取"
                    : "欢迎使用班级随机抽人"
            }}
          </div>
          <template v-if="results.length <= 1"
            ><div class="spark left" aria-hidden="true"><i /><i /><i /></div>
            <div class="name">
              {{
                results[0]?.name ||
                (current ? (students.length ? "准备好了吗" : "添加你的学生名单") : "创建你的第一个班级")
              }}
            </div>
            <div class="number">
              {{
                drawing ? "" : results[0]
                  ? needsNumber(results[0])
                    ? `学号 ${results[0].no}`
                    : ""
                  : current
                    ? (students.length ? "点击下方按钮开始" : "添加或导入学生后即可开始抽取")
                    : "通过右上角设置菜单维护班级和学生"
              }}
            </div>
            <div class="spark right" aria-hidden="true"><i /><i /><i /></div
          ></template>
          <div v-else class="multi-results">
            <div v-for="result in results" :key="result.id">
              <b>{{ result.name }}</b
              ><span v-if="!drawing && needsNumber(result)">学号 {{ result.no }}</span>
            </div>
          </div>
        </div>
        <button
          class="draw-btn"
          :disabled="
            drawing || busy || !state.ready
          "
          @click="draw"
        >
          <UserRound :size="26" />{{
            drawing
              ? "抽取中…"
              : !current
                ? "创建班级"
                : !students.length
                  ? "添加学生"
                  : `抽取 ${config.count || 1} 人`
          }}
        </button>
        <div class="shortcut">
          <Keyboard :size="18" />{{
            current && students.length ? "按 Space 快速抽取" : "支持逐行添加、批量粘贴或导入名单"
          }}
        </div>
      </section>
      <section class="stats" aria-label="本轮统计">
        <div>
          <UsersRound class="blue" /><span>全班</span
          ><strong>{{ students.length }}<small>人</small></strong>
        </div>
        <div>
          <CheckCircle2 class="green" /><span>可参与</span
          ><strong class="green-text"
            >{{ available.length }}<small>人</small></strong
          >
        </div>
        <div>
          <UserRound class="purple" /><span>{{
            config.mode === "random" ? "抽取模式" : "本轮已抽"
          }}</span
          ><strong
            class="purple-text"
            :class="{ 'mode-label': config.mode === 'random' }"
            >{{ config.mode === "random" ? "完全随机" : drawnCount
            }}<small v-if="config.mode !== 'random'">人</small></strong
          >
        </div>
        <div>
          <History class="slate" /><span>{{
            config.mode === "random" ? "当前可抽" : "本轮剩余"
          }}</span
          ><strong>{{ remaining }}<small>人</small></strong>
        </div>
      </section>
      <section class="bottom-row">
        <div class="tools">
          <button
            :disabled="!current || drawing || busy"
            @click="openModal('exclude')"
          >
            <ShieldCheck :size="22" />临时排除<em
              >已排除 {{ excludedCount }} 人</em
            ></button
          ><button
            :disabled="!current || drawing || busy"
            @click="openModal('reset')"
          >
            <RotateCcw :size="22" />重置本轮
          </button>
        </div>
        <button type="button" class="recent" :disabled="drawing || busy" aria-label="查看抽取记录" @click="navigate('history')">
          <div class="recent-head">
            <span><History :size="18" />最近记录</span
            ><span class="recent-link">查看全部<ChevronRight :size="16" /></span>
          </div>
          <div v-if="lastRecord" class="recent-item">
            <UserRound :size="20" class="blue" /><b>{{
              lastRecord.results.map((r) => r.name).join("、")
            }}</b
            ><span>{{ lastRecord.results.length }} 人</span
            ><time>{{
              new Date(lastRecord.time).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })
            }}</time>
          </div>
          <div v-else class="recent-empty">暂无抽取记录</div>
        </button>
      </section>
    </template>
    <RosterPage
      v-else-if="page === 'roster'"
      ref="rosterPage"
      :initial-id="current?.id"
      @back="back"
      @notice="showNotice"
    />
    <SettingsPage v-else-if="page === 'settings'" ref="settingsPage" @back="back" @notice="showNotice" />
    <HistoryPage v-else-if="page === 'history'" :initial-id="current?.id" @back="back" />
    <AboutPage v-else @back="back" />
    <div v-if="notice || loadError" class="notice" role="alert">
      {{ loadError || notice
      }}<button v-if="loadError" @click="load">重试</button
      ><button v-else aria-label="关闭提示" @click="notice = ''">
        <X :size="18" />
      </button>
    </div>
    <AppDialog
      v-if="modal"
      :title="modal === 'reset' ? '重置本轮抽取？' : '临时排除学生'"
      :busy="busy"
      :error="modalError"
      :submit-label="modal === 'reset' ? '确认重置' : '保存排除名单'"
      @close="modal = ''"
      @submit="submitModal"
      ><template v-if="modal === 'reset'"
        ><p>将清空「{{ current.name }}」的本轮已抽进度。名单和历史记录保留。</p>
        <label class="check-field"
          ><input
            v-model="restoreExcluded"
            type="checkbox"
          />同时恢复临时排除的学生</label
        ></template
      ><template v-else
        ><label class="field"
          >搜索姓名或学号<input
            v-model="exclusionSearch"
            placeholder="搜索学生"
        /></label>
        <div class="exclusion-list">
          <label v-for="s in filteredExclusions" :key="s.id" class="check-field"
            ><input v-model="exclusionIds" type="checkbox" :value="s.id" />{{
              s.name
            }}
            <span v-if="s.no"> · {{ s.no }}</span
            ><small v-if="!s.enabled">（已停用）</small></label
          >
          <p v-if="!filteredExclusions.length" class="muted">未找到学生</p>
        </div>
        <button type="button" class="text-button" @click="exclusionIds = []">
          清除全部临时排除
        </button>
        <p class="muted">
          已选择 {{ exclusionIds.length }} 人，仅影响当前班级。
        </p></template
      ></AppDialog
    >
  </main>
</template>
