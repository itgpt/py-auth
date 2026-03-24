import { createRouter, createWebHistory } from 'vue-router'
import AdminPanel from './components/AdminPanel.vue'
import Settings from './views/Settings.vue'
import Users from './views/Users.vue'
import AuditLogs from './views/AuditLogs.vue'
import Docs from './views/Docs.vue'
import LoginForm from './components/LoginForm.vue'
import AdminLayout from './views/AdminLayout.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    meta: { title: '登录' },
    component: LoginForm,
  },
  {
    path: '/',
    component: AdminLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/devices',
      },
      {
        path: 'devices',
        name: 'Dashboard',
        meta: { title: '设备管理' },
        component: AdminPanel,
      },
      {
        path: 'settings',
        name: 'Settings',
        meta: { title: '系统配置' },
        component: Settings,
      },
      {
        path: 'users',
        name: 'Users',
        meta: { title: '用户管理' },
        component: Users,
      },
      {
        path: 'logs',
        name: 'AuditLogs',
        meta: { title: '审计日志' },
        component: AuditLogs,
      },
      {
        path: 'docs',
        name: 'Docs',
        meta: { title: '使用文档' },
        component: Docs,
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  const isLoggedIn = !!localStorage.getItem('authToken')

  if (to.matched.some(record => record.meta.requiresAuth) && !isLoggedIn) {
    return { name: 'Login' }
  }

  if (to.name === 'Login' && isLoggedIn) {
    return { name: 'Dashboard' }
  }

  return true
})

const appTitle = '授权管理面板'
router.afterEach((to) => {
  const leaf = [...to.matched].reverse().find((r) => r.meta?.title)
  const section = leaf?.meta?.title
  document.title = section ? `${section} · ${appTitle}` : appTitle
})

export default router
