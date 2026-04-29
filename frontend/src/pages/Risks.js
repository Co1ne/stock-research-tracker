import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const Risks = {
  components: { EmptyState },
  setup() {
    const risks = ref([])
    const error = ref('')

    async function loadRisks() {
      try {
        const data = await api('/risks')
        risks.value = Array.isArray(data) ? data : []
      } catch (err) {
        error.value = err.message || '风险事件加载失败'
        risks.value = []
      }
    }

    onMounted(loadRisks)
    return { risks, error }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Risk</p><h1>风险事件</h1></div></div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="risks.length === 0" title="暂无风险事件" description="没有风险数据或接口暂时不可用。" />
      <div v-else class="card-list">
        <article v-for="item in risks" :key="item.id" class="data-card">
          <router-link v-if="item.company_id" :to="'/companies/' + item.company_id" class="card-title">{{ item.title || '-' }}</router-link>
          <div v-else class="card-title">{{ item.title || '-' }}</div>
          <p class="muted">{{ item.description || '-' }}</p>
          <div class="summary-row">
            <span>{{ item.level || 'unknown' }}</span><span>{{ item.event_type || '-' }}</span><span>{{ item.source_type || '-' }} #{{ item.source_id || '-' }}</span><span>{{ item.is_resolved ? '已解决' : '未解决' }}</span>
          </div>
        </article>
      </div>
    </section>`
}

export default Risks
