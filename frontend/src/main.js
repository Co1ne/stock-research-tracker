import { createApp, onMounted, ref, watch } from 'vue'
import { createRouter, createWebHistory, useRoute } from 'vue-router'
import './style.css'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function api(path, options = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  })
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null ? body.detail : body
    throw new Error(detail || `HTTP ${response.status}`)
  }
  return body
}

function useCompanies() {
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

const EmptyState = {
  props: ['title', 'description'],
  template: `<div class="empty-state"><strong>{{ title }}</strong><span>{{ description }}</span></div>`
}

const Dashboard = {
  components: { EmptyState },
  setup() {
    const { companies, loading, error, loadCompanies } = useCompanies()
    const health = ref('checking')
    const summaries = ref([])

    async function load() {
      await Promise.allSettled([
        api('/health').then(() => { health.value = 'ok' }).catch(() => { health.value = 'error' }),
        loadCompanies()
      ])
      const results = await Promise.allSettled(companies.value.slice(0, 6).map((company) => api(`/companies/${company.id}/logic-summary`)))
      summaries.value = results.map((result, index) => ({
        company: companies.value[index],
        summary: result.status === 'fulfilled' ? result.value : null
      })).filter((item) => item.company)
    }

    onMounted(load)
    return { companies, loading, error, health, summaries }
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
        <div class="metric"><span>已加载摘要</span><strong>{{ summaries.filter(item => item.summary).length }}</strong></div>
      </div>
      <EmptyState v-if="!loading && companies.length === 0" title="暂无自选股" description="可在自选股页面新增公司。" />
      <div v-else class="card-list">
        <article v-for="item in summaries" :key="item.company.id" class="data-card">
          <router-link :to="'/companies/' + item.company.id" class="card-title">{{ item.company.code }} - {{ item.company.name }}</router-link>
          <div v-if="item.summary" class="summary-row">
            <span>正面 {{ item.summary.positive_count ?? 0 }}</span>
            <span>负面 {{ item.summary.negative_count ?? 0 }}</span>
            <span>风险 {{ item.summary.risk_count ?? 0 }}</span>
            <span>{{ item.summary.overall_status || 'unknown' }}</span>
          </div>
          <p v-else class="muted">摘要接口暂无数据。</p>
        </article>
      </div>
    </section>`
}

const Companies = {
  components: { EmptyState },
  setup() {
    const { companies, loading, error, loadCompanies } = useCompanies()
    const form = ref({ code: '', name: '' })
    const saving = ref(false)

    async function createCompany() {
      if (!form.value.code.trim() || !form.value.name.trim()) return
      saving.value = true
      error.value = ''
      try {
        await api('/companies', {
          method: 'POST',
          body: JSON.stringify({ code: form.value.code.trim(), name: form.value.name.trim(), market: 'A', status: 'watching' })
        })
        form.value = { code: '', name: '' }
        await loadCompanies()
      } catch (err) {
        error.value = err.message || '新增公司失败'
      } finally {
        saving.value = false
      }
    }

    onMounted(loadCompanies)
    return { companies, loading, error, form, saving, createCompany }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Watchlist</p><h1>自选股</h1></div></div>
      <form class="toolbar" @submit.prevent="createCompany">
        <input v-model="form.code" placeholder="股票代码，如 600519" />
        <input v-model="form.name" placeholder="公司名称" />
        <button type="submit" :disabled="saving">新增</button>
      </form>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="!loading && companies.length === 0" title="暂无公司" description="新增公司后会显示在这里。" />
      <div class="table-wrap" v-else>
        <table>
          <thead><tr><th>代码</th><th>名称</th><th>市场</th><th>状态</th><th></th></tr></thead>
          <tbody>
            <tr v-for="company in companies" :key="company.id">
              <td>{{ company.code }}</td><td>{{ company.name }}</td><td>{{ company.market || '-' }}</td><td>{{ company.status || '-' }}</td>
              <td><router-link :to="'/companies/' + company.id">详情</router-link></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

const CompanyDetail = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const company = ref(null)
    const businessLines = ref([])
    const summary = ref(null)
    const evidence = ref([])
    const loading = ref(false)
    const error = ref('')

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const companies = await api('/companies').catch(() => [])
        company.value = Array.isArray(companies) ? companies.find((item) => String(item.id) === String(route.params.id)) || null : null
        const [summaryResult, evidenceResult, linesResult] = await Promise.allSettled([
          api(`/companies/${route.params.id}/logic-summary`),
          api(`/companies/${route.params.id}/evidence`),
          api(`/companies/${route.params.id}/business-lines`)
        ])
        summary.value = summaryResult.status === 'fulfilled' ? summaryResult.value : null
        evidence.value = evidenceResult.status === 'fulfilled' && Array.isArray(evidenceResult.value) ? evidenceResult.value : []
        businessLines.value = linesResult.status === 'fulfilled' && Array.isArray(linesResult.value) ? linesResult.value : []
      } catch (err) {
        error.value = err.message || '公司详情加载失败'
      } finally {
        loading.value = false
      }
    }

    watch(() => route.params.id, load, { immediate: true })
    return { company, businessLines, summary, evidence, loading, error }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Company</p><h1>{{ company ? company.name : '公司详情' }}</h1></div>
        <router-link to="/companies" class="secondary-link">返回自选股</router-link>
      </div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-if="summary" class="metric-grid">
        <div class="metric"><span>正面</span><strong>{{ summary.positive_count ?? 0 }}</strong></div>
        <div class="metric"><span>负面</span><strong>{{ summary.negative_count ?? 0 }}</strong></div>
        <div class="metric"><span>风险</span><strong>{{ summary.risk_count ?? 0 }}</strong></div>
        <div class="metric"><span>状态</span><strong>{{ summary.overall_status || '-' }}</strong></div>
      </div>
      <EmptyState v-else-if="!loading" title="暂无摘要" description="摘要接口无数据或暂时不可用。" />
      <h2>业务线</h2>
      <EmptyState v-if="businessLines.length === 0" title="暂无业务线" description="可通过 API 增加业务线后查看匹配证据。" />
      <div v-else class="card-list">
        <article v-for="line in businessLines" :key="line.id" class="data-card">
          <div class="card-title">{{ line.name }}</div>
          <p class="muted">{{ line.description || line.role || '-' }}</p>
        </article>
      </div>
      <h2>证据列表</h2>
      <EmptyState v-if="!loading && evidence.length === 0" title="暂无证据" description="数据为空不会阻塞页面渲染。" />
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>标题</th><th>方向</th><th>类型</th><th>置信度</th><th>原因</th></tr></thead>
          <tbody>
            <tr v-for="item in evidence" :key="item.id">
              <td>{{ item.title || '-' }}</td><td>{{ item.direction || '-' }}</td><td>{{ item.evidence_type || '-' }}</td><td>{{ item.confidence || '-' }}</td><td>{{ item.reason || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

const Feed = {
  components: { EmptyState },
  setup() {
    const { companies, loadCompanies } = useCompanies()
    const feed = ref([])
    const form = ref({ company_id: '', title: '', raw_text: '', type: 'news' })
    const message = ref('')
    const error = ref('')

    async function loadFeed() {
      try {
        const data = await api('/feed')
        feed.value = Array.isArray(data) ? data : []
      } catch (err) {
        error.value = err.message || '信息流加载失败'
        feed.value = []
      }
    }

    async function submit() {
      error.value = ''
      message.value = ''
      if (!form.value.company_id || !form.value.title || !form.value.raw_text) return
      const query = new URLSearchParams({ company_id: form.value.company_id, title: form.value.title, raw_text: form.value.raw_text })
      try {
        await api(`/mock/${form.value.type}?${query.toString()}`, { method: 'POST' })
        message.value = '已写入信息流样例数据'
        form.value.title = ''
        form.value.raw_text = ''
        await loadFeed()
      } catch (err) {
        error.value = err.message || '写入失败'
      }
    }

    onMounted(async () => {
      await loadCompanies()
      await loadFeed()
    })
    return { companies, feed, form, message, error, submit }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Feed</p><h1>信息流</h1></div></div>
      <form class="panel-form" @submit.prevent="submit">
        <select v-model="form.company_id">
          <option value="">选择公司</option>
          <option v-for="company in companies" :key="company.id" :value="company.id">{{ company.code }} - {{ company.name }}</option>
        </select>
        <select v-model="form.type"><option value="news">新闻</option><option value="announcement">公告</option></select>
        <input v-model="form.title" placeholder="标题" />
        <textarea v-model="form.raw_text" placeholder="正文"></textarea>
        <button type="submit">写入样例</button>
      </form>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="feed.length === 0" title="暂无信息流" description="写入新闻或公告样例后会显示在这里。" />
      <div v-else class="card-list">
        <article v-for="item in feed" :key="item.source_type + '-' + item.id" class="data-card">
          <div class="card-title">{{ item.title || '-' }}</div>
          <div class="summary-row">
            <span>{{ item.source_type }}</span><span>{{ item.category || 'uncategorized' }}</span><span>重要性 {{ item.importance_score ?? 0 }}</span>
            <span v-if="item.is_risk_event">风险</span><span v-if="item.logic_impact">{{ item.logic_impact }}</span>
          </div>
        </article>
      </div>
    </section>`
}

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

const NotFound = {
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">404</p><h1>页面不存在</h1></div></div>
      <router-link to="/">返回 Dashboard</router-link>
    </section>`
}

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/companies', name: 'Companies', component: Companies },
  { path: '/companies/:id', name: 'CompanyDetail', component: CompanyDetail },
  { path: '/feed', name: 'Feed', component: Feed },
  { path: '/risks', name: 'Risks', component: Risks },
  { path: '/reports', name: 'Reports', component: Reports },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound }
]

const router = createRouter({ history: createWebHistory(), routes })

const App = {
  setup() {
    return {
      navItems: [
        { to: '/', label: 'Dashboard' },
        { to: '/companies', label: '自选股' },
        { to: '/feed', label: '信息流' },
        { to: '/risks', label: '风险事件' },
        { to: '/reports', label: '报告中心' }
      ]
    }
  },
  template: `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand">Stock Research</div>
        <nav><router-link v-for="item in navItems" :key="item.to" :to="item.to">{{ item.label }}</router-link></nav>
      </aside>
      <main class="main-content"><router-view /></main>
    </div>`
}

createApp(App).use(router).mount('#app')
