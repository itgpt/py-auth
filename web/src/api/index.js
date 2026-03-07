const API_BASE = '/api'

class ApiService {
  constructor() {
    this.token = localStorage.getItem('authToken')
  }

  setToken(token) {
    this.token = token
    if (token) {
      localStorage.setItem('authToken', token)
    } else {
      localStorage.removeItem('authToken')
    }
  }

  getToken() {
    return this.token
  }

  async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    }

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    }

    const response = await fetch(url, {
      ...options,
      headers
    })

    if (response.status === 401) {
      this.setToken(null)
      throw new Error('登录已过期，请重新登录')
    }

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`
      try {
        const errorData = await response.json()
        errorMessage = errorData.detail || errorData.message || errorMessage
      } catch (e) {
        // ignore
      }
      throw new Error(errorMessage)
    }

    if (response.status === 204) {
      return null
    }
    return response.json()
  }

  // 用户认证
  async login(username, password) {
    // 登录前清除旧 token，避免发送无效 token 导致 401
    this.setToken(null)
    
    const data = await this.request('/user/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    })
    this.setToken(data.access_token)
    return data
  }

  async verifyToken() {
    try {
      await this.request('/user/verify')
      return true
    } catch (e) {
      return false
    }
  }

  async changePassword(oldPassword, newPassword) {
    return this.request('/user/change-password', {
      method: 'POST',
      body: JSON.stringify({
        old_password: oldPassword,
        new_password: newPassword
      })
    })
  }

  logout() {
    this.setToken(null)
  }

  // 配置管理
  async getConfigs() {
    return this.request('/admin/config')
  }

  async updateConfigs(configs) {
    return this.request('/admin/config', {
      method: 'PUT',
      body: JSON.stringify({ configs })
    })
  }

  // 用户管理
  async getUsers() {
    return this.request('/admin/users')
  }

  async createUser(userData) {
    return this.request('/admin/users', {
      method: 'POST',
      body: JSON.stringify(userData)
    })
  }

  async updateUser(userId, userData) {
    return this.request(`/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData)
    })
  }

  async deleteUser(userId) {
    return this.request(`/admin/users/${userId}`, {
      method: 'DELETE'
    })
  }

  async getMe() {
    return this.request('/user/me')
  }
}

export const api = new ApiService()

