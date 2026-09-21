<script setup lang="ts">
import { onMounted, ref } from "vue";

import { listAgentRuns, type AgentRun } from "../api";
import EmptyState from "../components/EmptyState.vue";
import StatusBadge from "../components/StatusBadge.vue";

const runs = ref<AgentRun[]>([]);
const loading = ref(true);
const error = ref("");

function statusLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (["online", "running", "active"].includes(normalized)) return "在线";
  if (["idle", "waiting"].includes(normalized)) return "空闲";
  if (["paused"].includes(normalized)) return "已暂停";
  if (["offline", "stopped"].includes(normalized)) return "离线";
  if (["error", "failed"].includes(normalized)) return "异常";
  return status;
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  const normalized = status.toLowerCase();
  if (["online", "running", "active"].includes(normalized)) return "success";
  if (["idle", "waiting", "paused"].includes(normalized)) return "warning";
  if (["error", "failed"].includes(normalized)) return "danger";
  return "neutral";
}

function formatHeartbeat(value: string | null): string {
  if (!value) return "暂无心跳";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : `${date.toLocaleString("zh-CN")}（本地时间）`;
}

async function loadRuns(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    runs.value = await listAgentRuns();
  } catch (err) {
    runs.value = [];
    const message = err instanceof Error ? err.message : String(err);
    error.value = `加载 Agent 状态失败：${message}`;
  } finally {
    loading.value = false;
  }
}

onMounted(() => void loadRuns());
</script>

<template>
  <section class="dashboard-page page" data-testid="dashboard-page" data-page-panel>
    <div class="page-kicker">WORKSPACE / LIVE CONTROL</div>

    <section class="dashboard-hero">
      <div class="dashboard-hero-copy">
        <p class="eyebrow">RECRUITING INTELLIGENCE</p>
        <h1>FIND.<br /><em>SCORE.</em><br />CONNECT.</h1>
        <p>让人才发现、智能判断与真实沟通自然流动。</p>
      </div>
      <article class="mission-control">
        <div>
          <p class="eyebrow">Active Mission</p>
          <h2>招聘任务控制台</h2>
          <p>任务状态与控制接口暂未接入，当前不会伪造运行结果。</p>
        </div>
        <div class="mission-actions">
          <button type="button" aria-label="暂停任务" disabled>暂停任务</button>
          <button type="button" aria-label="停止任务" disabled>停止任务</button>
        </div>
      </article>
    </section>

    <section class="dashboard-metrics" aria-label="招聘统计">
      <article v-for="label in ['今日发现', '评分达标', '问候成功', '收到简历']" :key="label" class="metric">
        <span>{{ label }}</span>
        <strong class="metric-value">—</strong>
        <small>统计接口暂未提供</small>
      </article>
    </section>

    <section class="dashboard-lower">
      <article class="panel activity-panel">
        <div class="section-heading">
          <div><p class="eyebrow">LIVE ACTIVITY</p><h2>实时任务流</h2></div>
        </div>
        <EmptyState kind="unavailable" title="实时动态暂未接入" description="动态接口暂未提供，当前不会用演示活动替代真实记录。" />
      </article>

      <article class="quota-card">
        <p class="eyebrow">DAILY SHARED QUOTA</p>
        <h2>每日招呼额度</h2>
        <strong>200 次 / 天</strong>
        <p>每位 HR 每日 200 次，全岗位共享。</p>
        <div class="quota-values">
          <span>今日已用 <b>—</b></span>
          <span>今日剩余 <b>—</b></span>
          <span>使用比例 <b>—</b></span>
        </div>
        <small>用量接口暂未接入</small>
      </article>
    </section>

    <article class="panel task-control-boundary">
      <div><p class="eyebrow">TASK CONTROL</p><h2>任务控制</h2></div>
      <p>任务控制接口暂未提供，当前页面不会伪造启动或暂停操作。</p>
    </article>

    <article class="panel agent-panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">AGENTS</p>
          <h2>Agent 设备</h2>
        </div>
        <button type="button" aria-label="刷新 Agent 状态" :disabled="loading" @click="loadRuns">
          {{ loading ? "加载中…" : error ? "重试" : "刷新状态" }}
        </button>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-else-if="loading" aria-live="polite">正在加载 Agent 状态…</p>
      <EmptyState
        v-else-if="runs.length === 0"
        title="暂无 Agent 设备"
        description="Agent 首次上报运行状态后会显示在这里。"
      />
      <div v-else class="agent-list">
        <article v-for="run in runs" :key="run.id" class="agent-card">
          <div>
            <h3>{{ run.machine_id }}</h3>
            <p class="muted">最后心跳：{{ formatHeartbeat(run.last_heartbeat) }}</p>
          </div>
          <StatusBadge :label="statusLabel(run.status)" :tone="statusTone(run.status)" />
          <p v-if="run.last_error" class="error">最近错误：{{ run.last_error }}</p>
        </article>
      </div>
    </article>
  </section>
</template>
