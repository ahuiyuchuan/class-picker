<script setup>
/**
 * 产品说明按三个主题切换，版本信息在所有主题下方共用一个底部模块。
 * 复用管理页标题与卡片规范，不在用户页面展示实现技术。
 * @author ahui
 */
import { ref } from "vue";
import {
  ArrowLeft, Info, Database, Shuffle, UsersRound, SlidersHorizontal,
  Lightbulb, BookOpen, PlayCircle, ClipboardList, Target,
} from "lucide-vue-next";

const emit = defineEmits(["back"]);
const activeTab = ref("features");
const tabs = [
  ["features", "功能介绍", Lightbulb],
  ["usage", "使用方式", BookOpen],
  ["data", "数据说明", Database],
];

/**
 * 按左右方向键循环切换主题，Home/End 跳到首尾；焦点与选中主题同步。
 * @param {KeyboardEvent} event 当前 Tab 上的键盘事件，其他按键沿用浏览器行为。
 * @param {number} index 当前 Tab 在 tabs 中的下标。
 */
function navigateTab(event, index) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const next =
    event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  activeTab.value = tabs[next][0];
  event.currentTarget.parentElement.querySelectorAll('[role="tab"]')[next].focus();
}
</script>

<template>
  <div class="management-page about-page">
    <header class="page-heading about-heading">
      <button class="secondary-btn" @click="emit('back')">
        <ArrowLeft :size="20" />返回课堂
      </button>
      <h1><Info />关于</h1>
      <p>了解软件功能与使用方式</p>
    </header>

    <div class="about-scroll">
      <div class="about-content">
        <nav class="about-tabs panel" aria-label="关于页面导航" role="tablist">
          <button
            v-for="([id, label, Icon], index) in tabs"
            :id="'about-tab-' + id"
            :key="id"
            type="button"
            role="tab"
            :aria-selected="activeTab === id"
            aria-controls="about-panel"
            :tabindex="activeTab === id ? 0 : -1"
            @click="activeTab = id"
            @keydown="navigateTab($event, index)"
          >
            <component :is="Icon" :size="20" aria-hidden="true" />{{ label }}
          </button>
        </nav>

        <main id="about-panel" class="about-main" role="tabpanel" :aria-labelledby="'about-tab-' + activeTab">
          <section v-if="activeTab === 'features'" class="about-feature-panel panel">
            <div class="about-product">
              <img src="/app-icon.png" alt="班级随机抽人应用图标" />
              <div class="about-product-copy">
                <h2>班级随机抽人</h2>
                <strong>让课堂互动更简单</strong>
                <p>专为老师设计的课堂抽人工具。集中管理多个班级的学生名单，按课堂需要随机选人，让提问、展示与互动更轻松。</p>
              </div>
            </div>
            <div class="about-feature-columns">
              <article class="about-column">
                <h2><Shuffle :size="22" />主要功能</h2>
                <ul>
                  <li>支持按班级从参与学生中随机抽人</li>
                  <li>提供单人、多人和本轮不重复模式</li>
                  <li>可临时排除学生，灵活调整范围</li>
                  <li>支持导入、导出与编辑学生名单</li>
                </ul>
              </article>
              <article class="about-column">
                <h2><UsersRound :size="22" />怎么用</h2>
                <ul>
                  <li>在班级名单中维护学生信息</li>
                  <li>选择班级、抽取人数与模式</li>
                  <li>点击抽取，查看本次结果</li>
                  <li>按需查看最近抽取记录</li>
                </ul>
              </article>
              <article class="about-column">
                <h2><Target :size="22" />适用场景</h2>
                <ul>
                  <li>课堂提问与互动问答</li>
                  <li>课堂展示与上台发言</li>
                  <li>小组代表与活动人选抽取</li>
                  <li>课前点名与随机检查</li>
                </ul>
              </article>
            </div>
          </section>

          <section v-else-if="activeTab === 'usage'" class="about-info-card panel">
            <h2><BookOpen :size="22" />使用方式</h2>
            <p class="about-section-note">准备好班级名单后，即可返回课堂开始抽取。</p>
            <div class="about-steps">
              <div>
                <span class="about-step-number">01</span><UsersRound />
                <b>准备名单</b><p>通过设置菜单进入班级名单，新建班级并添加或导入学生。</p>
              </div>
              <div>
                <span class="about-step-number">02</span><SlidersHorizontal />
                <b>选择规则</b><p>选择当前班级，设置抽取人数；可为不同班级单独设置规则。</p>
              </div>
              <div>
                <span class="about-step-number">03</span><PlayCircle />
                <b>开始抽取</b><p>点击抽取按钮，或使用空格键开始，等待展示本次结果。</p>
              </div>
              <div>
                <span class="about-step-number">04</span><ClipboardList />
                <b>继续互动</b><p>查看抽取结果和最近记录；按课堂需要继续抽取或重置本轮。</p>
              </div>
            </div>
          </section>

          <section v-else-if="activeTab === 'data'" class="about-info-card panel">
            <h2><Database :size="22" />数据说明</h2>
            <p class="about-section-note">抽取范围由当前班级名单和已设置的规则共同决定。</p>
            <dl class="about-info-grid">
              <div><dt>名单与参与范围</dt><dd>使用当前班级的学生名单；停用或临时排除的学生不参与抽取。</dd></div>
              <div><dt>随机与不重复</dt><dd>在符合规则的学生中随机选择；本轮不重复模式会跳过本轮已抽中的学生。</dd></div>
              <div><dt>离线使用</dt><dd>无需登录，名单、规则和抽取记录保存在本机，不上传学生信息。</dd></div>
              <div><dt>备份与迁移</dt><dd>在应用设置中备份和恢复数据；更换电脑前，请将备份保存到其他位置。</dd></div>
            </dl>
          </section>

        </main>

        <!-- 共用版本信息跟随内容自然排列，切换主题始终保留，避免固定定位遮挡正文。 -->
        <footer class="about-version-footer panel" aria-label="版本信息">
          <dl>
            <div><dt>版本</dt><dd>v1.0.0</dd></div>
            <div><dt>作者</dt><dd>ahui</dd></div>
            <div><dt>应用类型</dt><dd>Windows 桌面应用</dd></div>
            <div><dt>运行方式</dt><dd>免登录 · 离线使用</dd></div>
          </dl>
        </footer>
      </div>
    </div>
  </div>
</template>
