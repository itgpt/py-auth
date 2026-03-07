import { createRouter, createWebHistory } from 'vue-router'
import AdminPanel from './components/AdminPanel.vue'
import Settings from './views/Settings.vue'
import Users from './views/Users.vue'
import LoginForm from './components/LoginForm.vue'
import AdminLayout from './views/AdminLayout.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginForm,
  },
  {
    path: '/',
    component: AdminLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: AdminPanel,
      },
      {
        path: 'settings',
        name: 'Settings',
        component: Settings,
      },
      {
        path: 'users',
        name: 'Users',
        component: Users,
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
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

export default router
