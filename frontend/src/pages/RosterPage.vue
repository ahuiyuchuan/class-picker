<script setup>
/** @author ahui
 * 名单维护页：管理班级选择独立于课堂选择。所有写入由 Python 校验并提交。
 * 新增行在当前页面生命周期中按班级保留草稿；批量保存成功后才清除。
 * 对话框失败保留输入；导入先预览，确认后整批事务提交，空学号始终保持为空。
 */
import { ref, computed, nextTick, watch } from "vue";
import {
  ArrowLeft,
  ArrowUp,
  ArrowDown,
  GraduationCap,
  UsersRound,
  PlusCircle,
  Settings,
  Search,
  UserPlus,
  Clipboard,
  Upload,
  Download,
  Pencil,
  Trash2,
  CheckCircle2,
  MinusCircle,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Check,
  X,
  Undo2,
} from "lucide-vue-next";
import ClassSelect from "../components/ClassSelect.vue";
import AppDialog from "../components/AppDialog.vue";
import RuleFields from "../components/RuleFields.vue";
import { cellText, columnLabel, previewSheet, validateImportIssues } from "../rosterImport";
import { state, change, call } from "../data";
const props = defineProps({ initialId: Number });
const emit = defineEmits(["back", "notice"]);
const selectedId = ref(props.initialId),
  search = ref(""),
  selectedStudents = ref([]),
  editingId = ref(null),
  editingDraft = ref({}),
  classSelectRef = ref(null),
  modal = ref(""),
  busy = ref(false),
  error = ref("");
const form = ref({}),
  batch = ref(""),
  sheets = ref({}),
  sheet = ref(""),
  sheetConfigs = ref({}),
  replace = ref(false),
  follow = ref(true);
const current = computed(
  () =>
    state.classes.find((c) => c.id === selectedId.value) || state.classes[0],
);
const names = computed(() => state.classes.map((c) => c.name));
// 仅有实际字段变更才提示放弃，单纯进入编辑态可直接离开。
const editDirty = computed(() => {
  const original = current.value?.students.find((student) => student.id === editingId.value);
  return !!original && (editingDraft.value.name !== original.name ||
    editingDraft.value.no !== (original.no || "") || editingDraft.value.enabled !== !!original.enabled);
});
// 新增草稿按班级隔离，切换班级后仍可继续填写；只在保存成功后移除对应草稿。
const newRowsByClass = ref({});
const nextAction = ref(null);
let draftSequence = 0;
const newRows = computed(() => newRowsByClass.value[current.value?.id] || []);
const filledNewRows = computed(() =>
  newRows.value.filter((row) => row.name.trim() || row.no.trim()),
);
watch(
  () => current.value?.id,
  () => {
    cancelEdit();
    selectedStudents.value = [];
    search.value = "";
  },
);
const students = computed(
  () =>
    current.value?.students.filter((s) =>
      `${s.name} ${s.no || ""}`.includes(search.value.trim()),
    ) || [],
);
// 筛选后的全选只作用于可见名单，隐藏行保留原选择；不能仅比较两个数组的长度。
const selectedVisibleCount = computed(() => {
  const ids = new Set(selectedStudents.value);
  return students.value.filter((student) => ids.has(student.id)).length;
});
/** @param {Event} event 表头复选框 change 事件；保存期间拒绝变更选择。 */
function selectVisible(event) {
  if (busy.value) return;
  const visible = new Set(students.value.map((student) => student.id));
  selectedStudents.value = event.target.checked
    ? [...new Set([...selectedStudents.value, ...visible])]
    : selectedStudents.value.filter((id) => !visible.has(id));
}
// 导入替换或逐行删除后移除失效选择，防止批量删除提交已不存在的学生 ID。
watch(() => current.value?.students.map((student) => student.id), (ids = []) => {
  const existing = new Set(ids);
  selectedStudents.value = selectedStudents.value.filter((id) => existing.has(id));
  if (editingId.value && !existing.has(editingId.value)) cancelEdit();
});
// 勾选决定是否提交，当前表只决定预览；映射按表保留，避免切换时覆盖。
const sheetNames = computed(() => Object.keys(sheets.value));
const activeConfig = computed(() => sheetConfigs.value[sheet.value]);
const selectedSheets = computed(() => sheetNames.value.filter((name) => sheetConfigs.value[name]?.selected));
const sheetPreviews = computed(() => Object.fromEntries(sheetNames.value.map((name) =>
  [name, previewSheet(name, sheets.value[name], sheetConfigs.value[name])],
)));
const importEntries = computed(() => modal.value === "paste"
  ? batch.value.split(/\r?\n/).flatMap((name, index) => name.trim()
      ? [{ sheet: "粘贴名单", row: index + 1, name: name.trim(), no: "" }] : [])
  : selectedSheets.value.flatMap((name) => sheetPreviews.value[name].entries));
const importRows = computed(() => importEntries.value.map(({ name, no }) => ({ name, no })));
const previewRows = computed(() => modal.value === "paste"
  ? importEntries.value : sheetPreviews.value[sheet.value]?.entries || []);
