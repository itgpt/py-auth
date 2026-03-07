<template>
  <el-container class="admin-layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon :size="24"><Lock /></el-icon>
        <span>授权管理系统</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="menu"
        router
      >
        <el-menu-item index="/">
          <el-icon><Box /></el-icon>
          <span>设备管理</span>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统配置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <span class="page-title">{{ pageTitle }}</span>
        </div>
        <div class="header-right">
          <div class="user-info">
            <el-avatar :size="32">{{ username.charAt(0).toUpperCase() }}</el-avatar>
            <span class="username">{{ username }}</span>
          </div>
          <el-dropdown trigger="click">
            <span class="el-dropdown-link">
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="showChangePassword">修改密码</el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 修改密码弹窗 (全局) -->
    <el-dialog v-model="showPasswordDialog" title="修改密码" width="400px">
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
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword" :loading="changingPassword">确认</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, Box, User, Setting, ArrowDown } from '@element-plus/icons-vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const username = ref(localStorage.getItem('username') || 'Admin')

const activeMenu = computed(() => route.path)
const pageTitle = computed(() => {
  const titles = {
    '/': '设备管理',
    '/users': '用户管理',
    '/settings': '系统配置'
  }
  return titles[route.path] || ''
})

const showPasswordDialog = ref(false)
const changingPassword = ref(false)
const passwordFormRef = ref(null)
const passwordForm = ref({ oldPassword: '', newPassword: '', confirmPassword: '' })

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

const showChangePassword = () => {
  passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
  showPasswordDialog.value = true
}

const handleChangePassword = async () => {
  if (!passwordFormRef.value) return
  try {
    await passwordFormRef.value.validate()
    changingPassword.value = true
    await api.changePassword(passwordForm.value.oldPassword, passwordForm.value.newPassword)
    ElMessage.success('密码修改成功')
    showPasswordDialog.value = false
  } catch (e) {
    ElMessage.error(e.message || '修改失败')
  } finally {
    changingPassword.value = false
  }
}

const handleLogout = () => {
  api.logout()
  localStorage.removeItem('username')
  router.push('/login')
}
</script>

<style scoped>
.admin-layout {
  height: 100vh;
}

.aside {
  background: #001529;
  color: white;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  font-size: 18px;
  font-weight: bold;
  background: #002140;
}

.menu {
  border-right: none;
  background: transparent;
}

.menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.65);
}

.menu :deep(.el-menu-item.is-active) {
  background: #1890ff !important;
  color: white;
}

.menu :deep(.el-menu-item:hover) {
  color: white;
}

.header {
  background: white;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: flex-start;
  align-items: center;
  padding: 0 24px;
  gap: 24px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  font-size: 14px;
  color: #606266;
}

.main {
  background: #f0f2f5;
  padding: 24px;
}
</style>
