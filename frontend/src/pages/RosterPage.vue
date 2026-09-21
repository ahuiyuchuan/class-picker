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
} from "lucide-vue-next";
import ClassSelect from "../components/ClassSelect.vue";
import AppDialog from "../components/AppDialog.vue";
import RuleFields from "../components/RuleFields.vue";
import Segmented from "../components/Segmented.vue";
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
  nameCol = ref(1),
  noCol = ref(2),
  dataStartRow = ref(2),
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
const rawRows = computed(() =>
  modal.value === "paste"
    ? batch.value
        .split(/\r?\n/)
        .filter((x) => x.trim())
        .map((x) => [x.trim()])
    : (sheets.value[sheet.value] || [])
        .slice(Math.max(0, dataStartRow.value - 1))
        .filter((r) => r.some((x) => String(x).trim())),
);
const importRows = computed(() =>
  rawRows.value.map((r) => ({
    name: String(
      r[(modal.value === "paste" ? 1 : nameCol.value) - 1] || "",
    ).trim(),
    // 学号列为 0 时明确表示不导入学号，不能使用 JavaScript 的负索引语义。
    no:
      modal.value === "paste" || noCol.value <= 0
        ? ""
        : String(r[noCol.value - 1] || "").trim(),
  })),
);
const importErrors = computed(() => {
  // 行号按工作表原始行计算，先跳过说明/表头，再忽略空行。
  if (modal.value === "import") {
    if (!Number.isInteger(dataStartRow.value) || dataStartRow.value < 1 ||
        dataStartRow.value > (sheets.value[sheet.value]?.length || 0))
      return ["数据起始行请输入工作表范围内的正整数"];
    if (!Number.isInteger(nameCol.value) || nameCol.value < 1 || nameCol.value > 50 ||
        !Number.isInteger(noCol.value) || noCol.value < 0 || noCol.value > 50)
      return ["请填写有效列号：姓名列 1—50，学号列 0—50"];
  }
  const seen = new Set(
      replace.value
        ? []
        : current.value?.students.map((s) => s.no).filter(Boolean) || [],
    ),
    list = [];
  importRows.value.forEach((r, i) => {
    if (!r.name || r.name.length > 60 || r.no.length > 60)
      list.push(`第 ${i + 1} 行：姓名缺失或字段超过 60 字`);
    if (r.no && seen.has(r.no)) list.push(`第 ${i + 1} 行：学号 ${r.no} 重复`);
    if (r.no) seen.add(r.no);
  });
  return list;
});
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
      if (!importRows.value.length || importErrors.value.length)
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
async function chooseImport() {
  if (busy.value) return;
  busy.value = true;
  try {
    const value = await call("choose_import");
    if (value) {
      sheets.value = value;
      sheet.value = Object.keys(value)[0];
      dataStartRow.value = 2;
      replace.value = false;
      nameCol.value = 1;
      noCol.value = 2;
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
      :wide="['import', 'paste', 'rules'].includes(modal)"
      :class="{
        'rules-dialog': modal === 'rules',
        'class-action-dialog': ['newClass', 'rules', 'rename', 'deleteClass'].includes(modal),
      }"
      :disabled="
        ['paste', 'import'].includes(modal) &&
        (!importRows.length || !!importErrors.length)
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
      <template v-if="['paste', 'import'].includes(modal)">
        <label v-if="modal === 'paste'" class="field"
          >每行一个姓名（同名不自动合并）<textarea
            v-model="batch"
            rows="5"
            placeholder="李小红&#10;王强"
          ></textarea>
        </label>
        <template v-else
          ><Segmented
            v-model="sheet"
            label="工作表"
            :options="Object.keys(sheets).map((k) => [k, k])"
          />
          <div class="import-mapping">
            <label
              >姓名在第
              <input v-model.number="nameCol" type="number" min="1" max="50" />
              列</label
            ><label
              >学号在第
              <input v-model.number="noCol" type="number" min="0" max="50" />
              列（0 表示无学号）</label
            ><label
              >数据从第 <input v-model.number="dataStartRow" type="number" min="1" :max="sheets[sheet]?.length || 1" aria-label="数据起始行" /> 行开始</label
            >
          </div></template
        >
        <label class="check-field"
          ><input
            v-model="replace"
            type="checkbox"
          />替换当前名单（清空本轮进度，保留历史；先自动备份）</label
        >
        <p class="muted">
          共 {{ importRows.length }} 行；预览前 20 行。学号选填，留空保存为空；同名会作为不同学生保留。
        </p>
        <div v-if="importErrors.length" class="form-error">
          {{ importErrors.slice(0, 5).join("；") }}
        </div>
        <div class="import-preview">
          <table>
            <thead>
              <tr>
                <th>行</th>
                <th>姓名</th>
                <th>学号</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in importRows.slice(0, 20)" :key="i">
                <td>{{ i + 1 }}</td>
                <td>{{ r.name || "（缺少姓名）" }}</td>
                <td>{{ r.no || "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </AppDialog>
  </div>
</template>
