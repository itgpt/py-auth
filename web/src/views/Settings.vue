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
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'
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
const configs = ref({ ...defaultConfigs })

const loadConfigs = async () => {
  loading.value = true
  try {
    const data = await api.getConfigs()
    if (data && typeof data === 'object') {
      configs.value = { ...defaultConfigs, ...data }
    }
  } catch (e) {
    ElMessage.error(e.message || '加载配置失败')
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
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
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

@media (max-width: 768px) {
  :deep(.el-form-item__label) {
    width: 120px !important;
  }
}
</style>
