import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import { useCompanies } from '../composables/useCompanies.js'
import EmptyState from '../components/EmptyState.js'

const Feed = {
  components: { EmptyState },
  setup() {
    const { companies, loadCompanies } = useCompanies()
    const feed = ref([])
    const filters = ref({ company_id: '', source_type: '', category: '', min_importance: '', is_risk: '', need_manual_review: '', logic_impact: '' })
    const message = ref('')
    const error = ref('')
    const fetching = ref(false)

    async function loadFeed() {
      try {
        const query = new URLSearchParams()
        Object.entries(filters.value).forEach(([key, value]) => {
          if (value !== '') query.set(key, value)
        })
        const data = await api(`/feed${query.toString() ? `?${query.toString()}` : ''}`)
        feed.value = Array.isArray(data) ? data : []
      } catch (err) {
        error.value = err.message || '信息流加载失败'
        feed.value = []
      }
    }

    async function fetchData(kind) {
      error.value = ''
      message.value = ''
      fetching.value = true
      try {
        const query = new URLSearchParams()
        if (filters.value.company_id) query.set('company_id', filters.value.company_id)
        const path = kind === 'announcement' ? '/fetch/announcements' : kind === 'financial' ? '/fetch/financials' : '/fetch/news'
        const result = await api(`${path}${query.toString() ? `?${query.toString()}` : ''}`, { method: 'POST' })
        message.value = `${kind === 'announcement' ? '公告' : kind === 'financial' ? '财务' : '新闻'}抓取完成，新增/更新 ${result.inserted ?? result.upserted ?? 0} 条`
        await loadFeed()
      } catch (err) {
        error.value = err.message || '抓取失败'
      } finally {
        fetching.value = false
      }
    }

    async function analyzePending() {
      error.value = ''
      message.value = ''
      try {
        const result = await api('/logic-analysis/run-pending?limit=20', { method: 'POST' })
        message.value = `AI 分析完成：公告 ${result.announcements} 条，新闻 ${result.news} 条`
        await loadFeed()
      } catch (err) {
        error.value = err.message || 'AI 分析失败'
      }
    }

    function analysisLabel(status) {
      return {
        unprocessed: '未处理',
        processed: '已分析',
        failed: '分析失败',
        pending_review: '待复核'
      }[status] || '未处理'
    }

    function impactLabel(impact) {
      return {
        strengthen: '增强',
        weaken: '削弱',
        neutral: '中性',
        uncertain: '不确定'
      }[impact] || '不确定'
    }

    onMounted(async () => {
      await loadCompanies()
      await loadFeed()
    })
    return { companies, feed, filters, message, error, fetching, loadFeed, fetchData, analyzePending, analysisLabel, impactLabel }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Feed</p><h1>信息流</h1></div></div>
      <div class="action-row">
        <button @click="fetchData('announcement')" :disabled="fetching">抓取公告</button>
        <button @click="fetchData('news')" :disabled="fetching">抓取新闻</button>
        <button @click="fetchData('financial')" :disabled="fetching">抓取财务</button>
        <button @click="analyzePending">批量 AI 分析</button>
      </div>
      <form class="panel-form" @submit.prevent="loadFeed">
        <select v-model="filters.company_id"><option value="">全部公司</option><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.code }} - {{ company.name }}</option></select>
        <select v-model="filters.source_type"><option value="">公告+新闻</option><option value="announcement">公告</option><option value="news">新闻</option></select>
        <input v-model="filters.category" placeholder="分类" />
        <select v-model="filters.min_importance"><option value="">全部重要性</option><option value="4">重要性 ≥ 4</option><option value="5">重要性 = 5</option></select>
        <select v-model="filters.is_risk"><option value="">全部风险</option><option value="true">仅风险</option><option value="false">非风险</option></select>
        <select v-model="filters.need_manual_review"><option value="">全部复核</option><option value="true">需人工复核</option><option value="false">无需复核</option></select>
        <select v-model="filters.logic_impact"><option value="">全部逻辑影响</option><option value="strengthen">增强</option><option value="weaken">削弱</option><option value="neutral">中性</option><option value="uncertain">不确定</option></select>
        <button type="submit">筛选</button>
      </form>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="feed.length === 0" title="暂无信息流" description="点击抓取公告或抓取新闻后，真实数据会进入这里。" />
      <div v-else class="card-list">
        <article v-for="item in feed" :key="item.source_type + '-' + item.id" class="data-card">
          <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer" class="card-title">{{ item.title || '-' }}</a>
          <div v-else class="card-title">{{ item.title || '-' }}</div>
          <div class="summary-row">
            <span>{{ item.source_type === 'announcement' ? '公告' : '新闻' }}</span><span>{{ item.company_name || '-' }}</span><span>{{ item.source || '-' }}</span><span>{{ item.category || 'uncategorized' }}</span><span>重要性 {{ item.importance_score ?? 0 }}</span>
            <span v-if="item.is_risk_event">风险</span><span v-if="item.is_business_update">业务更新</span><span v-if="item.need_review">需复核</span>
          </div>
          <div class="summary-row">
            <span>状态 {{ analysisLabel(item.analysis_status) }}</span><span>影响 {{ impactLabel(item.impact_direction) }}</span><span>证据 {{ item.generated_evidence_count ?? 0 }} 条</span><span>{{ item.ai_analyzed ? '已 AI 分析' : '待 AI' }}</span>
          </div>
          <p class="muted">关联：{{ item.related_business_line_names?.join(' / ') || '暂无业务线归因' }}</p>
        </article>
      </div>
    </section>`
}

export default Feed
