<template>
  <div class="card">
    <div class="card-header">
      <h2>用户管理</h2>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon>
        <span>新建用户</span>
      </el-button>
    </div>

    <el-table :data="users" v-loading="loading">
      <el-table-column prop="username" label="用户名"></el-table-column>
      <el-table-column prop="is_admin" label="管理员" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_admin ? 'success' : 'info'">{{ row.is_admin ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'">{{ row.is_active ? '已激活' : '已禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间">
         <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-popconfirm
            title="确定要删除此用户吗？"
            confirm-button-text="确定"
            cancel-button-text="取消"
            @confirm="handleDelete(row.id)"
            :disabled="isCurrentUser(row)"
          >
            <template #reference>
              <el-button link type="danger" size="small" :disabled="isCurrentUser(row)">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑用户对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="90%" style="max-width: 450px;" @close="resetForm">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="isEditMode"></el-input>
        </el-form-item>
        <el-form-item label="密码" :prop="isEditMode ? 'password_optional' : 'password'">
          <el-input v-model="form.password" type="password" :placeholder="isEditMode ? '留空则不修改' : ''"></el-input>
        </el-form-item>
        <el-form-item label="管理员" prop="is_admin">
          <el-switch v-model="form.is_admin"></el-switch>
        </el-form-item>
        <el-form-item label="激活状态" prop="is_active">
          <el-switch v-model="form.is_active"></el-switch>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const users = ref([])
const loading = ref(true)
const dialogVisible = ref(false)
const formRef = ref(null)
const currentUser = ref(null)
const form = ref({
  id: null,
  username: '',
  password: '',
  is_admin: false,
  is_active: true
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  password_optional: [] // for edit
}

const isEditMode = computed(() => !!form.value.id)
const dialogTitle = computed(() => isEditMode.value ? '编辑用户' : '新建用户')

const fetchUsers = async () => {
  loading.value = true
  try {
    // 同时获取当前登录用户的信息
    const [usersData, meData] = await Promise.all([api.getUsers(), api.getMe()])
    users.value = usersData
    currentUser.value = meData
  } catch (error) {
    ElMessage.error(`加载用户列表失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

// 检查是否是当前登录的用户，防止自己删除自己
const isCurrentUser = (user) => {
  return currentUser.value && currentUser.value.id === user.id
}

const resetForm = () => {
  form.value = {
    id: null,
    username: '',
    password: '',
    is_admin: false,
    is_active: true
  }
  if(formRef.value) {
    formRef.value.resetFields()
  }
}

const openCreateDialog = () => {
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = (user) => {
  resetForm()
  dialogVisible.value = true
  nextTick(() => {
    form.value = { ...user, password: '' }
  })
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      const userData = { ...form.value }
      if (isEditMode.value && !userData.password) {
        delete userData.password
      }
      
      try {
        if (isEditMode.value) {
          await api.updateUser(userData.id, userData)
          ElMessage.success('用户更新成功')
        } else {
          await api.createUser(userData)
          ElMessage.success('用户创建成功')
        }
        dialogVisible.value = false
        await fetchUsers()
      } catch (error) {
        ElMessage.error(`操作失败: ${error.message}`)
      }
    }
  })
}

const handleDelete = async (userId) => {
  try {
    await api.deleteUser(userId)
    ElMessage.success('用户删除成功')
    await fetchUsers()
  } catch (error) {
    ElMessage.error(`删除失败: ${error.message}`)
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.card-header h2 {
    margin: 0;
}
.el-button--link {
    padding-left: 6px;
    padding-right: 6px;
}
</style>
