<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <template v-else>
      <div class="stat-row">
        <article v-for="card in cards" :key="card.label" class="stat-card">
          <span class="stat-label">{{ card.label }}</span>
          <strong class="stat-value">{{ card.value }}</strong>
        </article>
      </div>
      <table class="data-table">
        <thead>
          <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in moduleRows" :key="row.name">
            <td>{{ row.name }}</td>
            <td>{{ row.created }}</td>
            <td>{{ row.pending }}</td>
            <td>{{ row.abnormal }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  ready?: boolean
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const errorMessage = ref('')

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    if (payload.ready === false) {
      errorMessage.value = '示例数据核对未通过，联调准备未完成：请执行 make seed 重新导入并核对'
      return
    }
    cards.value = payload.cards
    moduleRows.value = payload.modules
  } catch {
    errorMessage.value = '后端服务未连接：请先起后端（cd backend && ./run.sh），启动前会自动检查端口与数据连通'
  }
})
</script>
