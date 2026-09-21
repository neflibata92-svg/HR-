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
  <section class="page" data-testid="dashboard-page" data-page-panel>
    <header class="page-heading">
      <div>
        <p class="eyebrow">OVERVIEW</p>
        <h1>工作台</h1>
        <p class="muted">查看真实 Agent 设备状态与当前系统能力。</p>
      </div>
    </header>

    <div class="dashboard-grid">
      <article class="panel quota-card">
        <p class="eyebrow">每日招呼额度</p>
        <h2>每位 HR 每日 200 次，全岗位共享</h2>
        <p class="muted">已使用量与剩余量的统计接口暂未提供。</p>
      </article>
      <article class="panel">
        <h2>招聘统计</h2>
        <EmptyState title="统计接口暂未提供" description="接入后将在这里展示真实招聘指标。" />
      </article>
      <article class="panel">
        <h2>实时动态</h2>
        <EmptyState title="动态接口暂未提供" description="当前不会用演示活动替代真实记录。" />
      </article>
      <article class="panel">
        <h2>任务控制</h2>
        <EmptyState title="任务控制接口暂未提供" description="当前页面不会伪造启动或暂停操作。" />
      </article>
    </div>

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
