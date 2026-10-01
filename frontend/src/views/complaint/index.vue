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

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
          <td :colspan="columns.length + 1" class="empty-state">暂无市民热线数据，可先登记热线记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条市民热线记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatsPayload = { total: number; by_status: Record<string, number> }

const ENDPOINT = '/api/complaint'
const columns = ["记录编号", "来电人", "来电内容", "问题位置", "问题类型", "转办部门", "处理结果", "记录状态"]
const actions = ["转办部门", "处理反馈", "办结归档"]
const statuses = ["待转办", "已转办", "处理中", "已办结"]
const stats = ref([
  { label: '工单总数', value: 0 },
  { label: '待转办记录', value: 0 },
  { label: '处理中记录', value: 0 },
  { label: '已办结记录', value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '热线记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('市民热线动作未生效，请稍后重试')
    }
    await reload()
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '市民热线操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('热线记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '市民热线列表读取失败'
  }
}

async function reloadStats() {
  try {
    const payload = await fetchJson<StatsPayload>(`${ENDPOINT}/stats`)
    stats.value = [
      { label: '工单总数', value: payload.total },
      { label: '待转办记录', value: payload.by_status['待转办'] ?? 0 },
      { label: '处理中记录', value: payload.by_status['处理中'] ?? 0 },
      { label: '已办结记录', value: payload.by_status['已办结'] ?? 0 },
    ]
  } catch {
    // 列表请求已经把错误写到页脚，这里不再重复提示
  }
}

onMounted(() => {
  void reload()
  void reloadStats()
})
</script>
