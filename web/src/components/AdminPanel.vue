<template>
  <div class="admin-panel">
    <div class="content">
      <!-- 统计卡片 -->
      <div class="stats">
        <div class="stat-card">
          <div class="stat-icon total"><el-icon :size="24"><Box /></el-icon></div>
          <div class="stat-info">
            <span class="stat-value">{{ total }}</span>
            <span class="stat-label">总设备</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon success"><el-icon :size="24"><CircleCheck /></el-icon></div>
          <div class="stat-info">
            <span class="stat-value">{{ authorizedCount }}</span>
            <span class="stat-label">已授权</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon danger"><el-icon :size="24"><CircleClose /></el-icon></div>
          <div class="stat-info">
            <span class="stat-value">{{ unauthorizedCount }}</span>
            <span class="stat-label">未授权</span>
          </div>
        </div>
      </div>

      <!-- 设备列表 -->
      <div class="device-section">
        <div class="section-header">
          <h2>设备列表</h2>
          <el-button type="primary" size="small" @click="loadDevices" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>

        <!-- 桌面端表格 -->
        <el-table :data="devices" :loading="loading" stripe border class="desktop-table">
          <el-table-column prop="device_id" label="设备ID" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <code class="device-id">{{ row.device_id }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="software_name" label="软件" min-width="100">
            <template #default="{ row }">{{ row.software_name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="device_info" label="详情" width="80" align="center">
            <template #default="{ row }">
              <el-button v-if="row.device_info" type="primary" link size="small" @click="showDeviceInfo(row)">查看</el-button>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row._remarkValue" size="small" placeholder="备注" @blur="saveRemark(row)" @keyup.enter="saveRemark(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="is_authorized" label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.is_authorized ? 'success' : 'danger'" size="small">
                {{ row.is_authorized ? '已授权' : '未授权' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" width="160">
            <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column prop="last_check" label="最后检查" width="160">
            <template #default="{ row }">{{ formatDate(row.last_check) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right" align="center">
            <template #default="{ row }">
              <div class="op-btns">
                <el-button v-if="row.is_authorized" type="warning" size="small" @click="toggleAuth(row, false)" :loading="row._updating">取消授权</el-button>
                <el-button v-else type="success" size="small" @click="toggleAuth(row, true)" :loading="row._updating">授权</el-button>
                <el-button type="danger" size="small" @click="deleteDevice(row)" :loading="row._updating">删除设备</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 移动端卡片 -->
        <div class="mobile-list">
          <div v-if="loading" class="loading-state">
            <el-icon class="is-loading" :size="20"><Refresh /></el-icon>
            <span>加载中...</span>
          </div>
          <div v-else-if="devices.length === 0" class="empty-state">
            <el-empty description="暂无设备" />
          </div>
          <div v-else class="device-cards">
            <div v-for="device in devices" :key="device.device_id" class="device-card">
              <div class="card-header">
                <code class="device-id">{{ device.device_id }}</code>
                <el-tag :type="device.is_authorized ? 'success' : 'danger'" size="small">
                  {{ device.is_authorized ? '已授权' : '未授权' }}
                </el-tag>
              </div>
              <div class="card-body">
                <div class="info-row" v-if="device.software_name">
                  <span class="label">软件：</span>
                  <span class="value">{{ device.software_name }}</span>
                </div>
                <div class="info-row">
                  <span class="label">创建：</span>
                  <span class="value">{{ formatDate(device.created_at) }}</span>
                </div>
                <div class="info-row" v-if="device.updated_at">
                  <span class="label">更新：</span>
                  <span class="value">{{ formatDate(device.updated_at) }}</span>
                </div>
                <div class="info-row" v-if="device.last_check">
                  <span class="label">最后检查：</span>
                  <span class="value">{{ formatDate(device.last_check) }}</span>
                </div>
                <div class="info-row" v-if="device.device_info">
                  <el-button type="primary" link size="small" @click="showDeviceInfo(device)">查看设备详情</el-button>
                </div>
                <div class="info-row">
                  <span class="label">备注：</span>
                  <el-input v-model="device._remarkValue" size="small" placeholder="备注" @blur="saveRemark(device)" />
                </div>
              </div>
              <div class="card-footer">
                <el-button v-if="device.is_authorized" type="warning" size="small" @click="toggleAuth(device, false)" :loading="device._updating">取消授权</el-button>
                <el-button v-else type="success" size="small" @click="toggleAuth(device, true)" :loading="device._updating">授权</el-button>
                <el-button type="danger" size="small" @click="deleteDevice(device)" :loading="device._updating">删除</el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div class="pagination">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[50, 80, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
            @size-change="loadDevices"
            @current-change="loadDevices"
          />
        </div>
      </div>

      <!-- 设备信息弹窗 -->
      <el-dialog v-model="deviceInfoVisible" title="设备详情" width="90%" style="max-width: 500px;">
        <el-descriptions :column="1" border v-if="selectedDevice?.device_info">
          <el-descriptions-item v-for="(value, key) in selectedDevice.device_info" :key="key" :label="key">
            {{ value ?? '-' }}
          </el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="暂无信息" />
      </el-dialog>

      <!-- 修改密码弹窗 -->
      <el-dialog v-model="showChangePasswordDialog" title="修改密码" width="90%" style="max-width: 400px;" @close="resetPasswordForm">
        <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="80px">
          <el-form-item label="旧密码" prop="oldPassword">
            <el-input v-model="passwordForm.oldPassword" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码" prop="newPassword">
            <el-input v-model="passwordForm.newPassword" type="password" show-password />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirmPassword">
            <el-input v-model="passwordForm.confirmPassword" type="password" show-password @keyup.enter="handleChangePassword" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showChangePasswordDialog = false">取消</el-button>
          <el-button type="primary" @click="handleChangePassword" :loading="changingPassword">确认</el-button>
        </template>
      </el-dialog>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { Lock, Refresh, Box, CircleCheck, CircleClose, Key, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { useRouter } from 'vue-router'

const router = useRouter()
const devices = ref([])
const loading = ref(false)
const deviceInfoVisible = ref(false)
const selectedDevice = ref(null)
const showChangePasswordDialog = ref(false)
const changingPassword = ref(false)
const passwordFormRef = ref(null)
const passwordForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' })
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)
let refreshTimer = null

const authorizedCount = computed(() => devices.value.filter(d => d.is_authorized).length)
const unauthorizedCount = computed(() => devices.value.filter(d => !d.is_authorized).length)

const loadDevices = async () => {
  loading.value = true
  try {
    const data = await api.getDevices(currentPage.value, pageSize.value)
    total.value = data.total
    devices.value = data.devices.map(d => ({
      ...d,
      _originalRemark: d.remark || '',
      _remarkValue: d.remark || '',
      _updating: false
    }))
  } catch (e) {
    if (e.message.includes('登录已过期')) {
      api.logout()
      router.push('/login')
    } else {
      ElMessage.error(e.message || '加载失败')
    }
  } finally {
    loading.value = false
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return dateStr
  }
}

const showDeviceInfo = (device) => {
  selectedDevice.value = device
  deviceInfoVisible.value = true
}

const saveRemark = async (device) => {
  if (device._remarkValue === device._originalRemark) return
  try {
    // 只传递备注字段，updated_at 由后端自动处理
    const updatedDevice = await api.updateDevice(device.device_id, { remark: device._remarkValue })
    // 更新本地设备对象，使用后端返回的数据（包括后端设置的 updated_at）
    Object.assign(device, {
      ...updatedDevice,
      _originalRemark: updatedDevice.remark || '',
      _remarkValue: updatedDevice.remark || ''
    })
    ElMessage.success('备注已保存')
  } catch (e) {
    device._remarkValue = device._originalRemark
    ElMessage.error(e.message || '保存失败')
  }
}

const toggleAuth = async (device, authorize) => {
  // 防止重复点击
  if (device._updating) return
  device._updating = true
  try {
    // 只传递授权状态字段，updated_at 由后端自动处理
    const updatedDevice = await api.updateDevice(device.device_id, { is_authorized: authorize })
    // 更新本地设备对象，使用后端返回的数据（包括后端设置的 updated_at）
    Object.assign(device, {
      ...updatedDevice,
      _originalRemark: updatedDevice.remark || '',
      _remarkValue: updatedDevice.remark || ''
    })
    ElMessage.success(authorize ? '已授权' : '已取消授权')
  } catch (e) {
    if (e.message.includes('登录已过期')) {
      api.logout()
      router.push('/login')
    }
    else ElMessage.error(e.message || '操作失败')
  } finally {
    device._updating = false
  }
}

const deleteDevice = async (device) => {
  device._updating = true
  try {
    await api.deleteDevice(device.device_id)
    devices.value = devices.value.filter(d => d.device_id !== device.device_id)
    ElMessage.success('已删除')
  } catch (e) {
    if (e.message.includes('登录已过期')) {
      api.logout()
      router.push('/login')
    }
    else ElMessage.error(e.message || '删除失败')
  } finally {
    device._updating = false
  }
}

const passwordRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [{ required: true, message: '请输入新密码', trigger: 'blur' }, { min: 6, message: '至少6位', trigger: 'blur' }],
  confirmPassword: [{ required: true, message: '请确认密码', trigger: 'blur' }, {
    validator: (_, value, callback) => {
      if (value !== passwordForm.value.newPassword) callback(new Error('密码不一致'))
      else callback()
    }, trigger: 'blur'
  }]
}

const resetPasswordForm = () => {
  passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
  passwordFormRef.value?.clearValidate()
}

const handleChangePassword = async () => {
  if (!passwordFormRef.value) return
  try {
    await passwordFormRef.value.validate()
    if (passwordForm.value.oldPassword === passwordForm.value.newPassword) {
      ElMessage.warning('新密码不能与旧密码相同')
      return
    }
    changingPassword.value = true
    await api.changePassword(passwordForm.value.oldPassword, passwordForm.value.newPassword)
    ElMessage.success('密码修改成功')
    showChangePasswordDialog.value = false
    resetPasswordForm()
  } catch (e) {
    if (e.message?.includes('登录已过期')) {
      api.logout()
      router.push('/login')
    }
    else if (e.message) ElMessage.error(e.message)
  } finally {
    changingPassword.value = false
  }
}

onMounted(() => {
  loadDevices()
  refreshTimer = setInterval(() => { if (!loading.value) loadDevices() }, 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.admin-panel {
  width: 100%;
}

/* Content */
.content {
  max-width: 1400px;
  margin: 0 auto;
}

/* Stats */
.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  background: white;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.stat-icon.total { background: linear-gradient(135deg, #667eea, #764ba2); }
.stat-icon.success { background: linear-gradient(135deg, #56ab2f, #a8e063); }
.stat-icon.danger { background: linear-gradient(135deg, #eb3349, #f45c43); }

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

/* Device Section */
.device-section {
  background: white;
  border-radius: 10px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}

/* Desktop Table */
.desktop-table {
  display: block;
}

.device-id {
  font-family: monospace;
  font-size: 11px;
  color: #606266;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
}

.op-btns {
  display: flex;
  gap: 4px;
}

.op-btns .el-button {
  flex: 1;
  padding: 5px 0;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* Mobile List */
.mobile-list {
  display: none;
}

.loading-state, .empty-state {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.device-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.device-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
}

.card-header .device-id {
  flex: 1;
  word-break: break-all;
  display: block;
  padding: 6px 8px;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.info-row .label {
  color: #909399;
  min-width: 50px;
}

.info-row .value {
  color: #303133;
}

.info-row .el-input {
  flex: 1;
}

.card-footer {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

.card-footer .el-button {
  flex: 1;
}

/* Responsive */
@media (max-width: 768px) {
  .desktop-table {
    display: none !important;
  }
  
  .mobile-list {
    display: block;
  }
  
  .btn-label {
    display: none;
  }
  
  .stats {
    grid-template-columns: repeat(3, 1fr);
  }
  
  .stat-card {
    padding: 12px;
    flex-direction: column;
    text-align: center;
    gap: 8px;
  }
  
  .stat-icon {
    width: 40px;
    height: 40px;
  }
  
  .stat-value {
    font-size: 20px;
  }
}

@media (max-width: 480px) {
  .header {
    padding: 10px 12px;
  }
  
  .header-title h1 {
    font-size: 16px;
  }
  
  .user-info {
    display: none;
  }
  
  .content {
    padding: 12px;
  }
  
  .stats {
    gap: 8px;
  }
  
  .stat-card {
    padding: 10px;
  }
  
  .stat-icon {
    width: 36px;
    height: 36px;
  }
  
  .stat-value {
    font-size: 18px;
  }
  
  .stat-label {
    font-size: 11px;
  }
}
</style>