// 分页仅限制 DOM 渲染量，校验和提交始终使用完整数据；切表或修改映射回到首页。
const previewPage = ref(1), previewTable = ref(null), issueIndex = ref(0);
// 一次仅编辑一行；草稿未保存时阻止导入、切表和翻页，避免无声丢失。
const previewEdit = ref(null);
const removedPreviewRows = ref([]);
const previewPageSize = 50;
const previewPageCount = computed(() => Math.max(1, Math.ceil(previewRows.value.length / previewPageSize)));
const pagedPreviewRows = computed(() => previewRows.value.slice(
  (previewPage.value - 1) * previewPageSize, previewPage.value * previewPageSize,
));
// 使用 Vue 的批处理时机，避免读取文件初始化期间先看到新 sheets、旧 configs。
watch([sheet, modal, batch, () => activeConfig.value?.nameCol,
  () => activeConfig.value?.noCol, () => activeConfig.value?.startRow], () => { previewPage.value = 1; });
watch(previewPageCount, (count) => { previewPage.value = Math.min(previewPage.value, count); });
watch(modal, () => { previewEdit.value = null; });
watch(previewPage, () => { if (previewTable.value) previewTable.value.scrollTop = 0; });
const columnOptions = computed(() => {
  const rows = sheets.value[sheet.value] || [];
  const width = rows.reduce((max, row) => Math.max(max, row.length), 0);
  const header = rows[(activeConfig.value?.startRow || 1) - 2] || [];
  return Array.from({ length: width }, (_, index) => {
    const sample = cellText(header[index]) || cellText(rows[(activeConfig.value?.startRow || 1) - 1]?.[index]);
    return { value: index + 1, label: `${columnLabel(index + 1)} 列${sample ? ` · ${sample.slice(0, 24)}` : ""}` };
  });
});
const importIssues = computed(() => {
  const issues = modal.value === "import"
    ? selectedSheets.value.flatMap((name) => sheetPreviews.value[name].issues) : [];
  if (modal.value === "import" && !selectedSheets.value.length)
    issues.push({ sheet: null, row: null, message: "请至少勾选一张工作表" });
  return [...issues, ...validateImportIssues(importEntries.value, replace.value ? [] : current.value?.students || [])];
});
const importErrors = computed(() => importIssues.value.map((issue) => issue.message));
const currentIssue = computed(() => importIssues.value[issueIndex.value]);
watch(importIssues, () => { issueIndex.value = 0; });
const issuesBySheet = computed(() => Object.fromEntries(sheetNames.value.map((name) =>
  [name, importIssues.value.filter((issue) => issue.sheet === name)],
)));
const activeRowIssues = computed(() => {
  const result = new Map();
  for (const issue of importIssues.value.filter((item) => item.sheet === (modal.value === "paste" ? "粘贴名单" : sheet.value))) {
    if (!issue.row) continue;
    result.set(issue.row, [...(result.get(issue.row) || []), issue.message]);
  }
  return result;
});
/**
 * 开启本次导入的行内草稿；另一行未保存时不覆盖用户输入。
 * @param {Object} entry 带工作表、原始行号、姓名和学号的预览行。
 * @returns {Promise<void>} 渲染输入框后聚焦姓名，不写入数据库。
 */
async function editPreviewRow(entry) {
  if (previewEdit.value) {
    emit("notice", "请先保存或取消当前行编辑");
    return;
  }
  previewEdit.value = { ...entry, originalName: entry.name, originalNo: entry.no, nameTouched: false, noTouched: false, error: "" };
  await nextTick();
  previewTable.value?.querySelector('[aria-label="预览姓名"]')?.focus();
}
/** 保存的是内存修正；字段校验失败保留草稿，重复学号交由完整批次校验定位。 */
function savePreviewRow() {
  const draft = previewEdit.value;
  if (!draft || busy.value) return;
  const name = draft.name.trim(), no = draft.no.trim();
  if (!name || name.length > 60 || no.length > 60) {
    draft.error = "姓名必填，姓名和学号均不得超过 60 字";
    return;
  }
  const config = sheetConfigs.value[draft.sheet];
  config.edits ||= {};
  // 显式输入（包括将缺缓存的学号清空）也算修正；未操作的另一字段继续跟随列映射。
  const edit = { ...config.edits[draft.row] };
  if (draft.nameTouched || name !== draft.originalName) edit.name = name;
  if (draft.noTouched || no !== draft.originalNo) edit.no = no;
  config.edits[draft.row] = edit;
  previewEdit.value = null;
}
/**
 * 移除只排除本次导入的原始行，保留源行号；撤销按后进先出恢复，不修改原文件。
 * @param {Object} entry 需要排除的预览行，包含 sheet 和原始 row。
 */
