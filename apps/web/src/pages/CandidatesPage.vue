<script setup lang="ts">
import { onMounted, ref } from "vue";

import { listCandidates, markExchange, type Candidate, type UserMe } from "../api";
import AppDrawer from "../components/AppDrawer.vue";
import EmptyState from "../components/EmptyState.vue";

const props = defineProps<{ user: UserMe }>();

const candidates = ref<Candidate[]>([]);
const query = ref("");
const loading = ref(true);
const loadError = ref("");
const actionError = ref("");
const selected = ref<Candidate | null>(null);
const markingId = ref<number | null>(null);
const feedback = ref("");

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  actionError.value = "";
  feedback.value = "";
  try {
    candidates.value = await listCandidates(query.value.trim());
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    loadError.value = `加载候选人失败：${message}`;
  } finally {
    loading.value = false;
  }
}

async function recordExchange(candidate: Candidate): Promise<void> {
  if (markingId.value !== null) return;
  markingId.value = candidate.id;
  actionError.value = "";
  feedback.value = "";
  try {
    await markExchange(candidate.id, props.user.username);
    feedback.value = `已记录${candidate.name}的简历交换`;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    actionError.value = `记录交换失败：${message}`;
  } finally {
    markingId.value = null;
  }
}

onMounted(() => void load());
</script>

<template>
  <section class="page-section candidates-page" data-testid="candidates-page" data-page-panel>
    <header class="page-heading">
      <div>
        <p class="eyebrow">TALENT DISCOVERY</p>
        <h1>HUMAN POTENTIAL.</h1>
        <p class="muted">查询真实候选人基础资料并记录简历交换。</p>
      </div>
    </header>

    <section class="candidate-stats" aria-label="候选人统计">
      <article data-testid="candidate-total"><span>候选人总数</span><strong>{{ candidates.length }}</strong></article>
      <article data-testid="candidate-high-score"><span>高分人才</span><strong>—</strong><small>暂未接入</small></article>
      <article data-testid="candidate-contacted"><span>已联系</span><strong>—</strong><small>暂未接入</small></article>
      <article data-testid="candidate-resume"><span>收到简历</span><strong>—</strong><small>暂未接入</small></article>
    </section>

    <form class="panel candidate-toolbar" @submit.prevent="load">
      <label>
        姓名或 BOSS ID
        <input v-model="query" aria-label="搜索候选人" placeholder="输入姓名或 BOSS ID" />
      </label>
      <label>岗位<select aria-label="筛选候选人岗位" disabled><option>暂未接入</option></select></label>
      <label>处理状态<select aria-label="筛选处理状态" disabled><option>暂未接入</option></select></label>
      <label>AI 分数<select aria-label="筛选 AI 分数" disabled><option>暂未接入</option></select></label>
      <button type="submit" :disabled="loading">搜索</button>
    </form>

    <p v-if="loading" aria-live="polite">正在加载候选人…</p>
    <section v-else-if="loadError" class="panel">
      <p class="error" role="alert">{{ loadError }}</p>
      <button type="button" aria-label="重试加载候选人" @click="load">重试</button>
    </section>
    <p v-else-if="feedback" class="panel success-message" aria-live="polite">{{ feedback }}</p>
    <p v-if="actionError" class="panel error" role="alert">{{ actionError }}</p>

    <EmptyState v-if="!loading && !loadError && candidates.length === 0" title="暂无候选人" description="当前条件下没有查询到候选人。" />
    <div v-else-if="!loading && !loadError" class="candidate-list">
      <article v-for="candidate in candidates" :key="candidate.id" class="panel candidate-card candidate-row">
        <div class="candidate-identity">
          <span class="candidate-avatar">{{ (candidate.name || '?').slice(0, 1) }}</span>
          <div><h2>{{ candidate.name || "未命名候选人" }}</h2><p class="muted">BOSS ID：{{ candidate.boss_id || "未提供" }}</p></div>
        </div>
        <div><small>基础资料</small><p>{{ candidate.age ?? "年龄未知" }}<template v-if="candidate.age !== null"> 岁</template> · {{ candidate.years_of_experience ?? "经验未知" }}<template v-if="candidate.years_of_experience !== null"> 年经验</template></p></div>
        <div><small>来源</small><p>{{ candidate.source }}</p></div>
        <div><small>AI 评估</small><p>— · 暂未接入</p></div>
        <div class="candidate-actions">
          <button type="button" class="secondary" :aria-label="`查看${candidate.name}详情`" @click="selected = candidate">查看详情</button>
          <button type="button" :aria-label="`标记${candidate.name}已交换简历`" :disabled="markingId !== null" @click="recordExchange(candidate)">
            {{ markingId === candidate.id ? "正在记录…" : "标记已交换简历" }}
          </button>
        </div>
      </article>
    </div>

    <AppDrawer :open="Boolean(selected)" :title="selected?.name || '候选人详情'" @close="selected = null">
      <template v-if="selected">
        <dl class="detail-list">
          <div><dt>BOSS ID</dt><dd>{{ selected.boss_id || "未提供" }}</dd></div>
          <div><dt>年龄</dt><dd>{{ selected.age === null ? "未提供" : `${selected.age} 岁` }}</dd></div>
          <div><dt>工作经验</dt><dd>{{ selected.years_of_experience === null ? "未提供" : `${selected.years_of_experience} 年经验` }}</dd></div>
          <div><dt>来源</dt><dd>{{ selected.source }}</dd></div>
          <div><dt>录入时间</dt><dd>{{ selected.created_at || "未提供" }}</dd></div>
        </dl>
        <section class="drawer-section"><p class="eyebrow">EXPERIENCE</p><p>{{ selected.years_of_experience === null ? "经历详情暂未接入" : `${selected.years_of_experience} 年工作经验；经历详情暂未接入` }}</p></section>
        <section class="drawer-section"><p class="eyebrow">MATCH EVIDENCE</p><p class="muted">匹配证据暂未接入</p></section>
        <section class="drawer-section"><p class="eyebrow">RISK NOTE</p><p class="muted">风险提示暂未接入</p></section>
        <section class="drawer-section"><p class="eyebrow">ACTIVITY</p><p class="muted">活动时间线暂未接入</p></section>
        <p class="muted">AI 分数、匹配证据、风险和时间线详情接口暂未提供。</p>
        <button type="button" :aria-label="`查看${selected.name}简历`" disabled>查看简历 · 暂未接入</button>
      </template>
    </AppDrawer>
  </section>
</template>
