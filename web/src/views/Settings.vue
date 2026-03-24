<template>
  <div class="page-container">
    <main class="page-content page-content-narrow">
      <div class="card">
        <div class="config-header">
          <h2>系统配置</h2>
          <p>调整授权系统的全局行为</p>
        </div>

        <el-form label-width="180px" label-position="left" v-if="!loading" @submit.prevent="save">
          <el-form-item v-for="field in configFields" :key="field.key" :label="field.label">
            <el-switch
              v-if="field.type === 'switch'"
              v-model="configs[field.key]"
            />
            <el-input-number
              v-else-if="field.type === 'number'"
              v-model="configs[field.key]"
              :min="field.min"
              :max="field.max"
              :step="field.step || 1"
              controls-position="right"
            />
            <p class="form-item-help">{{ field.help }}</p>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="save" :loading="saving">保存配置</el-button>
          </el-form-item>
        </el-form>
        <div v-else class="loading-state">
          <el-icon class="is-loading" :size="20"><Refresh /></el-icon>
          <span>加载中...</span>
        </div>

        <el-divider />
        <div class="cleanup-header">
          <h3>审计日志清理</h3>
          <p>按天清理历史日志，输入 0 表示全部清空。</p>
        </div>
        <div class="cleanup-actions">
          <el-input-number v-model="cleanupDays" :min="0" :max="3650" controls-position="right" />
          <el-button type="warning" :loading="cleaning" @click="cleanupOldLogs">
            {{ cleanupDays === 0 ? '全部清空日志' : `清空 ${cleanupDays} 天前` }}
          </el-button>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { reportApiError } from '../utils/errorFeedback'
import { Refresh } from '@element-plus/icons-vue'

const configFields = [
  {
    key: 'default_authorization',
    label: '新设备默认授权',
    type: 'switch',
    help: '开启后，新设备首次请求会自动授权。'
  }
]

const defaultConfigs = {
  default_authorization: true
}

const loading = ref(false)
const saving = ref(false)
const cleaning = ref(false)
const cleanupDays = ref(30)
const configs = ref({ ...defaultConfigs })

const loadConfigs = async () => {
  loading.value = true
  try {
    const data = await api.getConfigs()
    if (data && typeof data === 'object') {
      configs.value = { ...defaultConfigs, ...data }
    }
  } catch (e) {
    if (reportApiError(e, '加载配置失败')) return
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    const payload = {}
    for (const field of configFields) {
      payload[field.key] = configs.value[field.key]
    }
    await api.updateConfigs(payload)
    ElMessage.success('配置已保存')
  } catch (e) {
    if (reportApiError(e, '保存失败')) return
  } finally {
    saving.value = false
  }
}

const cleanupOldLogs = async () => {
  const isClearAll = cleanupDays.value === 0
  const confirmMessage = isClearAll
    ? '将清空全部审计日志且不可恢复，是否继续？'
    : `将删除 ${cleanupDays.value} 天前的审计日志，是否继续？`
  const confirmTitle = isClearAll ? '高风险操作确认' : '确认清理'
  const confirmType = isClearAll ? 'error' : 'warning'

  try {
    await ElMessageBox.confirm(
      confirmMessage,
      confirmTitle,
      { type: confirmType }
    )
  } catch {
    return
  }

  cleaning.value = true
  try {
    const result = await api.cleanupOperationLogs(cleanupDays.value)
    ElMessage.success(`已处理 ${result.deleted_count || 0} 条日志`)
  } catch (e) {
    if (reportApiError(e, '操作失败')) return
  } finally {
    cleaning.value = false
  }
}

onMounted(() => {
  loadConfigs()
})
</script>

<style scoped>
.config-header {
  margin-bottom: 16px;
}

.config-header h2 {
  margin: 0;
  font-size: 16px;
  color: var(--color-text-primary);
}

.config-header p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.form-item-help {
  color: #909399;
  font-size: 12px;
  margin: 0;
  line-height: 1.5;
}

.loading-state {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}

.cleanup-header h3 {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-primary);
}

.cleanup-header p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.cleanup-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  :deep(.el-form-item__label) {
    width: 120px !important;
  }

  .cleanup-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .cleanup-actions .el-button {
    width: 100%;
  }
}
</style>
