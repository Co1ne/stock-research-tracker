import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const STATUS_LABELS = { draft: '草稿', completed: '已完成', archived: '已归档' }
const RESULT_LABELS = { passed: '纪律检查通过', blocked: '存在阻断项' }

const DisciplineChecks = {
  components: { EmptyState },
  setup() {
    const rows = ref([])
    const companies = ref([])
    const filters = ref({ company_id: '', status: '', discipline_result: '' })
    const loading = ref(false)
    const error = ref('')

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const query = new URLSearchParams()
        Object.entries(filters.value).forEach(([key, value]) => {
          if (value) query.set(key, value)
        })
        const [checkRows, companyRows] = await Promise.all([
          api(`/discipline-checks${query.toString() ? `?${query.toString()}` : ''}`),
          api('/companies').catch(() => [])
        ])
        rows.value = Array.isArray(checkRows) ? checkRows : []
        companies.value = Array.isArray(companyRows) ? companyRows : []
      } catch (err) {
        error.value = err.message || '纪律检查加载失败'
        rows.value = []
      } finally {
        loading.value = false
      }
    }

    function resetFilters() {
      filters.value = { company_id: '', status: '', discipline_result: '' }
      load()
    }

    function statusLabel(value) {
      return STATUS_LABELS[value] || value || '-'
    }

    function resultLabel(value) {
      return RESULT_LABELS[value] || value || '-'
    }

    onMounted(load)
    return { rows, companies, filters, loading, error, load, resetFilters, statusLabel, resultLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Discipline</p><h1>买入前纪律检查</h1></div>
        <router-link to="/discipline-checks/new" class="secondary-link">新建检查单</router-link>
      </div>
      <p class="muted">这里记录的是个人纪律检查，不是系统交易建议。检查单用于确认逻辑、证据、风险和仓位纪律是否完整。</p>
      <div v-if="error" class="notice error">{{ error }}</div>
      <form class="panel-form" @submit.prevent="load">
        <select v-model="filters.company_id">
          <option value="">全部公司</option>
          <option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option>
        </select>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="completed">已完成</option>
          <option value="archived">已归档</option>
        </select>
        <select v-model="filters.discipline_result">
          <option value="">全部结果</option>
          <option value="passed">纪律检查通过</option>
          <option value="blocked">存在阻断项</option>
        </select>
        <div class="action-row">
          <button type="submit">筛选</button>
          <button type="button" class="secondary" @click="resetFilters">重置</button>
        </div>
      </form>
      <div v-if="loading" class="notice">正在加载纪律检查单...</div>
      <EmptyState v-if="!loading && rows.length === 0" title="暂无纪律检查单" description="可以从公司详情页或本页新建一张买入前纪律检查单。" />
      <div v-else class="card-list">
        <article v-for="item in rows" :key="'discipline-' + item.id" class="data-card">
          <div class="logic-header">
            <div>
              <router-link :to="'/discipline-checks/' + item.id" class="card-title">{{ item.title }}</router-link>
              <div class="summary-row">
                <span>{{ item.company_name || item.stock_code || '-' }}</span>
                <span>{{ statusLabel(item.status) }}</span>
                <span>{{ resultLabel(item.discipline_result) }}</span>
                <span>最大计划仓位 {{ item.max_position_pct ?? '-' }}%</span>
              </div>
            </div>
            <router-link :to="'/discipline-checks/' + item.id" class="secondary-link">查看/编辑</router-link>
          </div>
          <div class="summary-row">
            <span>引用证据 {{ item.evidence_count ?? 0 }}</span>
            <span>已确认 {{ item.reviewed_evidence_count ?? 0 }}</span>
            <span>未确认 {{ item.unreviewed_evidence_count ?? 0 }}</span>
            <span>已驳回 {{ item.rejected_evidence_count ?? 0 }}</span>
          </div>
          <div v-if="item.blockers?.length" class="notice error">
            <div v-for="blocker in item.blockers.slice(0, 3)" :key="blocker">{{ blocker }}</div>
          </div>
        </article>
      </div>
    </section>`
}

export default DisciplineChecks
