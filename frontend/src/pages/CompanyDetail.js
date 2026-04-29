import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const CompanyDetail = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const company = ref(null)
    const businessLines = ref([])
    const summary = ref(null)
    const evidence = ref([])
    const risks = ref([])
    const announcements = ref([])
    const news = ref([])
    const financials = ref([])
    const hypotheses = ref([])
    const loading = ref(false)
    const error = ref('')

    function statusLabel(status) {
      return {
        strengthening: '增强',
        weakening: '削弱',
        strengthened: '增强',
        weakened: '削弱',
        at_risk: '风险上升',
        unverified: '待验证',
        falsified: '已证伪',
        stable: '稳定',
        risk_rising: '风险上升',
        uncertain: '不确定'
      }[status] || '不确定'
    }

    function directionLabel(direction) {
      return {
        positive: '正面',
        negative: '负面',
        neutral: '中性',
        uncertain: '不确定'
      }[direction] || '不确定'
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
        strengthening: '增强',
        weaken: '削弱',
        weakening: '削弱',
        neutral: '中性',
        stable: '稳定',
        uncertain: '不确定',
        risk_rising: '风险'
      }[impact] || '不确定'
    }

    function lineStats(line) {
      return summary.value?.business_lines?.find((item) => item.business_line_id === line.id) || {}
    }

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const companies = await api('/companies').catch(() => [])
        company.value = Array.isArray(companies) ? companies.find((item) => String(item.id) === String(route.params.id)) || null : null
        const [summaryResult, evidenceResult, linesResult, riskResult, announcementResult, newsResult, financialResult, hypothesisResult] = await Promise.allSettled([
          api(`/companies/${route.params.id}/logic-summary`),
          api(`/companies/${route.params.id}/evidence`),
          api(`/companies/${route.params.id}/business-lines`),
          api(`/risks?company_id=${route.params.id}`),
          api(`/announcements?company_id=${route.params.id}`),
          api(`/news?company_id=${route.params.id}`),
          api(`/companies/${route.params.id}/financials`),
          api(`/companies/${route.params.id}/hypotheses`)
        ])
        summary.value = summaryResult.status === 'fulfilled' ? summaryResult.value : null
        evidence.value = evidenceResult.status === 'fulfilled' && Array.isArray(evidenceResult.value) ? evidenceResult.value : []
        businessLines.value = linesResult.status === 'fulfilled' && Array.isArray(linesResult.value) ? linesResult.value : []
        risks.value = riskResult.status === 'fulfilled' && Array.isArray(riskResult.value) ? riskResult.value : []
        announcements.value = announcementResult.status === 'fulfilled' && Array.isArray(announcementResult.value) ? announcementResult.value : []
        news.value = newsResult.status === 'fulfilled' && Array.isArray(newsResult.value) ? newsResult.value : []
        financials.value = financialResult.status === 'fulfilled' && Array.isArray(financialResult.value) ? financialResult.value : []
        hypotheses.value = hypothesisResult.status === 'fulfilled' && Array.isArray(hypothesisResult.value) ? hypothesisResult.value : []
      } catch (err) {
        error.value = err.message || '公司详情加载失败'
      } finally {
        loading.value = false
      }
    }

    watch(() => route.params.id, load, { immediate: true })
    return { company, businessLines, summary, evidence, risks, announcements, news, financials, hypotheses, loading, error, statusLabel, directionLabel, analysisLabel, impactLabel, lineStats }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Company</p><h1>{{ company ? company.name : '公司详情' }}</h1></div>
        <router-link to="/companies" class="secondary-link">返回自选股</router-link>
      </div>
      <div v-if="error" class="notice error">{{ error }}</div>

      <section class="logic-panel">
        <div class="logic-header">
          <div>
            <p class="eyebrow">Current Conclusion</p>
            <h2>当前结论摘要</h2>
          </div>
          <span class="status-badge" :class="summary?.overall_status || 'uncertain'">{{ statusLabel(summary?.overall_status) }}</span>
        </div>
        <p class="lead-text">{{ summary?.system_summary || '暂无足够证据形成判断，请先抓取公告、新闻和财务数据。' }}</p>
        <div v-if="summary" class="metric-grid compact">
          <div class="metric"><span>风险证据</span><strong>{{ summary.risk_count ?? 0 }}</strong></div>
          <div class="metric"><span>待复核</span><strong>{{ summary.pending_review_count ?? 0 }}</strong></div>
          <div class="metric"><span>正面证据</span><strong>{{ summary.positive_count ?? 0 }}</strong></div>
          <div class="metric"><span>负面证据</span><strong>{{ summary.negative_count ?? 0 }}</strong></div>
        </div>
        <div class="logic-columns">
          <div>
            <h3>待人工复核</h3>
            <EmptyState v-if="!summary?.review_questions?.length" title="暂无复核问题" description="暂无足够证据形成明确复核问题。" />
            <div v-else class="mini-list">
              <div v-for="question in summary.review_questions.slice(0, 5)" :key="question" class="mini-item">{{ question }}</div>
            </div>
          </div>
          <div>
            <h3>最近重要变化</h3>
            <EmptyState v-if="!summary?.recent_changes?.length" title="暂无重要变化" description="抓取并分析后会显示最新证据。" />
            <div v-else class="mini-list">
              <div v-for="item in summary.recent_changes.slice(0, 5)" :key="'change-' + item.id" class="mini-item">
                <strong>{{ item.title || '-' }}</strong>
                <div class="summary-row"><span>{{ item.evidence_type || '-' }}</span><span>{{ impactLabel(item.impact_direction) }}</span><span>{{ item.review_status || '-' }}</span></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="logic-panel">
        <div class="logic-header">
          <div>
            <p class="eyebrow">Logic Check</p>
            <h2>投资逻辑验证</h2>
          </div>
          <span class="status-badge" :class="summary?.overall_status || 'uncertain'">{{ statusLabel(summary?.overall_status) }}</span>
        </div>
        <div class="thesis-grid">
          <div>
            <span class="field-label">投资逻辑</span>
            <p>{{ company?.thesis || '未填写' }}</p>
          </div>
          <div>
            <span class="field-label">证伪条件</span>
            <p>{{ company?.disproof_conditions || '未填写' }}</p>
          </div>
        </div>
        <div v-if="summary" class="metric-grid compact">
          <div class="metric"><span>正面证据</span><strong>{{ summary.positive_count ?? 0 }}</strong></div>
          <div class="metric"><span>负面证据</span><strong>{{ summary.negative_count ?? 0 }}</strong></div>
          <div class="metric"><span>风险事件</span><strong>{{ risks.length }}</strong></div>
          <div class="metric"><span>不确定</span><strong>{{ summary.uncertain_count ?? 0 }}</strong></div>
        </div>
        <EmptyState v-else-if="!loading" title="暂无逻辑摘要" description="暂无证据或摘要接口暂时不可用。" />
        <div class="logic-columns">
          <div>
            <h3>最新证据</h3>
            <EmptyState v-if="!loading && evidence.length === 0" title="暂无证据" description="写入公告或新闻并分析后会沉淀证据。" />
            <div v-else class="mini-list">
              <div v-for="item in evidence.slice(0, 5)" :key="'logic-evidence-' + item.id" class="mini-item">
                <strong>{{ item.title || '-' }}</strong>
                <div class="summary-row">
                  <span>{{ directionLabel(item.direction) }}</span>
                  <span>{{ item.evidence_type || '-' }}</span>
                  <span>{{ item.confidence || 'low' }}</span>
                </div>
              </div>
            </div>
          </div>
          <div>
            <h3>风险摘要</h3>
            <EmptyState v-if="!loading && risks.length === 0" title="暂无风险事件" description="目前没有规则命中的风险事件。" />
            <div v-else class="mini-list">
              <div v-for="item in risks.slice(0, 5)" :key="'logic-risk-' + item.id" class="mini-item">
                <strong>{{ item.title || '-' }}</strong>
                <div class="summary-row">
                  <span>{{ item.level || 'unknown' }}</span>
                  <span>{{ item.is_resolved ? '已解决' : '未解决' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <h2>投资假设</h2>
      <EmptyState v-if="!loading && hypotheses.length === 0" title="暂无投资假设" description="可通过智能初始化生成，或后续人工补充。" />
      <div v-else class="card-list">
        <article v-for="item in hypotheses" :key="'hypothesis-' + item.id" class="data-card">
          <div class="card-title">{{ item.title }}</div>
          <p class="muted">{{ item.description || '暂无描述' }}</p>
          <div class="summary-row">
            <span>状态 {{ statusLabel(item.status) }}</span><span>正面 {{ item.positive_evidence_count ?? 0 }}</span><span>负面 {{ item.negative_evidence_count ?? 0 }}</span><span>风险 {{ item.risk_evidence_count ?? 0 }}</span>
          </div>
          <p class="muted">最新相关信息：{{ item.latest_evidence_summary || '暂无直接证据' }}</p>
          <div class="mini-list" v-if="item.falsification_conditions?.length">
            <div v-for="condition in item.falsification_conditions.slice(0, 4)" :key="condition" class="mini-item">{{ condition }}</div>
          </div>
        </article>
      </div>
      <h2>业务线</h2>
      <EmptyState v-if="businessLines.length === 0" title="暂无业务线" description="可通过 API 增加业务线后查看匹配证据。" />
      <div v-else class="card-list">
        <article v-for="line in businessLines" :key="line.id" class="data-card">
          <div class="card-title">{{ line.name }}</div>
          <p class="muted">{{ line.description || line.role || '-' }}</p>
          <div class="summary-row">
            <span>公告 {{ lineStats(line).announcement_count ?? 0 }}</span>
            <span>新闻 {{ lineStats(line).news_count ?? 0 }}</span>
            <span>正面 {{ lineStats(line).positive_count ?? 0 }}</span>
            <span>负面 {{ lineStats(line).negative_count ?? 0 }}</span>
            <span>风险 {{ lineStats(line).risk_count ?? 0 }}</span>
            <span>待复核 {{ lineStats(line).pending_review_count ?? 0 }}</span>
          </div>
          <div v-if="lineStats(line).latest_evidence?.length" class="mini-list">
            <div v-for="item in lineStats(line).latest_evidence.slice(0, 3)" :key="'line-evidence-' + item.id" class="mini-item">
              <strong>{{ item.title }}</strong>
              <span>{{ item.summary || item.reason || '暂无摘要' }}</span>
            </div>
          </div>
          <p v-else class="muted">暂无直接证据，当前缺少订单、收入、客户、项目落地等直接材料。</p>
        </article>
      </div>
      <h2>最近公告</h2>
      <EmptyState v-if="!loading && announcements.length === 0" title="暂无公告" description="点击信息流页面的抓取公告后会显示真实公告。" />
      <div v-else class="card-list">
        <article v-for="item in announcements.slice(0, 5)" :key="'announcement-' + item.id" class="data-card">
          <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer" class="card-title">{{ item.title || '-' }}</a>
          <div v-else class="card-title">{{ item.title || '-' }}</div>
          <div class="summary-row"><span>{{ item.source || '-' }}</span><span>{{ item.category || '-' }}</span><span>{{ item.publish_time || '-' }}</span></div>
          <div class="summary-row"><span>状态 {{ analysisLabel(item.analysis_status) }}</span><span>影响 {{ impactLabel(item.impact_direction) }}</span><span>证据 {{ item.generated_evidence_count ?? 0 }} 条</span><span>{{ item.need_review ? '待复核' : '无需复核' }}</span></div>
          <p class="muted">关联：{{ item.related_business_line_names?.join(' / ') || '暂无业务线归因' }}</p>
        </article>
      </div>
      <h2>最近新闻</h2>
      <EmptyState v-if="!loading && news.length === 0" title="暂无新闻" description="点击信息流页面的抓取新闻后会显示相关新闻。" />
      <div v-else class="card-list">
        <article v-for="item in news.slice(0, 5)" :key="'news-' + item.id" class="data-card">
          <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer" class="card-title">{{ item.title || '-' }}</a>
          <div v-else class="card-title">{{ item.title || '-' }}</div>
          <div class="summary-row"><span>{{ item.source || '-' }}</span><span>{{ item.category || '-' }}</span><span>{{ item.publish_time || '-' }}</span></div>
          <div class="summary-row"><span>状态 {{ analysisLabel(item.analysis_status) }}</span><span>影响 {{ impactLabel(item.impact_direction) }}</span><span>证据 {{ item.generated_evidence_count ?? 0 }} 条</span><span>{{ item.need_review ? '待复核' : '无需复核' }}</span></div>
          <p class="muted">关联：{{ item.related_business_line_names?.join(' / ') || '暂无业务线归因' }}</p>
        </article>
      </div>
      <h2>财务快照</h2>
      <EmptyState v-if="!loading && financials.length === 0" title="暂无财务数据" description="点击抓取财务数据后显示，缺失字段会保留为空。" />
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>报告期</th><th>营收</th><th>归母净利</th><th>毛利率</th><th>经营现金流</th><th>ROE</th></tr></thead>
          <tbody>
            <tr v-for="item in financials.slice(0, 8)" :key="item.id">
              <td>{{ item.report_period }}</td><td>{{ item.revenue ?? '暂缺' }}</td><td>{{ item.net_profit ?? '暂缺' }}</td><td>{{ item.gross_margin ?? '暂缺' }}</td><td>{{ item.operating_cash_flow ?? '暂缺' }}</td><td>{{ item.roe ?? '暂缺' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <h2>证据列表</h2>
      <EmptyState v-if="!loading && evidence.length === 0" title="暂无证据" description="数据为空不会阻塞页面渲染。" />
      <div v-else class="table-wrap">
        <table>
          <thead><tr><th>标题</th><th>业务线</th><th>方向</th><th>类型</th><th>复核</th><th>原因</th></tr></thead>
          <tbody>
            <tr v-for="item in evidence" :key="item.id">
              <td>{{ item.title || '-' }}</td><td>{{ item.business_line_name || '未归因' }}</td><td>{{ directionLabel(item.direction) }}</td><td>{{ item.evidence_type || '-' }}</td><td>{{ item.review_status || '-' }}</td><td>{{ item.reason || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

export default CompanyDetail
