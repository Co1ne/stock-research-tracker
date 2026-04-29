import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const Jobs = {
  components: { EmptyState },
  setup() {
    const runs = ref([])
    const error = ref('')

    async function loadRuns() {
      try {
        const data = await api('/jobs/runs')
        runs.value = Array.isArray(data) ? data : []
      } catch (err) {
        error.value = err.message || '任务状态加载失败'
        runs.value = []
      }
    }

    onMounted(loadRuns)
    return { runs, error, loadRuns }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Jobs</p><h1>任务状态</h1></div><button @click="loadRuns">刷新</button></div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="runs.length === 0" title="暂无任务记录" description="手动抓取或定时任务执行后会显示在这里。" />
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>任务</th><th>状态</th><th>开始</th><th>结束</th><th>结果</th><th>错误</th></tr></thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id">
              <td>{{ run.job_name }}</td><td>{{ run.status }}</td><td>{{ run.started_at || '-' }}</td><td>{{ run.finished_at || '-' }}</td><td>{{ run.result_summary || '-' }}</td><td>{{ run.error_message || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

export default Jobs