function removePreviewRow(entry) {
  if (busy.value || previewEdit.value) return;
  const config = sheetConfigs.value[entry.sheet];
  config.removedRows ||= [];
  config.removedRows.push(entry.row);
  removedPreviewRows.value.push({ sheet: entry.sheet, row: entry.row });
}
/** 恢复最近移除的行及其已有修正，完整批次重新校验；不自动勾选工作表。 */
function undoPreviewRemoval() {
  if (busy.value || previewEdit.value) return;
  const entry = removedPreviewRows.value.pop();
  if (!entry) return;
  const config = sheetConfigs.value[entry.sheet];
  config.removedRows = config.removedRows.filter((row) => row !== entry.row);
}
/** 定位当前问题，跨工作表及分页后聚焦原始行；配置错误聚焦配置区域，不修改选择。 */
async function locateImportIssue() {
  const issue = currentIssue.value;
  if (!issue) return;
  if (issue.sheet && modal.value === "import") sheet.value = issue.sheet;
  await nextTick();
  const index = previewRows.value.findIndex((entry) => entry.row === issue.row);
  if (index >= 0) {
    previewPage.value = Math.floor(index / previewPageSize) + 1;
    await nextTick();
    const row = previewTable.value?.querySelector(`[data-row="${issue.row}"]`);
    row?.scrollIntoView({ block: "center" });
    row?.focus({ preventScroll: true });
  } else {
    document.querySelector(issue.sheet ? '.import-mapping input' : '.import-select-all input')?.focus();
  }
}
/**
 * 全选包含空表，空表会明确报告无有效数据；不会静默跳过用户勾选的表。
 * @param {boolean} selected true 全选，false 取消全选；仅作用于本次打开的文件。
 */
function selectAllSheets(selected) {
  for (const config of Object.values(sheetConfigs.value)) config.selected = selected;
}
/** 仅复制映射和起始行；各表选择状态独立，宽度不同的目标表仍须通过校验。 */
function applySheetMapping() {
  const { nameCol, noCol, startRow } = activeConfig.value;
  for (const name of selectedSheets.value.filter((value) => value !== sheet.value))
    Object.assign(sheetConfigs.value[name], { nameCol, noCol, startRow });
}
const title = computed(
  () =>
    ({
      newClass: "新建班级",
      rename: "修改班级名称",
      paste: "批量粘贴导入",
      import: "预览导入名单",
      rules: "本班抽取规则",
      deleteClass: "删除班级？",
      deleteStudent: "删除学生？",
      leaveDrafts: "放弃未保存的学生？",
      leaveEdit: "放弃本行修改？",
      discardDrafts: "取消本班新增？",
    })[modal.value],
);
function open(type, item = {}) {
  if (busy.value) return;
  error.value = "";
  modal.value = type;
  form.value = { ...item };
  if (type === "rename") form.value = { name: current.value.name };
  if (type === "paste") {
    batch.value = "";
    replace.value = false;
  }
  if (type === "rules") {
    follow.value = !Object.keys(current.value.rules).length;
    form.value = { ...state.settings, ...current.value.rules };
  }
}
/**
 * 每次点击追加一条空行并聚焦姓名；保留已有草稿，支持连续添加后统一保存。
 * 每班同时最多保留 100 行，避免误操作生成过大的编辑表格。
 */
async function startAdd() {
  if (!current.value || busy.value) return;
  if (newRows.value.length >= 100) {
    emit("notice", "每班最多同时填写 100 行，请先保存或移除空行");
    return;
  }
  const row = {
    key: ++draftSequence,
    name: "",
    no: "",
    enabled: true,
    error: "",
  };
  newRowsByClass.value[current.value.id] = [...newRows.value, row];
  await nextTick();
  document.getElementById(`new-name-${row.key}`)?.focus();
}
/** 删除未入库的空行或草稿；不对已保存学生执行删除。 */
function removeNewRow(row) {
  if (busy.value) return;
  newRowsByClass.value[current.value.id] = newRows.value.filter(
    (item) => item.key !== row.key,
  );
}
/**
 * 输入框获得焦点时滚入可见区域；配合滚动容器顶部留白，避免固定表头遮挡。
 * @param {FocusEvent} event 表格内输入框或按钮的焦点事件，支持键盘逐行填写。
 */
function revealTableField(event) {
  event.target.scrollIntoView({ block: "nearest", inline: "nearest" });
}
/** 有填写内容时确认取消，空白行可直接清除。 */
function discardNewRows() {
  if (busy.value) return;
  if (filledNewRows.value.length) open("discardDrafts");
  else newRowsByClass.value[current.value.id] = [];
}
/**
 * 保存本班有内容的新增行；空行忽略，校验或请求失败保留全部输入。
 * 后端使用一次事务写入，防止前几行成功、后几行失败导致重复录入。
 */
