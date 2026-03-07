<template>
  <div class="settings-page">
    <header class="header">
      <div class="header-left">
        <div class="header-icon">
          <el-icon :size="20"><Setting /></el-icon>
        </div>
        <div class="header-title">
          <h1>系统配置</h1>
          <p>管理系统全局设置</p>
        </div>
      </div>
    </header>

    <main class="content">
      <div class="config-card">
        <el-form label-width="180px" label-position="left" v-if="!loading" @submit.prevent="save">
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
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'
import { Refresh, Setting } from '@element-plus/icons-vue'

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
.settings-page {
  min-height: 100vh;
  background: #f5f7fa;
}

.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 12px 20px;
  display: flex;
  justify-content: flex-start;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,0.2);
  border-radius: 8px;
}

.header-title h1 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}

.header-title p {
  font-size: 12px;
  opacity: 0.8;
  margin: 0;
}

.content {
  padding: 16px;
  max-width: 800px;
  margin: 0 auto;
}

.config-card {
  background: white;
  border-radius: 10px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
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
</style>
