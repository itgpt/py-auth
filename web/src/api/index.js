const API_BASE = '/api'


export const SESSION_EXPIRED_MESSAGE = '登录已过期，请重新登录'

let onSessionExpired = null


export function configureSessionExpired(handler) {
  onSessionExpired = handler
}

export function notifySessionExpired() {
  api.setToken(null)
  try {
    localStorage.removeItem('username')
  } catch (_) {
  }
  onSessionExpired?.()
}

export function isSessionExpiredError(err) {
  const m = err?.message
  return typeof m === 'string' && m.includes('登录已过期')
}

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
      notifySessionExpired()
      throw new Error(SESSION_EXPIRED_MESSAGE)
    }

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`
      try {
        const errorData = await response.json()
        errorMessage = errorData.detail || errorData.message || errorMessage
      } catch (e) {
      }
      throw new Error(errorMessage)
    }

    if (response.status === 204) {
      return null
    }
    return response.json()
  }

  
  async login(username, password) {
    
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

  
  async getConfigs() {
    return this.request('/admin/config')
  }

  async updateConfigs(configs) {
    return this.request('/admin/config', {
      method: 'PUT',
      body: JSON.stringify({ configs })
    })
  }

  async getOperationLogs(page = 1, pageSize = 50) {
    return this.request(`/admin/logs?page=${page}&page_size=${pageSize}`)
  }

  async cleanupOperationLogs(days) {
    if (!Number.isInteger(days) || days < 0) {
      throw new Error('days 必须是大于等于 0 的整数')
    }
    return this.request(`/admin/logs?days=${days}`, {
      method: 'DELETE'
    })
  }

  
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