async function saveNewRows() {
  if (!current.value || busy.value) return;
  const rows = filledNewRows.value;
  if (!rows.length) {
    emit("notice", "请先填写学生姓名");
    return;
  }
  const used = new Set(
    current.value.students.map((student) => student.no).filter(Boolean),
  );
  newRows.value.forEach((row) => {
    row.error = "";
  });
  for (const row of rows) {
    const no = row.no.trim();
    if (!row.name.trim()) row.error = "请填写姓名";
    else if (row.name.trim().length > 60 || no.length > 60)
      row.error = "姓名和学号最多 60 个字符";
    else if (no && used.has(no)) row.error = "学号重复，请修改";
    if (no) used.add(no);
  }
  const invalid = rows.find((row) => row.error);
  if (invalid) {
    emit("notice", "请修正标记行后再保存");
    await nextTick();
    document
      .getElementById(`new-${invalid.name.trim() ? "no" : "name"}-${invalid.key}`)
      ?.focus();
    return;
  }
  busy.value = true;
  const cid = current.value.id;
  try {
    await change("add_students", {
      class_id: cid,
      rows: rows.map(({ name, no, enabled }) => ({ name, no, enabled })),
    });
    newRowsByClass.value[cid] = [];
    search.value = "";
    emit("notice", "保存成功");
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
/**
 * 返回课堂或点击标题栏关闭按钮前保护新增草稿；未填写空行无需确认。
 * @param {Function} action 用户确认离开后执行的同步导航或异步窗口操作。
 */
function leave(action = () => emit("back")) {
  if (busy.value) return;
  const hasInput = Object.values(newRowsByClass.value).some((rows) =>
    rows.some((row) => row.name.trim() || row.no.trim()),
  );
  if (hasInput || editDirty.value) {
    nextAction.value = action;
    open("leaveDrafts");
  } else action();
}
defineExpose({ leave });
function cancelEdit() {
  editingId.value = null;
  editingDraft.value = {};
}
/**
 * 在按钮 click 的捕获阶段展开，早于弹窗挂载和 busy 更新。
 * 保留按钮焦点；关联区域由 ClassSelect 识别，避免先关闭再重开及筛选丢失。
 */
function ensureClassSelectOpen() {
  classSelectRef.value?.ensureOpen(false);
}
async function submit() {
  if (busy.value) return;
  if (modal.value === "leaveEdit") {
    cancelEdit();
    modal.value = "";
    nextAction.value?.();
    return;
  }
  if (modal.value === "leaveDrafts") {
    newRowsByClass.value = {};
    modal.value = "";
    nextAction.value?.();
    return;
  }
  if (modal.value === "discardDrafts") {
    newRowsByClass.value[current.value.id] = [];
    modal.value = "";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const cid = current.value?.id;
    if (modal.value === "newClass" || modal.value === "rename") {
      await change("save_class", {
        name: form.value.name,
        ...(modal.value === "rename" ? { class_id: cid } : {}),
      });
      if (modal.value === "newClass")
        selectedId.value = state.classes.find(
          (c) => c.name === form.value.name.trim(),
        )?.id;
    } else if (modal.value === "deleteStudent")
      await change("delete_student", { id: form.value.id, class_id: cid });
    else if (modal.value === "deleteClass") {
      await change("delete_class", { class_id: cid });
      delete newRowsByClass.value[cid];
    } else if (["paste", "import"].includes(modal.value)) {
      if (!importRows.value.length || importErrors.value.length || previewEdit.value)
        throw new Error("请先修正预览中的问题");
      await change("import", {
        class_id: cid,
        rows: importRows.value,
        replace: replace.value,
      });
    } else if (modal.value === "rules") {
      const values = follow.value
        ? {}
        : Object.fromEntries(
            ["count", "mode", "effect", "duration", "show_number"].map((k) => [
              k,
              form.value[k],
            ]),
          );
      await change("rules", { class_id: cid, values });
    }
    modal.value = "";
    emit("notice", "保存成功");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
/**
 * 读取文件并初始化每张表的独立配置；取消选文件不改变当前界面。
 * @returns {Promise<void>} 成功打开预览，读取失败显示提示；始终释放忙碌锁。
 */
async function chooseImport() {
  if (busy.value) return;
  busy.value = true;
  try {
    const value = await call("choose_import");
    if (value) {
      sheets.value = value;
      previewEdit.value = null;
      removedPreviewRows.value = [];
      sheet.value = Object.keys(value).find((name) => value[name].some((row) =>
        row.some((cell) => cell?.issue || cellText(cell)))) || Object.keys(value)[0];
      sheetConfigs.value = Object.fromEntries(Object.keys(value).map((name) => [name, {
        selected: name === sheet.value, startRow: 2, nameCol: 1, noCol: null,
      }]));
      replace.value = false;
      // 文件读取使用 busy 锁；在 finally 解锁前直接切换到预览态。
      error.value = "";
      modal.value = "import";
    }
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
async function exportList() {
  if (busy.value) return;
  busy.value = true;
  try {
    if (await call("export", { class_id: current.value.id }))
      emit("notice", "名单已导出");
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
/**
 * 按完整名单移动一位并持久化；筛选和编辑期间不排序，避免隐藏行或草稿造成歧义。
 * @param {Object} student 当前班级中已保存的学生。
 * @param {number} direction -1 上移，1 下移。
 */
async function moveStudent(student, direction) {
  if (busy.value || search.value.trim() || editingId.value || newRows.value.length) return;
  busy.value = true;
  try {
    await change("move_student", { class_id: current.value.id, id: student.id, direction });
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
/** 模板下载也复用忙碌锁，防止连续点击打开多个系统保存框。 */
async function downloadTemplate() {
  if (busy.value) return;
  busy.value = true;
  try {
    if (await call("download_template")) emit("notice", "导入模板已下载");
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
/** 有行编辑改动时先确认，避免切班或编辑另一行静默丢失输入。 */
function guardEdit(action) {
  if (busy.value) return;
  if (editDirty.value) {
    nextAction.value = action;
    open("leaveEdit");
  } else action();
}
function startEdit(student) {
  if (busy.value) return;
  guardEdit(() => setEditingStudent(student));
}
/** 确认放弃旧草稿后建立新编辑副本，绝不直接修改已保存快照。 */
function setEditingStudent(student) {
  editingId.value = student.id;
  editingDraft.value = { name: student.name, no: student.no || "", enabled: !!student.enabled };
}
/**
 * Enter 保存只响应已结束的文本输入；中文输入法选词不触发写入。
 * @param {KeyboardEvent} event 输入框 keydown 事件，229 兼容旧版输入法。
 * @param {Object} student 当前编辑的已保存学生。
 */
function submitEditKey(event, student) {
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  saveEdit(student);
}
async function saveEdit(student) {
  if (busy.value) return;
  busy.value = true;
  try {
    await change("save_student", {
      ...editingDraft.value,
      id: student.id,
      class_id: current.value.id,
    });
    cancelEdit();
    emit("notice", "保存成功");
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
async function deleteSelected() {
  if (!selectedStudents.value.length || busy.value) return;
  busy.value = true;
  try {
    await change("delete_students", { class_id: current.value.id, ids: selectedStudents.value });
    selectedStudents.value = [];
    emit("notice", "已删除选中的学生");
  } catch (e) {
    emit("notice", e.message);
  } finally {
    busy.value = false;
  }
}
async function move(direction) {
  if (busy.value) return;
  busy.value = true;
  try {
    await change("move_class", { class_id: current.value.id, direction });
    modal.value = "";
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="management-page roster-page">
    <header class="page-heading">
      <button class="secondary-btn" :disabled="busy" @click="leave()">
        <ArrowLeft :size="20" />返回课堂
      </button>
      <h1><GraduationCap />班级名单</h1>
      <p>管理班级和学生名单</p>
    </header>
    <section class="roster-classbar panel">
      <ClassSelect
        ref="classSelectRef"
        v-if="current"
        :model-value="current.name"
        :options="names"
        :disabled="busy"
        interaction-scope=".roster-classbar, .class-action-dialog"
        @update:model-value="
          (name) => {
            guardEdit(() => {
              selectedId = state.classes.find((c) => c.name === name).id;
              search = '';
            });
          }
        "
      /><span v-else>尚未创建班级</span
      ><span class="muted roster-count"
        ><UsersRound :size="20" />共
        {{ current?.students.length || 0 }} 名学生</span
      >
      <div class="push-actions" @click.capture="ensureClassSelectOpen">
        <button class="primary-btn" :disabled="busy" @click="open('newClass')">
          <PlusCircle :size="20" />新建班级</button
        ><button
          class="secondary-btn"
          :disabled="!current || busy"
          @click="open('rules')"
        >
          <Settings :size="20" />本班规则</button
        ><div class="class-actions" aria-label="班级操作">
          <button class="text-button" :disabled="!current || busy" @click="open('rename')">修改名称</button>
          <button class="text-button" :disabled="!current || busy" @click="move(-1)">上移</button>
          <button class="text-button" :disabled="!current || busy" @click="move(1)">下移</button>
          <button class="text-button danger-text" :disabled="!current || busy" @click="open('deleteClass')">删除班级</button>
        </div>
      </div>
    </section>
    <section class="roster-panel panel">
      <div class="roster-toolbar">
        <label class="search-field"
          ><Search :size="20" /><input
            v-model="search"
            placeholder="搜索姓名或学号"
            aria-label="搜索姓名或学号" /></label
        ><button
          class="primary-btn"
          :disabled="!current || busy"
          @click="startAdd"
        >
          <UserPlus :size="19" />添加学生</button>
        <button
          class="secondary-btn"
          :disabled="!current || busy"
          @click="open('paste')"
        >
          <Clipboard :size="18" />批量粘贴导入</button
        ><button
          class="secondary-btn"
          :disabled="!current || busy"
          @click="chooseImport"
        >
          <Upload :size="18" />导入名单</button
        ><button
          class="secondary-btn"
          :disabled="!current || busy"
          @click="downloadTemplate"
        >
          <Download :size="18" />下载导入模板</button
        ><button
          class="secondary-btn"
          :disabled="!current || busy"
          @click="exportList"
        >
          <Download :size="18" />导出名单
        </button><button
          v-if="selectedStudents.length"
          class="secondary-btn danger-text"
          :disabled="busy"
          @click="deleteSelected"
        ><Trash2 :size="18" />删除选中（{{ selectedStudents.length }}）</button>
      </div>
      <div v-if="newRows.length" class="draft-toolbar">
        <p>待新增 {{ newRows.length }} 行<span>学号选填，留空即为空；全空行不保存</span></p>
        <div>
          <button class="secondary-btn" :disabled="busy" @click="discardNewRows">取消新增</button>
          <button class="primary-btn" :disabled="busy || !filledNewRows.length" @click="saveNewRows">{{ busy ? '保存中…' : '保存新增' }}</button>
        </div>
      </div>
      <div class="table-scroll" @focusin="revealTableField">
        <table>
          <thead>
            <tr>
              <th class="select-col"><input type="checkbox" aria-label="全选学生" :disabled="busy || !students.length" :checked="selectedVisibleCount === students.length && students.length > 0" :indeterminate="selectedVisibleCount > 0 && selectedVisibleCount < students.length" @change="selectVisible" /></th>
              <th>学号</th>
              <th>姓名</th>
              <th>参与状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in newRows" :key="'draft-' + row.key" class="editing-row new-student-row" :class="{ 'draft-invalid': row.error }">
              <td class="select-col"><span class="draft-row-index">{{ index + 1 }}</span></td>
              <td><input :id="'new-no-' + row.key" v-model="row.no" class="table-input" maxlength="60" placeholder="选填" :aria-label="'新增第' + (index + 1) + '行学号'" :disabled="busy" :aria-invalid="!!row.error" @input="row.error = ''" /></td>
              <td>
                <input :id="'new-name-' + row.key" v-model="row.name" class="table-input" maxlength="60" placeholder="请输入姓名" :aria-label="'新增第' + (index + 1) + '行姓名'" :disabled="busy" :aria-invalid="!!row.error" @input="row.error = ''" />
                <small v-if="row.error" class="draft-row-error" role="alert">{{ row.error }}</small>
              </td>
              <td><label class="inline-check"><input v-model="row.enabled" type="checkbox" :disabled="busy" />参与</label></td>
              <td><button class="icon-btn small" :disabled="busy" :aria-label="'移除新增第' + (index + 1) + '行'" @click="removeNewRow(row)"><Trash2 :size="16" /></button></td>
            </tr>
            <tr v-for="(student, studentIndex) in students" :key="student.id">
              <td class="select-col"><input v-model="selectedStudents" type="checkbox" :disabled="busy" :value="student.id" aria-label="选择学生" /></td>
              <td v-if="editingId !== student.id">{{ student.no || "—" }}</td>
              <td v-else><input v-model="editingDraft.no" :disabled="busy" maxlength="60" class="table-input" placeholder="选填" aria-label="编辑学号" @keydown.enter="submitEditKey($event, student)" /></td>
              <td v-if="editingId !== student.id">{{ student.name }}</td>
              <td v-else><input v-model="editingDraft.name" :disabled="busy" maxlength="60" class="table-input" aria-label="编辑姓名" @keydown.enter="submitEditKey($event, student)" /></td>
              <td>
                <span v-if="editingId !== student.id" class="participation" :class="{ off: !student.enabled }"
                  ><CheckCircle2
                    v-if="student.enabled"
                    :size="19"
                  /><MinusCircle v-else :size="19" />{{
                    student.enabled ? "参与" : "停用"
                  }}</span><label v-else class="inline-check"><input v-model="editingDraft.enabled" :disabled="busy" type="checkbox" />参与</label
                >
              </td>
              <td>
                <div class="row-actions">
                  <button class="icon-btn small" aria-label="上移学生" :title="search.trim() ? '清空搜索后可排序' : '上移'" :disabled="busy || !!search.trim() || !!editingId || newRows.length > 0 || studentIndex === 0" @click="moveStudent(student, -1)"><ArrowUp :size="16" /></button>
                  <button class="icon-btn small" aria-label="下移学生" :title="search.trim() ? '清空搜索后可排序' : '下移'" :disabled="busy || !!search.trim() || !!editingId || newRows.length > 0 || studentIndex === students.length - 1" @click="moveStudent(student, 1)"><ArrowDown :size="16" /></button>
                  <button v-if="editingId !== student.id" class="icon-btn small" :disabled="busy" aria-label="编辑学生" @click="startEdit(student)"><Pencil :size="16" /></button>
                  <button v-else class="text-button" :disabled="busy" @click="saveEdit(student)">保存</button>
                  <button
                    class="icon-btn small"
                    aria-label="删除学生"
                    :disabled="busy"
                    @click="open('deleteStudent', student)"
                  >
                    <Trash2 :size="16" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!students.length && !newRows.length" class="empty-state">
          {{
            !current
              ? "先新建一个班级"
              : search
                ? "未找到匹配的学生"
                : "暂无学生，请添加或导入名单"
          }}
        </div>
      </div>
      <div class="table-caption">
        {{ students.length }} 名学生<span
          >停用不等于临时排除；停用学生不参与抽取</span
        >
      </div>
    </section>
    <AppDialog
      v-if="modal"
      :title="title"
      :busy="busy"
      :error="error"
      :custom-validation="modal === 'import'"
      :wide="['import', 'paste', 'rules'].includes(modal)"
      :class="{
        'rules-dialog': modal === 'rules',
        'import-dialog': modal === 'import',
        'class-action-dialog': ['newClass', 'rules', 'rename', 'deleteClass'].includes(modal),
      }"
      :disabled="
        ['paste', 'import'].includes(modal) &&
        (!importRows.length || !!importErrors.length || !!previewEdit)
      "
      :submit-label="
        modal === 'leaveEdit' ? '放弃修改'
          : modal === 'leaveDrafts' ? '放弃并离开'
          : modal === 'discardDrafts' ? '放弃新增'
          : ['deleteClass', 'deleteStudent'].includes(modal)
          ? '确认删除'
          : ['import', 'paste'].includes(modal)
            ? '确认导入'
            : '保存'
      "
      @close="modal = ''"
      @submit="submit"
    >
      <template v-if="modal === 'import'" #subtitle>
        <p class="import-subtitle">导入到 {{ current.name }}</p>
      </template>
      <template v-if="modal === 'import'" #footer-summary>
        <div class="import-footer-summary">
          <p role="status">已选 {{ selectedSheets.length }} 张工作表，共 {{ importRows.length }} 人</p>
          <label class="check-field"><input v-model="replace" :disabled="busy" type="checkbox" />替换当前名单
            <span>清空本轮进度，保留历史；导入前自动备份</span>
          </label>
          <p v-if="importErrors.length" class="danger-text">请先处理所选工作表中的错误</p>
          <p v-if="previewEdit" class="danger-text">请先保存或取消行内编辑</p>
        </div>
      </template>
      <p v-if="modal === 'leaveDrafts'">有未保存的学生信息，离开将丢弃新增草稿和当前行编辑。已保存的名单不受影响。</p>
      <p v-if="modal === 'leaveEdit'">当前行修改尚未保存，继续将丢弃本行修改。</p>
      <p v-if="modal === 'discardDrafts'">将清除本班未保存的新增行，已保存的学生不受影响。</p>
      <label v-if="['newClass', 'rename'].includes(modal)" class="field"
        >班级名称<input
          v-model="form.name"
          maxlength="60"
          required
          placeholder="例如：三年级一班"
      /></label>
      <p v-if="modal === 'deleteClass'">
        将删除「{{ current.name }}」的全部
        {{ current.students.length }}
        名学生、进度和历史。执行前自动生成保护备份。
      </p>
      <p v-if="modal === 'deleteStudent'">
        删除「{{ form.name }}」？历史抽取记录保留，执行前生成保护备份。
      </p>
      <template v-if="modal === 'rules'"
        ><label class="check-field"
          ><input v-model="follow" type="checkbox" />跟随全局设置</label
        ><RuleFields :values="follow ? state.settings : form" partial :disabled="follow || busy" />
        <p v-if="follow" class="muted">
          当前跟随全局设置，下面内容仅供查看。
        </p></template
      >
      <div v-if="['paste', 'import'].includes(modal)" :class="modal === 'import' ? 'import-workspace' : 'paste-workspace'">
        <aside v-if="modal === 'import'" class="import-sidebar">
          <div class="import-sheet-actions"><strong>工作表</strong><span>已选 {{ selectedSheets.length }}/{{ sheetNames.length }}</span></div>
          <label class="check-field import-select-all">
            <input type="checkbox" :disabled="!!previewEdit" :checked="selectedSheets.length === sheetNames.length"
              :indeterminate="selectedSheets.length > 0 && selectedSheets.length < sheetNames.length"
              @change="selectAllSheets($event.target.checked)" />全选
          </label>
          <div class="import-sheet-list" aria-label="选择导入工作表">
            <div v-for="name in sheetNames" :key="name" class="import-sheet-item" :class="{ active: sheet === name }">
              <input v-model="sheetConfigs[name].selected" :disabled="!!previewEdit" type="checkbox" :aria-label="`导入工作表 ${name}`" />
              <button type="button" class="text-button" :disabled="!!previewEdit" :aria-pressed="sheet === name" @click="sheet = name">
                <span>{{ name }}</span>
                <small v-if="issuesBySheet[name]?.length" class="danger-text"><AlertCircle :size="13" />{{ issuesBySheet[name].length }} 处错误</small>
                <small v-else>{{ sheetPreviews[name].entries.length }} 人</small>
              </button>
            </div>
          </div>
        </aside>
        <section class="import-main">
        <label v-if="modal === 'paste'" class="field"
          >每行一个姓名（同名不自动合并）<textarea
            v-model="batch"
            rows="5"
            placeholder="李小红&#10;王强"
          ></textarea>
        </label>
        <fieldset v-else-if="activeConfig" class="import-config" :disabled="!!previewEdit">
            <p class="import-sheet-title"><strong>{{ sheet }}</strong><span>{{ previewRows.length }} 人<span v-if="!activeConfig.selected"> · 未选中</span></span></p>
            <div class="import-mapping">
              <label>姓名列（必选）
                <select v-model="activeConfig.nameCol" aria-label="姓名列">
                  <option :value="null">请选择姓名列</option>
                  <option v-for="column in columnOptions" :key="column.value" :value="column.value">{{ column.label }}</option>
                </select>
              </label>
              <label>学号列（选填）
                <select v-model="activeConfig.noCol" aria-label="学号列">
                  <option :value="null">不导入学号</option>
                  <option v-for="column in columnOptions" :key="column.value" :value="column.value">{{ column.label }}</option>
                </select>
              </label>
              <label>数据起始行
                <input v-model.number="activeConfig.startRow" type="number" min="1" :max="sheets[sheet]?.length || 1" aria-label="数据起始行" />
              </label>
            </div>
            <div v-if="selectedSheets.length > 1" class="import-mapping-action">
              <button type="button" class="text-button" @click="applySheetMapping">将此配置应用到其他已选表</button>
            </div>
        </fieldset>
        <label v-if="modal === 'paste'" class="check-field"
          ><input
            v-model="replace"
            type="checkbox"
          />替换当前名单（清空本轮进度，保留历史；先自动备份）</label
        >
        <p v-if="modal === 'paste'" class="muted" role="status">
          共 {{ importRows.length }} 人，导入「{{ current.name }}」。
        </p>
        <div v-if="currentIssue" class="form-error import-errors" role="alert">
          <AlertCircle :size="16" />
          <span>{{ currentIssue.message }}</span>
          <button v-if="currentIssue.sheet" type="button" class="text-button" :disabled="!!previewEdit" @click="locateImportIssue">查看问题</button>
          <div v-if="importIssues.length > 1" class="import-issue-nav">
            <button type="button" class="icon-btn" aria-label="上一处问题" title="上一处问题" :disabled="issueIndex === 0" @click="issueIndex--"><ChevronLeft :size="16" /></button>
            <small>{{ issueIndex + 1 }}/{{ importIssues.length }}</small>
            <button type="button" class="icon-btn" aria-label="下一处问题" title="下一处问题" :disabled="issueIndex === importIssues.length - 1" @click="issueIndex++"><ChevronRight :size="16" /></button>
          </div>
        </div>
        <div class="import-preview-title"><strong>数据预览</strong><span>共 {{ previewRows.length }} 条</span>
          <button v-if="modal === 'import' && removedPreviewRows.length" type="button" class="text-button" :disabled="!!previewEdit" @click="undoPreviewRemoval"><Undo2 :size="14" />撤销移除（{{ removedPreviewRows.length }}）</button>
        </div>
        <div ref="previewTable" class="import-preview" tabindex="0" aria-label="数据预览表格">
          <table>
            <thead>
              <tr>
                <th>原始行号</th>
                <th>姓名</th>
                <th>学号</th>
                <th v-if="modal === 'import'" class="preview-actions-column">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in pagedPreviewRows" :key="r.row" :data-row="r.row" tabindex="-1" :class="{ 'import-row-error': activeRowIssues.has(r.row) }">
                <td>{{ r.row }}</td>
                <td>
                  <input v-if="previewEdit?.sheet === r.sheet && previewEdit?.row === r.row" v-model="previewEdit.name" class="table-input" aria-label="预览姓名" @input="previewEdit.nameTouched = true" @keydown.enter.prevent="!$event.isComposing && savePreviewRow()" @keydown.esc.stop.prevent="previewEdit = null" />
                  <template v-else>{{ r.name || "（缺少姓名）" }}</template>
                  <small v-if="previewEdit?.sheet === r.sheet && previewEdit?.row === r.row && previewEdit.error" class="import-row-message" role="alert">{{ previewEdit.error }}</small>
                  <small v-else-if="activeRowIssues.has(r.row)" class="import-row-message">{{ activeRowIssues.get(r.row).join('；') }}</small>
                </td>
                <td>
                  <input v-if="previewEdit?.sheet === r.sheet && previewEdit?.row === r.row" v-model="previewEdit.no" class="table-input" aria-label="预览学号" @input="previewEdit.noTouched = true" @keydown.enter.prevent="!$event.isComposing && savePreviewRow()" @keydown.esc.stop.prevent="previewEdit = null" />
                  <template v-else>{{ r.no || "—" }}</template>
                </td>
                <td v-if="modal === 'import'">
                  <div class="preview-row-actions">
                    <template v-if="previewEdit?.sheet === r.sheet && previewEdit?.row === r.row">
                      <button type="button" class="icon-btn small" aria-label="保存预览行" title="保存" @click="savePreviewRow"><Check :size="16" /></button>
                      <button type="button" class="icon-btn small" aria-label="取消预览编辑" title="取消" @click="previewEdit = null"><X :size="16" /></button>
                    </template>
                    <template v-else>
                      <button type="button" class="icon-btn small" aria-label="编辑预览行" title="编辑" :disabled="!!previewEdit" @click="editPreviewRow(r)"><Pencil :size="16" /></button>
                      <button type="button" class="icon-btn small" aria-label="移除预览行" title="从本次导入移除" :disabled="!!previewEdit" @click="removePreviewRow(r)"><Trash2 :size="16" /></button>
                    </template>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="!previewRows.length" class="import-empty">暂无可预览数据</p>
        </div>
        <nav class="import-pagination" aria-label="预览分页">
          <span>每页 50 条 · {{ previewRows.length ? (previewPage - 1) * previewPageSize + 1 : 0 }}–{{ Math.min(previewPage * previewPageSize, previewRows.length) }} / {{ previewRows.length }} 条</span>
          <div>
            <button type="button" class="icon-btn" aria-label="上一页" title="上一页" :disabled="!!previewEdit || previewPage === 1" @click="previewPage--"><ChevronLeft :size="18" /></button>
            <label><input :value="previewPage" :disabled="!!previewEdit" aria-label="预览页码" type="number" min="1" :max="previewPageCount" @keydown.enter.prevent="$event.target.blur()" @change="previewPage = Math.min(previewPageCount, Math.max(1, Math.trunc(Number($event.target.value) || 1))); $event.target.value = previewPage" /> / {{ previewPageCount }} 页</label>
            <button type="button" class="icon-btn" aria-label="下一页" title="下一页" :disabled="!!previewEdit || previewPage >= previewPageCount" @click="previewPage++"><ChevronRight :size="18" /></button>
          </div>
        </nav>
        </section>
      </div>
    </AppDialog>
  </div>
</template>
