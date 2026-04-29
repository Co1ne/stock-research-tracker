import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const Reports = {
  components: { EmptyState },
  setup() {
    const reports = ref([])
    const message = ref('')
    const error = ref('')

    async function loadReports() {
      try {
        const data = await api('/reports')
        reports.value = Array.isArray(data) ? data : []
      } catch (err) {
        error.value = err.message || '报告列表加载失败'
        reports.value = []
      }
    }

    async function generate() {
      message.value = ''
      error.value = ''
      try {
        const result = await api('/reports/daily', { method: 'POST' })
        message.value = `报告已生成，ID: ${result.report_id}`
        await loadReports()
      } catch (err) {
        error.value = err.message || '报告生成失败'
      }
    }

    onMounted(loadReports)
    return { reports, message, error, generate }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Reports</p><h1>报告中心</h1></div><button @click="generate">生成周报</button></div>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="reports.length === 0" title="暂无报告" description="生成周报后会显示在这里。" />
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>标题</th><th>周期</th><th>类型</th><th>风险</th><th>结论</th></tr></thead>
          <tbody>
            <tr v-for="report in reports" :key="report.id">
              <td>{{ report.title || '-' }}</td><td>{{ report.period || '-' }}</td><td>{{ report.report_type || '-' }}</td><td>{{ report.risk_level || '-' }}</td><td>{{ report.conclusion || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

export default Reports
