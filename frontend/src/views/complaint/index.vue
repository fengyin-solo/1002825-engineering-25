<template>
  <section class="page" data-module="complaint">
    <header class="page-head">
      <div>
        <h2>市民热线管理</h2>
        <p class="page-desc">维护热线记录，围绕记录编号、来电人、来电内容、问题位置做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记热线记录</button>
        <button class="btn" type="button" @click="exportRows">导出市民热线清单</button>
      </div>
    </header>

    <div v-if="backendDown" class="backend-banner">
      后端服务没起来：页面上的转办部门与处理结果读不到数据。请先到 backend 目录执行
      <code>make prepare</code> 完成预检与示例数据导入，再运行 <code>make backend</code> 起服务。
    </div>

    <div class="stat-row">
      <article v-for="item in statsCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>记录编号</span>
        <input v-model="keyword" placeholder="按记录编号检索" />
      </label>
      <label class="filter-item">
        <span>问题类型</span>
        <select v-model="issueType">
          <option value="">全部</option>
          <option v-for="item in issueTypes" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>转办部门</span>
        <select v-model="department">
          <option value="">全部</option>
          <option v-for="item in departments" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ backendDown ? '后端未连接，暂时读不到工单；服务起来后点「查询」刷新' : '暂无市民热线数据，可先登记热线记录' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条市民热线记录（与运营概览页同一口径）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ListStats = {
  total: number
  pending: number
  by_status: Record<string, number>
  rule_version: number
}

const ENDPOINT = '/api/complaint'
const columns = ["记录编号", "来电人", "来电内容", "问题位置", "问题类型", "转办部门", "处理结果", "记录状态"]
const actions = ["转办部门", "处理反馈", "办结归档"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const backendDown = ref(false)
const listStats = ref<ListStats | null>(null)

// 问题类型、转办部门取自后端固定示例数据的同一份选项
const issueTypes = ref<string[]>([])
const departments = ref<string[]>([])

const keyword = ref('')
const issueType = ref('')
const department = ref('')

const statsCards = computed(() => {
  const byStatus = listStats.value?.by_status ?? {}
  return [
    { label: "待转办记录", value: byStatus['待转办'] ?? 0 },
    { label: "处理中记录", value: byStatus['处理中'] ?? 0 },
    { label: "已办结记录", value: byStatus['已办结'] ?? 0 },
  ]
})

function resetFilters() {
  keyword.value = ''
  issueType.value = ''
  department.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '热线记录登记入口尚未接入审批流'
}

async function loadOptions() {
  try {
    const response = await request(`${ENDPOINT}/options`)
    if (!response.ok) return
    const payload = await response.json()
    issueTypes.value = payload.options?.['问题类型'] ?? []
    departments.value = payload.options?.['转办部门'] ?? []
  } catch {
    // 选项拉不到不阻塞列表，reload 会统一提示后端没起来
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('市民热线动作未生效，请稍后重试')
    }
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '市民热线动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '市民热线操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (issueType.value) query.set('issue_type', issueType.value)
  if (department.value) query.set('department', department.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('热线记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    listStats.value = payload.stats ?? null
    backendDown.value = false
  } catch (error) {
    backendDown.value = true
    rows.value = []
    listStats.value = null
    errorMessage.value = error instanceof Error ? error.message : '市民热线列表读取失败'
  }
}

onMounted(() => {
  void loadOptions()
  void reload()
})
</script>

<style scoped>
.backend-banner {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #f0a8a0;
  border-radius: 8px;
  background: #fef3f2;
  color: #b42318;
  font-size: 13px;
}
.backend-banner code {
  background: #fde7e5;
  border-radius: 4px;
  padding: 1px 5px;
}
.filter-item select {
  min-width: 140px;
}
</style>
