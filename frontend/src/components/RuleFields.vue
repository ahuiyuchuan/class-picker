<script setup>
/** @author ahui — 全局与本班规则共用字段；partial 时只展示可覆盖项目。 */
import Segmented from "./Segmented.vue";
const props = defineProps({ values: Object, partial: Boolean, disabled: Boolean });
</script>
<template>
  <fieldset class="rule-fields" :disabled="disabled">
  <section class="settings-card">
    <h2>默认抽取规则</h2>
    <p class="muted">
      {{
        partial
          ? "此处配置仅影响当前班级。"
          : "未单独设置规则的班级使用以下默认配置。"
      }}
    </p>
    <div class="settings-grid">
      <div class="setting-row">
        <div>
          <b>每次抽取人数</b><small>每次从班级中抽取的学生数量。</small>
        </div>
        <div class="stepper">
          <button
            type="button"
            aria-label="减少人数"
            :disabled="values.count <= 1"
            @click="values.count--"
          >
            −</button
          ><input
            v-model.number="values.count"
            type="number"
            min="1"
            max="100"
            aria-label="每次抽取人数"
          /><button
            type="button"
            aria-label="增加人数"
            :disabled="values.count >= 100"
            @click="values.count++"
          >
            ＋
          </button>
        </div>
      </div>
      <div class="setting-row">
        <div>
          <b>抽取模式</b
          ><small>{{
            values.mode === "unique"
              ? "本轮已抽中的学生不会重复出现。"
              : "前后两次可重复，单次结果不重复。"
          }}</small>
        </div>
        <Segmented
          v-model="values.mode"
          label="抽取模式"
          :options="[
            ['unique', '本轮不重复'],
            ['random', '完全随机'],
          ]"
        />
      </div>
    </div>
  </section>
  <section class="settings-card">
    <h2>展示设置</h2>
    <div class="settings-grid">
      <div class="setting-row">
        <div><b>展示效果</b><small>控制抽取结果的显示方式。</small></div>
        <Segmented
          v-model="values.effect"
          label="展示效果"
          :options="[
            ['direct', '直接显示'],
            ['reveal', '简短揭晓'],
            ['rolling', '姓名滚动'],
          ]"
        />
      </div>
      <div class="setting-row">
        <div><b>动画时长</b><small>直接显示时不播放动画。</small></div>
        <Segmented
          v-model="values.duration"
          label="动画时长"
          :disabled="values.effect === 'direct'"
          :options="[
            [0.5, '0.5 秒'],
            [1, '1 秒'],
            [2, '2 秒'],
          ]"
        />
      </div>
      <div class="setting-row">
        <div><b>显示学生学号</b><small>未填写时不显示；重名时显示已填写的学号。</small></div>
        <button
          class="toggle"
          type="button"
          role="switch"
          aria-label="显示学生学号"
          :aria-checked="values.show_number"
          @click="values.show_number = !values.show_number"
        >
          <i /><span>{{ values.show_number ? "已开启" : "已关闭" }}</span>
        </button>
      </div>
      <div v-if="!partial" class="setting-row">
        <div><b>结果字号</b><small>多人时自动适应显示空间。</small></div>
        <Segmented
          v-model="values.font_size"
          label="结果字号"
          :options="[
            ['auto', '自动'],
            ['normal', '标准'],
            ['large', '大'],
            ['huge', '超大'],
          ]"
        />
      </div>
      <div v-if="!partial" class="setting-row">
        <div><b>启动时全屏</b><small>下次启动时生效。</small></div>
        <button
          class="toggle"
          type="button"
          role="switch"
          aria-label="启动时全屏"
          :aria-checked="values.start_fullscreen"
          @click="values.start_fullscreen = !values.start_fullscreen"
        >
          <i /><span>{{ values.start_fullscreen ? "已开启" : "已关闭" }}</span>
        </button>
      </div>
    </div>
  </section>
  </fieldset>
</template>
