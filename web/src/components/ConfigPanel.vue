<template>
  <div class="config-panel">
    <h2>系统配置</h2>
    <el-form label-width="180px" label-position="left" v-if="!loading">
      <el-form-item label="新设备默认授权">
        <el-switch v-model="configs.default_authorization" />
        <p class="form-item-help">开启后，新设备首次请求会自动授权。</p>
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
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

const loading = ref(false)
const saving = ref(false)
const configs = ref({
  default_authorization: true
})

const loadConfigs = async () => {
  loading.value = true
  try {
    const data = await api.getConfigs()
    if (data && Object.keys(data).length > 0) {
      configs.value = { ...configs.value, ...data }
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
    await api.updateConfigs(configs.value)
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
.config-panel {
  padding: 20px;
}

.config-panel h2 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 20px;
    color: #303133;
}

.form-item-help {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
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
</style>
