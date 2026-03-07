<template>
  <div class="page-container">
    <main class="page-content">
      <div class="card">
        <div class="card-header">
          <div class="header-meta">
            <h2>审计日志</h2>
            <p>记录后台关键操作行为</p>
          </div>
        </div>

        <div class="table-wrap">
          <el-table :data="logs" v-loading="loading">
            <el-table-column prop="created_at" label="时间" width="170">
              <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="username" label="操作人" width="120" />
            <el-table-column prop="action" label="动作" width="140" />
            <el-table-column prop="target_type" label="对象类型" width="120" />
            <el-table-column prop="target_id" label="对象ID" min-width="180" show-overflow-tooltip />
            <el-table-column prop="detail" label="详情" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">
                <code>{{ formatDetail(row.detail) }}</code>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="pager">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[50, 80, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
            @size-change="fetchLogs"
            @current-change="fetchLogs"
          />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const logs = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

const formatDate = (value) => {
  if (!value) return '-'
  try {
    return new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'medium' })
  } catch {
    return value
  }
}

const formatDetail = (detail) => {
  if (!detail) return '-'
  try {
    return JSON.stringify(detail)
  } catch {
    return String(detail)
  }
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const data = await api.getOperationLogs(currentPage.value, pageSize.value)
    total.value = Number(data?.total || 0)
    logs.value = Array.isArray(data?.logs) ? data.logs : []
  } catch (e) {
    ElMessage.error(e.message || '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchLogs)
</script>

<style scoped>
.header-meta h2 {
  margin: 0;
  font-size: 16px;
  color: var(--color-text-primary);
}

.header-meta p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.table-wrap {
  overflow-x: auto;
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
