<script setup>
/** @author ahui — 设置草稿与已保存快照分离，返回/关闭时有未保存保护。 */
import { ref, computed } from "vue";
import {
  ArrowLeft,
  Settings,
  History,
  Database,
  ChevronDown,
  RotateCcw,
  Save,
  Info,
} from "lucide-vue-next";
import RuleFields from "../components/RuleFields.vue";
import AppDialog from "../components/AppDialog.vue";
import Segmented from "../components/Segmented.vue";
import { state, change, call, apply } from "../data";
const emit = defineEmits(["back", "notice", "dirty"]);
const draft = ref({ ...state.settings }),
  busy = ref(false),
  error = ref(""),
  confirm = ref(""),
  nextAction = ref(null);
const dirty = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(state.settings),
);
function leave(action = () => emit("back")) {
  if (busy.value) return;
  if (dirty.value) {
    nextAction.value = action;
    confirm.value = "leave";
  } else action();
}
defineExpose({ leave });
async function save() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await change("settings", { values: draft.value });
    draft.value = { ...state.settings };
    emit("notice", "保存成功");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function doConfirm() {
  if (busy.value) return;
  if (confirm.value === "leave") {
    draft.value = { ...state.settings };
    confirm.value = "";
    nextAction.value?.();
    return;
  }
  if (confirm.value === "defaults") {
    draft.value = { ...state.defaults };
    confirm.value = "";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    if (confirm.value === "restore") {
      const result = await call("restore");
      if (result) {
        apply(result);
        draft.value = { ...state.settings };
        emit("notice", "备份已恢复");
      }
    } else if (confirm.value === "clear") {
      await change("clear_history");
      emit("notice", "历史已清空，本轮进度保留");
    }
    confirm.value = "";
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function fileAction(action) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    if (await call(action))
      emit("notice", action === "backup" ? "保存成功" : "已打开数据目录");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="management-page settings-page">
    <header class="page-heading">
      <button class="secondary-btn" :disabled="busy" @click="leave()">
        <ArrowLeft :size="20" />返回课堂
      </button>
      <h1><Settings />应用设置</h1>
      <p>设置默认抽取规则与展示方式</p>
    </header>
    <div class="settings-scroll">
      <div class="settings-content">
        <fieldset :disabled="busy">
          <RuleFields :values="draft" />
          <details class="settings-card fold-card">
            <summary>
              <History /> <b>历史记录</b
              ><span
                >保存记录{{ draft.save_history ? "已开启" : "已关闭" }} ·
                {{
                  draft.history_days
                    ? `保留 ${draft.history_days} 天`
                    : "永久保留"
                }}</span
              ><ChevronDown />
            </summary>
            <div class="setting-row">
              <b>保存抽取记录</b
              ><button
                type="button"
                class="toggle"
                role="switch"
                :aria-checked="draft.save_history"
                aria-label="保存抽取记录"
                @click="draft.save_history = !draft.save_history"
              >
                <i /><span>{{ draft.save_history ? "已开启" : "已关闭" }}</span>
              </button>
            </div>
            <div class="setting-row">
              <div>
                <b>历史保留期限</b
                ><small>保存后清理过期记录，不影响本轮进度。</small>
              </div>
              <Segmented
                v-model="draft.history_days"
                label="历史保留期限"
                :options="[
                  [30, '30 天'],
                  [90, '90 天'],
                  [0, '永久'],
                ]"
              />
            </div>
            <button
              class="secondary-btn danger-text"
              @click="confirm = 'clear'"
            >
              清空历史记录
            </button>
          </details>
          <details class="settings-card fold-card">
            <summary>
              <Database /><b>数据与备份</b
              ><span
                >自动备份{{ draft.auto_backup ? "已开启" : "已关闭" }} · 保留
                {{ draft.backup_count }} 份</span
              ><ChevronDown />
            </summary>
            <div class="setting-row">
              <div>
                <b>自动备份</b
                ><small>每天首次修改前备份；保护备份始终保留。</small>
              </div>
              <button
                type="button"
                class="toggle"
                role="switch"
                :aria-checked="draft.auto_backup"
                aria-label="自动备份"
                @click="draft.auto_backup = !draft.auto_backup"
              >
                <i /><span>{{ draft.auto_backup ? "已开启" : "已关闭" }}</span>
              </button>
            </div>
            <div class="setting-row">
              <b>每日备份保留数量</b
              ><Segmented
                v-model="draft.backup_count"
                label="备份数量"
                :options="[
                  [3, '3 份'],
                  [7, '7 份'],
                  [15, '15 份'],
                ]"
              />
            </div>
            <div class="file-actions">
              <button class="secondary-btn" @click="fileAction('backup')">
                备份到文件</button
              ><button class="secondary-btn" @click="confirm = 'restore'">
                从备份恢复</button
              ><button class="secondary-btn" @click="fileAction('open_data')">
                打开数据目录
              </button>
            </div>
            <p class="muted">
              更换电脑前请备份到 U 盘等其他位置。同盘备份不能防止硬盘损坏。
            </p>
          </details>
        </fieldset>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      </div>
    </div>
    <footer class="settings-footer">
      <span class="save-status"
        ><Info :size="18" />{{
          dirty ? "有未保存的更改" : "所有设置已保存"
        }}</span
      >
      <div>
        <button
          class="text-button"
          :disabled="busy"
          @click="confirm = 'defaults'"
        >
          <RotateCcw :size="18" />恢复默认设置</button
        ><button
          class="secondary-btn"
          :disabled="!dirty || busy"
          @click="
            draft = { ...state.settings };
            error = '';
          "
        >
          取消更改</button
        ><button class="primary-btn" :disabled="!dirty || busy" @click="save">
          <Save :size="18" />{{ busy ? "保存中…" : "保存设置" }}
        </button>
      </div>
    </footer>
    <AppDialog
      v-if="confirm"
      :title="
        {
          leave: '放弃未保存的更改？',
          defaults: '恢复默认设置？',
          restore: '恢复备份？',
          clear: '清空历史记录？',
        }[confirm]
      "
      :busy="busy"
      :error="error"
      submit-label="确认"
      @close="confirm = ''"
      @submit="doConfirm"
      ><p>
        {{
          {
            leave: "当前编辑尚未保存，离开后将丢弃这些更改。",
            defaults:
              "全局设置将恢复为默认值，点击保存后生效。班级独立规则保持不变。",
            restore:
              "将选择备份文件并覆盖全部名单、配置、进度和记录。恢复前会自动备份当前数据，未保存的设置将丢弃。",
            clear:
              "将清空全部班级的历史记录，本轮进度和最近抽取结果保留。执行前自动生成保护备份。",
          }[confirm]
        }}
      </p></AppDialog
    >
  </div>
</template>
