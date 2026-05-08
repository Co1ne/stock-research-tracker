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
    const riskBoard = ref(null)
    const ingestionHealth = ref(null)
    const recentResearchNotes = ref([])
    const disciplineChecks = ref([])

    async function load() {
      await Promise.allSettled([
        api('/health').then(() => { health.value = 'ok' }).catch(() => { health.value = 'error' }),
        loadCompanies(),
        api('/dashboard/summary').then((data) => { dashboard.value = data }).catch(() => { dashboard.value = null }),
        api('/dashboard/risk-board').then((data) => { riskBoard.value = data }).catch(() => { riskBoard.value = null }),
        api('/dashboard/ingestion-health').then((data) => { ingestionHealth.value = data }).catch(() => { ingestionHealth.value = null }),
        api('/research-notes?limit=3').then((data) => { recentResearchNotes.value = Array.isArray(data) ? data : [] }).catch(() => { recentResearchNotes.value = [] }),
        api('/discipline-checks?limit=5').then((data) => { disciplineChecks.value = Array.isArray(data) ? data : [] }).catch(() => { disciplineChecks.value = [] })
      ])
      const results = await Promise.allSettled(companies.value.slice(0, 6).map((company) => api(`/companies/${company.id}/logic-summary`)))
      summaries.value = results.map((result, index) => ({
        company: companies.value[index],
        summary: result.status === 'fulfilled' ? result.value : null
      })).filter((item) => item.company)
    }

    function hypothesisStatusLabel(status) {
      return {
        stable: '假设稳定',
        watching: '需要观察',
        risk_rising: '风险上升',
        weakened: '假设削弱',
        unknown: '证据不足'
      }[status] || '证据不足'
    }

    function viewLabel(value) {
      return { bullish: '偏积极', neutral: '中性观察', cautious: '谨慎', negative: '偏负面' }[value] || '中性观察'
    }

    function priorityLabel(value) {
      return { high: '高', medium: '中', low: '低' }[value] || '中'
    }

    function ingestionStatusLabel(status) {
      return { success: '成功', partial_success: '部分成功', failed: '失败', skipped: '跳过' }[status] || status || '-'
    }

    function conclusionLabel(value) {
      return { strengthen: '强化假设', weaken: '削弱假设', watch: '需要观察', neutral: '中性', risk: '风险提示' }[value] || value || '-'
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

    function countText(value) {
      return Number(value || 0) > 0 ? String(value) : '暂无'
    }

    function disciplineResultLabel(value) {
      return { passed: '纪律检查通过', blocked: '存在阻断项' }[value] || value || '-'
    }

    function firstCompanyUrl(rows) {
      const first = Array.isArray(rows) ? rows[0] : null
      return first?.company_id ? `/companies/${first.company_id}` : '/'
    }

    onMounted(load)
    return { companies, loading, error, health, summaries, dashboard, riskBoard, ingestionHealth, recentResearchNotes, disciplineChecks, statusLabel, hypothesisStatusLabel, viewLabel, priorityLabel, ingestionStatusLabel, conclusionLabel, countText, firstCompanyUrl, disciplineResultLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Daily Research Workspace</p><h1>今日研究工作台</h1></div>
        <span class="status" :class="health === 'ok' ? 'ok' : 'warn'">API {{ health }}</span>
      </div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Today Actions</p><h2>今日待办</h2></div>
          <span class="muted">推荐流程：检查采集健康 → 处理待复核证据 → 查看风险公司 → 沉淀研究记录</span>
        </div>
        <div class="action-card-grid">
          <router-link to="/review" class="action-card">
            <span>待复核证据</span>
            <strong>{{ countText(riskBoard?.review?.pending_count ?? dashboard?.manual_review_count) }}</strong>
            <em>确认、驳回或编辑后确认</em>
          </router-link>
          <router-link :to="firstCompanyUrl(riskBoard?.risk_companies)" class="action-card">
            <span>风险上升公司</span>
            <strong>{{ countText(riskBoard?.hypothesis_status?.risk_rising_count) }}</strong>
            <em>优先查看假设验证</em>
          </router-link>
          <router-link :to="firstCompanyUrl(riskBoard?.weakened_companies)" class="action-card">
            <span>假设削弱公司</span>
            <strong>{{ countText(riskBoard?.hypothesis_status?.weakened_count) }}</strong>
            <em>复核负面证据链</em>
          </router-link>
          <router-link to="/ingestion" class="action-card">
            <span>采集失败记录</span>
            <strong>{{ countText(ingestionHealth?.recent_failed_count) }}</strong>
            <em>查看失败原因和来源</em>
          </router-link>
          <router-link :to="firstCompanyUrl(riskBoard?.missing_evidence_companies)" class="action-card">
            <span>高优先级证据不足</span>
            <strong>{{ countText(riskBoard?.missing_evidence_companies?.length) }}</strong>
            <em>补采集或补证据关系</em>
          </router-link>
          <router-link to="/research-notes" class="action-card">
            <span>待沉淀研究记录</span>
            <strong>{{ countText(dashboard?.reviewed_evidence_without_note_count) }}</strong>
            <em>把已确认重要证据写成记录</em>
          </router-link>
          <router-link to="/report-drafts/new" class="action-card">
            <span>生成研究快照</span>
            <strong>入口</strong>
            <em>选择记录和证据生成 Markdown</em>
          </router-link>
          <router-link to="/discipline-checks/new" class="action-card">
            <span>买入前纪律检查</span>
            <strong>{{ countText(disciplineChecks.filter((item) => item.discipline_result === 'blocked').length) }}</strong>
            <em>先填逻辑、证据、风险和仓位纪律</em>
          </router-link>
        </div>
        <div class="mini-list" v-if="recentResearchNotes.length">
          <router-link v-for="note in recentResearchNotes.slice(0, 3)" :key="'today-note-' + note.id" :to="'/research-notes/' + note.id" class="mini-item">
            <strong>最近研究记录：{{ note.company_name || note.stock_code }} - {{ note.title }}</strong>
            <span>{{ conclusionLabel(note.conclusion_direction) }} ｜ 引用 {{ note.evidence_count ?? 0 }} ｜ 未确认 {{ note.unreviewed_evidence_count ?? 0 }}</span>
          </router-link>
        </div>
        <div class="mini-list" v-if="disciplineChecks.length">
          <router-link v-for="item in disciplineChecks.slice(0, 3)" :key="'today-discipline-' + item.id" :to="'/discipline-checks/' + item.id" class="mini-item">
            <strong>纪律检查：{{ item.company_name || item.stock_code }} - {{ item.title }}</strong>
            <span>{{ disciplineResultLabel(item.discipline_result) }} ｜ 阻断项 {{ item.blockers?.length ?? 0 }} ｜ 证据 {{ item.evidence_count ?? 0 }}</span>
          </router-link>
        </div>
      </section>
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
          <div class="logic-header">
            <div class="card-title">待人工复核</div>
            <router-link to="/review" class="secondary-link">进入复核</router-link>
          </div>
          <EmptyState v-if="!dashboard?.pending_reviews?.length" title="暂无待复核" description="风险或不确定证据会进入这里。" />
          <div v-else class="mini-list">
            <router-link v-for="item in dashboard.pending_reviews.slice(0, 5)" :key="'review-' + item.id" to="/review" class="mini-item">
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
      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Risk Board</p><h2>投资假设风险看板</h2></div>
          <router-link to="/review" class="secondary-link">处理复核</router-link>
        </div>
        <div class="metric-grid compact">
          <div class="metric"><span>待复核证据</span><strong>{{ riskBoard?.review?.pending_count ?? 0 }}</strong></div>
          <div class="metric"><span>风险上升</span><strong>{{ riskBoard?.hypothesis_status?.risk_rising_count ?? 0 }}</strong></div>
          <div class="metric"><span>假设削弱</span><strong>{{ riskBoard?.hypothesis_status?.weakened_count ?? 0 }}</strong></div>
          <div class="metric"><span>需要观察</span><strong>{{ riskBoard?.hypothesis_status?.watching_count ?? 0 }}</strong></div>
          <div class="metric"><span>证据不足</span><strong>{{ riskBoard?.hypothesis_status?.unknown_count ?? 0 }}</strong></div>
        </div>
        <div class="logic-columns">
          <div>
            <h3>风险上升公司</h3>
            <EmptyState v-if="!riskBoard?.risk_companies?.length" title="暂无风险上升公司" description="已确认的高强度负面证据会进入这里。" />
            <div v-else class="mini-list">
              <router-link v-for="item in riskBoard.risk_companies" :key="'risk-board-risk-' + item.company_id" :to="'/companies/' + item.company_id" class="mini-item">
                <strong>{{ item.company_name }} {{ item.stock_code }}</strong>
                <span>{{ hypothesisStatusLabel(item.hypothesis_status) }} ｜ {{ viewLabel(item.current_view) }} ｜ 优先级 {{ priorityLabel(item.tracking_priority) }} ｜ 待复核 {{ item.pending_review_count ?? 0 }}</span>
                <span>{{ item.latest_evidence_title || '暂无最新证据' }}</span>
              </router-link>
            </div>
          </div>
          <div>
            <h3>假设削弱公司</h3>
            <EmptyState v-if="!riskBoard?.weakened_companies?.length" title="暂无假设削弱公司" description="多条已确认负面或反驳证据会进入这里。" />
            <div v-else class="mini-list">
              <router-link v-for="item in riskBoard.weakened_companies" :key="'risk-board-weakened-' + item.company_id" :to="'/companies/' + item.company_id" class="mini-item">
                <strong>{{ item.company_name }} {{ item.stock_code }}</strong>
                <span>负面证据 {{ item.negative_evidence_count ?? 0 }} ｜ {{ item.latest_evidence_title || '暂无最新证据' }}</span>
              </router-link>
            </div>
          </div>
        </div>
        <div class="logic-columns">
          <div>
            <h3>需要观察公司</h3>
            <EmptyState v-if="!riskBoard?.watching_companies?.length" title="暂无需要观察公司" description="待复核或观察类证据会进入这里。" />
            <div v-else class="mini-list">
              <router-link v-for="item in riskBoard.watching_companies" :key="'risk-board-watch-' + item.company_id" :to="'/companies/' + item.company_id" class="mini-item">
                <strong>{{ item.company_name }} {{ item.stock_code }}</strong>
                <span>待复核 {{ item.pending_review_count ?? 0 }} ｜ 负面证据 {{ item.negative_evidence_count ?? 0 }}</span>
              </router-link>
            </div>
          </div>
          <div>
            <h3>高优先级但证据不足</h3>
            <EmptyState v-if="!riskBoard?.missing_evidence_companies?.length" title="暂无高优先级证据不足公司" description="高优先级且缺少关联证据的公司会进入这里。" />
            <div v-else class="mini-list">
              <router-link v-for="item in riskBoard.missing_evidence_companies" :key="'risk-board-missing-' + item.company_id" :to="'/companies/' + item.company_id" class="mini-item">
                <strong>{{ item.company_name }} {{ item.stock_code }}</strong>
                <span>{{ hypothesisStatusLabel(item.hypothesis_status) }} ｜ 优先级 {{ priorityLabel(item.tracking_priority) }}</span>
              </router-link>
            </div>
          </div>
        </div>
      </section>
      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Data Sources</p><h2>数据采集健康</h2></div>
          <router-link to="/ingestion" class="secondary-link">查看采集记录</router-link>
        </div>
        <div class="metric-grid compact">
          <div class="metric"><span>最近采集</span><strong>{{ ingestionHealth?.last_run_at ? '已记录' : '暂无' }}</strong></div>
          <div class="metric"><span>成功</span><strong>{{ ingestionHealth?.recent_success_count ?? 0 }}</strong></div>
          <div class="metric"><span>失败</span><strong>{{ ingestionHealth?.recent_failed_count ?? 0 }}</strong></div>
          <div class="metric"><span>部分成功</span><strong>{{ ingestionHealth?.recent_partial_success_count ?? 0 }}</strong></div>
        </div>
        <EmptyState v-if="!ingestionHealth?.sources?.length" title="暂无采集运行记录" description="可进入采集调试页面手动触发公司采集。" />
        <div v-else class="mini-list">
          <router-link v-for="source in ingestionHealth.sources" :key="source.source_name" to="/ingestion" class="mini-item">
            <strong>{{ source.source_name }}：{{ ingestionStatusLabel(source.last_status) }}</strong>
            <span>成功 {{ source.success_count ?? 0 }} ｜ 失败 {{ source.failed_count ?? 0 }} ｜ 最近 {{ source.last_run_at || '-' }}</span>
            <span v-if="source.last_error_message">最近错误：{{ source.last_error_message }}</span>
          </router-link>
        </div>
      </section>
      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Research Notes</p><h2>研究记录</h2></div>
          <router-link to="/research-notes" class="secondary-link">进入研究记录</router-link>
        </div>
        <div class="logic-columns" v-if="dashboard?.reviewed_evidence_without_note?.length">
          <div>
            <h3>已确认但未沉淀的证据</h3>
            <div class="mini-list">
              <router-link v-for="item in dashboard.reviewed_evidence_without_note.slice(0, 4)" :key="'unnoted-evidence-' + item.id" :to="'/research-notes/new?company_id=' + item.company_id + '&hypothesis_id=' + (item.hypothesis_id || '') + '&evidence_id=' + item.id" class="mini-item">
                <strong>{{ item.company_name || item.stock_code }}：{{ item.title }}</strong>
                <span>复核 {{ item.review_status }} ｜ {{ item.evidence_type || '-' }} ｜ 点击创建研究记录</span>
              </router-link>
            </div>
          </div>
          <div>
            <h3>最近研究记录</h3>
            <EmptyState v-if="!recentResearchNotes.length" title="暂无研究记录" description="可从证据详情页创建人工研究记录，引用已复核证据。" />
            <div v-else class="mini-list">
              <router-link v-for="note in recentResearchNotes" :key="'dashboard-note-inline-' + note.id" :to="'/research-notes/' + note.id" class="mini-item">
                <strong>{{ note.company_name || note.stock_code }}：{{ note.title }}</strong>
                <span>{{ conclusionLabel(note.conclusion_direction) }} ｜ 引用 {{ note.evidence_count ?? 0 }} ｜ 未确认 {{ note.unreviewed_evidence_count ?? 0 }}</span>
              </router-link>
            </div>
          </div>
        </div>
        <EmptyState v-if="!recentResearchNotes.length && !dashboard?.reviewed_evidence_without_note?.length" title="暂无研究记录" description="可从证据详情页创建人工研究记录，引用已复核证据。" />
        <div v-else-if="!dashboard?.reviewed_evidence_without_note?.length" class="mini-list">
          <router-link v-for="note in recentResearchNotes" :key="'dashboard-note-' + note.id" :to="'/research-notes/' + note.id" class="mini-item">
            <strong>{{ note.company_name || note.stock_code }}：{{ note.title }}</strong>
            <span>{{ conclusionLabel(note.conclusion_direction) }} ｜ 引用 {{ note.evidence_count ?? 0 }} ｜ 未确认 {{ note.unreviewed_evidence_count ?? 0 }}</span>
            <span>{{ note.summary || '暂无摘要' }}</span>
          </router-link>
        </div>
      </section>
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
