import { ref } from 'vue'
import { api } from '../api/client.js'

export function useCompanies() {
  const companies = ref([])
  const loading = ref(false)
  const error = ref('')

  async function loadCompanies() {
    loading.value = true
    error.value = ''
    try {
      const data = await api('/companies')
      companies.value = Array.isArray(data) ? data : []
    } catch (err) {
      error.value = err.message || '公司列表加载失败'
      companies.value = []
    } finally {
      loading.value = false
    }
  }

  return { companies, loading, error, loadCompanies }
}
