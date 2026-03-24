import { ElMessage } from 'element-plus'
import { isSessionExpiredError } from '../api'


export function reportApiError(err, fallbackMessage) {
  if (isSessionExpiredError(err)) return true
  const msg = typeof err?.message === 'string' && err.message ? err.message : fallbackMessage
  ElMessage.error(msg)
  return false
}
