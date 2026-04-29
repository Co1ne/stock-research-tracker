import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import { useCompanies } from '../composables/useCompanies.js'
import EmptyState from '../components/EmptyState.js'

const Dashboard = {
  components: { EmptyState },
  setup() {
    const { companies, loading, error, loadCompanies } = useCompanies()
    const health = ref('checking')
    const summaries = ref([])
    const dashboard = ref(null)

    async function load() {
      await Promise.allSettled([
        api('/health').then(() => { health.value = 'ok' }).catch(() => { health.value = 'error' }),
        loadCompanies(),
        api('/dashboard/summary').then((data) => { dashboard.value = data }).catch(() => { dashboard.value = null })
      ])
      const results = await Promise.allSettled(companies.value.slice(0, 6).map((company) => api(`/companies/${company.id}/logic-summary`)))
      summaries.value = results.map((result, index) => ({
        company: companies.value[index],
        summary: result.status === 'fulfilled' ? result.value : null
      })).filter((item) => item.company)
    }

    function statusLabel(status) {
      return {
        strengthening: '增强',
        weakening: '削弱',
        risk_rising: '风险上升',
        stable: '稳定',
        uncertain: '待观察'
      }[status] || '待观察'
    }

    onMounted(load)
    return { companies, loading, error, health, summaries, dashboard, statusLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Overview</p><h1>Dashboard</h1></div>
        <span class="status" :class="health === 'ok' ? 'ok' : 'warn'">API {{ health }}</span>
      </div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div class="metric-grid">
        <div class="metric"><span>自选公司</span><strong>{{ companies.length }}</strong></div>
        <div class="metric"><span>今日公告</span><strong>{{ dashboard?.today_announcements ?? 0 }}</strong></div>
        <div class="metric"><span>今日新闻</span><strong>{{ dashboard?.today_news ?? 0 }}</strong></div>
        <div class="metric"><span>今日风险</span><strong>{{ dashboard?.today_risks ?? 0 }}</strong></div>
        <div class="metric"><span>今日证据</span><strong>{{ dashboard?.today_evidence ?? 0 }}</strong></div>
        <div class="metric"><span>待 AI 分析</span><strong>{{ dashboard?.pending_ai_count ?? 0 }}</strong></div>
        <div class="metric"><span>待人工复核</span><strong>{{ dashboard?.manual_review_count ?? 0 }}</strong></div>
        <div class="metric"><span>抓取失败公司</span><strong>{{ dashboard?.failed_company_count ?? 0 }}</strong></div>
      </div>
      <div class="logic-columns">
        <section class="data-card">
          <div class="card-title">今日重点</div>
          <EmptyState v-if="!dashboard?.today_focus?.length" title="暂无今日重点" description="可先抓取自选股公告、新闻和财务数据。" />
          <div v-else class="mini-list">
            <router-link v-for="item in dashboard.today_focus.slice(0, 5)" :key="item.company_id + item.title" :to="'/companies/' + item.company_id" class="mini-item">
              <strong>{{ item.company_name || item.stock_code }}：{{ item.title }}</strong>
              <span>{{ item.summary || '需要人工复核其经营影响。' }}</span>
            </router-link>
          </div>
        </section>
        <section class="data-card">
          <div class="card-title">待人工复核</div>
          <EmptyState v-if="!dashboard?.pending_reviews?.length" title="暂无待复核" description="风险或不确定证据会进入这里。" />
          <div v-else class="mini-list">
            <router-link v-for="item in dashboard.pending_reviews.slice(0, 5)" :key="'review-' + item.id" :to="'/companies/' + item.company_id" class="mini-item">
              <strong>{{ item.company_name || item.stock_code }}：{{ item.title }}</strong>
              <span>{{ item.reason || item.summary || '请复核该证据是否影响投资假设。' }}</span>
            </router-link>
          </div>
        </section>
      </div>
      <div class="logic-columns">
        <section class="data-card">
          <div class="card-title">风险上升公司</div>
          <EmptyState v-if="!dashboard?.risk_companies?.length" title="暂无风险上升公司" description="今日没有新增风险证据。" />
          <div v-else class="summary-row"><router-link v-for="item in dashboard.risk_companies" :key="'risk-company-' + item.company_id" :to="'/companies/' + item.company_id">{{ item.company_name }} {{ item.count }} 条</router-link></div>
        </section>
        <section class="data-card">
          <div class="card-title">最新证据</div>
          <EmptyState v-if="!dashboard?.latest_evidence?.length" title="暂无证据" description="风险、业务更新或分析结果会沉淀为证据。" />
          <div v-else class="mini-list">
            <router-link v-for="item in dashboard.latest_evidence.slice(0, 5)" :key="'latest-evidence-' + item.id" :to="'/companies/' + item.company_id" class="mini-item">
              <strong>{{ item.company_name || item.stock_code }}：{{ item.title }}</strong>
              <span>{{ item.evidence_type }} / {{ item.review_status }}</span>
            </router-link>
          </div>
        </section>
      </div>
      <div class="data-card" v-if="dashboard?.latest_runs?.length">
        <div class="card-title">最近抓取状态</div>
        <div class="summary-row">
          <span v-for="run in dashboard.latest_runs.slice(0, 3)" :key="run.id">{{ run.job_name }}: {{ run.status }}</span>
        </div>
      </div>
      <EmptyState v-if="!loading && companies.length === 0" title="暂无自选股" description="可在自选股页面新增公司。" />
      <div v-else class="card-list">
        <article v-for="item in summaries" :key="item.company.id" class="data-card">
          <router-link :to="'/companies/' + item.company.id" class="card-title">{{ item.company.code }} - {{ item.company.name }}</router-link>
          <div v-if="item.summary" class="summary-row">
            <span>正面 {{ item.summary.positive_count ?? 0 }}</span>
            <span>负面 {{ item.summary.negative_count ?? 0 }}</span>
            <span>风险 {{ item.summary.risk_count ?? 0 }}</span>
            <span>{{ statusLabel(item.summary.overall_status) }}</span>
          </div>
          <p v-else class="muted">摘要接口暂无数据。</p>
        </article>
      </div>
    </section>`
}

export default Dashboard
