<template>
  <div class="login-container">
    <div class="login-background">
      <div class="gradient-orb orb-1"></div>
      <div class="gradient-orb orb-2"></div>
      <div class="gradient-orb orb-3"></div>
    </div>
    
    <div class="login-card-wrapper">
      <el-card class="login-card" shadow="always">
        <div class="login-header">
          <div class="logo-icon">
            <el-icon :size="32"><Lock /></el-icon>
          </div>
          <h1 class="login-title">授权管理系统</h1>
          <p class="login-subtitle">设备授权管理平台</p>
        </div>
        
        <el-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          @submit.prevent="handleLogin"
          class="login-form"
          label-position="top"
        >
          <el-form-item label="用户名" prop="username" class="form-item-custom">
            <el-input 
              v-model="formData.username" 
              placeholder="请输入用户名"
              size="large"
              class="custom-input"
            >
              <template #prefix>
                <el-icon class="input-icon"><User /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          
          <el-form-item label="密码" prop="password" class="form-item-custom">
            <el-input 
              v-model="formData.password" 
              type="password"
              placeholder="请输入密码"
              size="large"
              class="custom-input"
              show-password
              @keyup.enter="handleLogin"
            >
              <template #prefix>
                <el-icon class="input-icon"><Lock /></el-icon>
              </template>
            </el-input>
          </el-form-item>
          
          <el-form-item>
            <el-button 
              type="primary" 
              @click="handleLogin"
              size="large"
              :loading="loading"
              class="login-button"
              style="width: 100%"
            >
              <span v-if="!loading">登录</span>
              <span v-else>登录中...</span>
            </el-button>
          </el-form-item>
        </el-form>
        
        <transition name="fade">
          <el-alert
            v-if="error"
            :title="error"
            type="error"
            :closable="true"
            @close="error = ''"
            class="error-message"
            show-icon
          />
        </transition>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const router = useRouter()
const formRef = ref(null)
const formData = ref({
  username: '',
  password: ''
})

const loading = ref(false)
const error = ref('')

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (!formRef.value) return
  
  try {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
    
    loading.value = true
    error.value = ''

    const data = await api.login(formData.value.username, formData.value.password)
    localStorage.setItem('username', data.username)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e) {
    error.value = e.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  min-height: -webkit-fill-available;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  padding-top: max(20px, env(safe-area-inset-top));
  padding-bottom: max(20px, env(safe-area-inset-bottom));
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-background {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  z-index: 0;
}

.gradient-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
  animation: float 20s infinite ease-in-out;
}

.orb-1 {
  width: 400px;
  height: 400px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  top: -200px;
  left: -200px;
  animation-delay: 0s;
}

.orb-2 {
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  bottom: -150px;
  right: -150px;
  animation-delay: 5s;
}

.orb-3 {
  width: 350px;
  height: 350px;
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  top: 50%;
  right: -175px;
  animation-delay: 10s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(30px, -30px) scale(1.1);
  }
  66% {
    transform: translate(-20px, 20px) scale(0.9);
  }
}

.login-card-wrapper {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 440px;
  animation: slideUp 0.6s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-card {
  width: 100%;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
  background: rgba(255, 255, 255, 0.95);
  overflow: hidden;
}

.login-card :deep(.el-card__body) {
  padding: 0;
}

.login-header {
  text-align: center;
  padding: 40px 0 30px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.logo-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  color: white;
  box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
}

.login-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-subtitle {
  color: #8c8c8c;
  font-size: 14px;
  margin: 0;
}

.login-form {
  padding: 30px 40px 40px;
}

.form-item-custom :deep(.el-form-item__label) {
  font-weight: 500;
  color: #262626;
  font-size: 14px;
  padding-bottom: 8px;
}

.custom-input {
  border-radius: 8px;
  transition: all 0.3s;
}

.custom-input :deep(.el-input__wrapper) {
  border-radius: 8px;
  border: 1.5px solid #dcdfe6;
  transition: all 0.3s;
  box-shadow: none;
}

.custom-input :deep(.el-input__wrapper):hover {
  border-color: #667eea;
}

.custom-input :deep(.el-input.is-focus .el-input__wrapper) {
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

.input-icon {
  color: #8c8c8c;
  font-size: 16px;
}

.login-button {
  height: 48px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
  transition: all 0.3s;
  margin-top: 10px;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}

.login-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
}

.login-button:active {
  transform: translateY(0);
  box-shadow: 0 2px 10px rgba(102, 126, 234, 0.3);
}

.error-message {
  margin: 0 40px 30px;
  animation: shake 0.5s;
  border-radius: 8px;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-10px); }
  75% { transform: translateX(10px); }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .login-container {
    padding: 16px;
  }
  
  .login-card-wrapper {
    max-width: 100%;
  }
  
  .login-form {
    padding: 24px 20px 32px;
  }
  
  .error-message {
    margin: 0 20px 24px;
  }
  
  .login-title {
    font-size: 22px;
  }
  
  .login-subtitle {
    font-size: 13px;
  }
  
  .login-header {
    padding: 32px 0 24px;
  }
  
  .logo-icon {
    width: 56px;
    height: 56px;
    margin: 0 auto 16px;
  }
  
  .gradient-orb {
    filter: blur(60px);
  }
  
  .orb-1 {
    width: 300px;
    height: 300px;
  }
  
  .orb-2 {
    width: 250px;
    height: 250px;
  }
  
  .orb-3 {
    width: 280px;
    height: 280px;
  }
}

@media (max-width: 480px) {
  .login-container {
    padding: 12px;
  }
  
  .login-form {
    padding: 20px 16px 28px;
  }
  
  .login-title {
    font-size: 20px;
  }
  
  .login-header {
    padding: 28px 0 20px;
  }
  
  .logo-icon {
    width: 48px;
    height: 48px;
  }
  
  .form-item-custom :deep(.el-form-item__label) {
    font-size: 13px;
  }
}
</style>
