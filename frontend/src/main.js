import { createApp, ref, onMounted } from 'vue'

const App = {
  setup() {
    const loading = ref(false)
    const error = ref('')
    const companies = ref([])
    const selectedCompanyId = ref(null)
    const summary = ref(null)
    const evidence = ref([])
    const newCompany = ref({ code: '', name: '' })

    const loadCompanies = async () => {
      const res = await fetch('/api/companies')
      if (!res.ok) throw new Error('加载公司列表失败')
      companies.value = await res.json()
      if (!selectedCompanyId.value && companies.value.length > 0) {
        selectedCompanyId.value = companies.value[0].id
      }
    }

    const loadCompanyData = async () => {
      if (!selectedCompanyId.value) {
        summary.value = null
        evidence.value = []
        return
      }
      const [sRes, eRes] = await Promise.all([
        fetch(`/api/companies/${selectedCompanyId.value}/logic-summary`),
        fetch(`/api/companies/${selectedCompanyId.value}/evidence`)
      ])
      summary.value = sRes.ok ? await sRes.json() : null
      evidence.value = eRes.ok ? await eRes.json() : []
    }

    const load = async () => {
      loading.value = true
      error.value = ''
      try {
        await loadCompanies()
        await loadCompanyData()
      } catch (e) {
        error.value = e.message || '加载失败'
      } finally {
        loading.value = false
      }
    }

    const createCompany = async () => {
      if (!newCompany.value.code || !newCompany.value.name) return
      const res = await fetch('/api/companies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...newCompany.value, market: 'A', status: 'watching' })
      })
      if (!res.ok) {
        error.value = '创建公司失败'
        return
      }
      newCompany.value = { code: '', name: '' }
      await load()
    }

    const analyzeAnnouncement = async () => {
      const id = prompt('输入公告ID')
      if (!id) return
      await fetch(`/api/announcements/${id}/analyze-logic`, { method: 'POST' })
      await loadCompanyData()
    }

    onMounted(load)
    return { loading, error, companies, selectedCompanyId, summary, evidence, newCompany, loadCompanyData, createCompany, analyzeAnnouncement }
  },
  template: `<main style='max-width:1000px;margin:24px auto;font-family:Arial'>
    <h1>投资逻辑验证</h1>

    <div v-if='error' style='color:#b91c1c;margin:8px 0;'>{{error}}</div>
    <div v-if='loading'>加载中...</div>

    <section v-if='!loading && companies.length === 0' style='padding:12px;border:1px solid #ddd;border-radius:8px;'>
      <h3>还没有自选股公司</h3>
      <p>先添加一家公司，页面就不会是空白。</p>
      <input v-model='newCompany.code' placeholder='股票代码，如 600519' style='margin-right:8px;' />
      <input v-model='newCompany.name' placeholder='公司名称，如 贵州茅台' style='margin-right:8px;' />
      <button @click='createCompany'>添加公司</button>
    </section>

    <section v-if='companies.length > 0'>
      <label>当前公司：</label>
      <select v-model='selectedCompanyId' @change='loadCompanyData'>
        <option v-for='c in companies' :key='c.id' :value='c.id'>{{c.code}} - {{c.name}}</option>
      </select>
      <button @click='analyzeAnnouncement' style='margin-left:8px;'>AI 分析逻辑影响（公告）</button>

      <div v-if='summary' style='margin-top:12px;'>
        <h3>最近30天逻辑状态</h3>
        <p>正面: {{summary.positive_count}} 负面: {{summary.negative_count}} 风险: {{summary.risk_count}} 总体: {{summary.overall_status}}</p>
      </div>

      <h3>证据列表</h3>
      <div v-if='evidence.length === 0' style='color:#666;'>暂无证据数据。可先录入公告/新闻并触发分析。</div>
      <table v-else border='1' cellpadding='6'>
        <tr><th>标题</th><th>方向</th><th>类型</th><th>置信度</th><th>原因</th></tr>
        <tr v-for='e in evidence' :key='e.id'><td>{{e.title}}</td><td>{{e.direction}}</td><td>{{e.evidence_type}}</td><td>{{e.confidence}}</td><td>{{e.reason}}</td></tr>
      </table>
    </section>
  </main>`
}

createApp(App).mount('#app')
