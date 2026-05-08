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
    const hypothesis = ref(null)
    const hypothesisForm = ref(emptyHypothesisForm())
    const hypothesisEditing = ref(false)
    const hypothesisMessage = ref('')
    const hypothesisError = ref('')
    const hypothesisEvidence = ref(null)
    const hypothesisEvidenceError = ref('')
    const researchNotes = ref([])
    const relationForms = ref({})
    const editingRelationId = ref(null)
    const hypothesisEvidenceFilters = ref({ hypothesis_relation: '', impact_direction: '', impact_strength: '', affected_aspect: '', review_status: '', source_name: '', source_type: '', has_ingestion_run: '' })
    const loading = ref(false)
    const error = ref('')

    function emptyHypothesisForm() {
      return {
        thesis: '',
        business_lines_text: '[]',
        watch_metrics_text: '',
        positive_evidence_rules_text: '',
        negative_evidence_rules_text: '',
        invalidation_conditions_text: '',
        current_view: 'neutral',
        tracking_priority: 'medium',
        note: ''
      }
    }

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
        positive: '正面',
        weaken: '削弱',
        weakening: '削弱',
        negative: '负面',
        neutral: '中性',
        stable: '稳定',
        uncertain: '不确定',
        risk_rising: '风险'
      }[impact] || '不确定'
    }

    function lineStats(line) {
      return summary.value?.business_lines?.find((item) => item.business_line_id === line.id) || {}
    }

    function listText(value) {
      return Array.isArray(value) ? value.join('\n') : ''
    }

    function linesFromText(value) {
      return String(value || '').split('\n').map((item) => item.replace(/^-+/, '').trim()).filter(Boolean)
    }

    function editHypothesis() {
      const item = hypothesis.value || {}
      hypothesisForm.value = {
        thesis: item.thesis || '',
        business_lines_text: JSON.stringify(item.business_lines || [], null, 2),
        watch_metrics_text: listText(item.watch_metrics),
        positive_evidence_rules_text: listText(item.positive_evidence_rules),
        negative_evidence_rules_text: listText(item.negative_evidence_rules),
        invalidation_conditions_text: listText(item.invalidation_conditions),
        current_view: item.current_view || 'neutral',
        tracking_priority: item.tracking_priority || 'medium',
        note: item.note || ''
      }
      hypothesisError.value = ''
      hypothesisMessage.value = ''
      hypothesisEditing.value = true
    }

    async function saveHypothesis() {
      hypothesisError.value = ''
      hypothesisMessage.value = ''
      let businessLines = []
      try {
        businessLines = JSON.parse(hypothesisForm.value.business_lines_text || '[]')
        if (!Array.isArray(businessLines)) throw new Error('业务线 JSON 必须是数组')
      } catch (err) {
        hypothesisError.value = err.message || '业务线 JSON 格式错误'
        return
      }
      try {
        const result = await api(`/companies/${route.params.id}/hypotheses`, {
          method: 'PUT',
          body: JSON.stringify({
            thesis: hypothesisForm.value.thesis,
            business_lines: businessLines,
            watch_metrics: linesFromText(hypothesisForm.value.watch_metrics_text),
            positive_evidence_rules: linesFromText(hypothesisForm.value.positive_evidence_rules_text),
            negative_evidence_rules: linesFromText(hypothesisForm.value.negative_evidence_rules_text),
            invalidation_conditions: linesFromText(hypothesisForm.value.invalidation_conditions_text),
            current_view: hypothesisForm.value.current_view,
            tracking_priority: hypothesisForm.value.tracking_priority,
            note: hypothesisForm.value.note
          })
        })
        hypothesis.value = result?.hypothesis || null
        hypothesisEditing.value = false
        hypothesisMessage.value = '投资假设已保存。'
      } catch (err) {
        hypothesisError.value = err.message || '投资假设保存失败'
      }
    }

    function viewLabel(value) {
      return {
        bullish: '偏积极',
        neutral: '中性观察',
        cautious: '谨慎',
        negative: '偏负面'
      }[value] || '中性观察'
    }

    function priorityLabel(value) {
      return { high: '高', medium: '中', low: '低' }[value] || '中'
    }

    function hypothesisStatusLabel(value) {
      return {
        stable: '假设稳定',
        watching: '需要观察',
        risk_rising: '风险上升',
        weakened: '假设削弱',
        unknown: '证据不足'
      }[value] || '证据不足'
    }

    function relationLabel(value) {
      return {
        supports: '支持假设',
        contradicts: '反驳假设',
        neutral: '中性相关',
        watch: '需要观察',
        unrelated: '无关'
      }[value] || '需要观察'
    }

    function aspectLabel(value) {
      return {
        revenue: '收入',
        profit: '利润',
        margin: '毛利率',
        cashflow: '现金流',
        order: '订单',
        shareholder: '股东行为',
        valuation: '估值',
        industry: '行业',
        policy: '政策',
        risk: '风险',
        business_line: '业务线',
        other: '其他'
      }[value] || '其他'
    }

    function sourceLabel(name) {
      return { akshare: 'AKShare', local: '本地 fallback' }[name] || name || '未记录来源'
    }

    function ingestionStatusLabel(status) {
      return { success: '采集成功', partial_success: '部分成功', failed: '采集失败', skipped: '跳过' }[status] || '无采集记录'
    }

    function noteTypeLabel(value) {
      return { daily_note: '日常记录', event_review: '事件复盘', hypothesis_update: '假设更新', risk_review: '风险复核', financial_review: '财务复核', manual_note: '手动记录' }[value] || value || '-'
    }

    function conclusionLabel(value) {
      return { strengthen: '强化假设', weaken: '削弱假设', watch: '需要观察', neutral: '中性', risk: '风险提示' }[value] || value || '-'
    }

    function relationForm(item) {
      if (!relationForms.value[item.evidence_id]) {
        relationForms.value[item.evidence_id] = {
          hypothesis_id: item.hypothesis_id || hypothesis.value?.id || null,
          hypothesis_relation: item.hypothesis_relation || 'watch',
          impact_direction: item.impact_direction || item.direction || 'unknown',
          impact_strength: item.impact_strength || 'low',
          affected_aspect: item.affected_aspect || 'other',
          evidence_summary: item.evidence_summary || item.summary || '',
          relation_note: item.relation_note || ''
        }
      }
      return relationForms.value[item.evidence_id]
    }

    function editRelation(item) {
      relationForm(item)
      hypothesisEvidenceError.value = ''
      editingRelationId.value = item.evidence_id
    }

    async function saveRelation(item) {
      hypothesisEvidenceError.value = ''
      const form = relationForm(item)
      try {
        await api(`/evidence/${item.evidence_id}/hypothesis-link`, {
          method: 'PUT',
          body: JSON.stringify(form)
        })
        editingRelationId.value = null
        await loadHypothesisEvidence()
      } catch (err) {
        hypothesisEvidenceError.value = err.message || '证据关系保存失败'
      }
    }

    async function loadHypothesisEvidence() {
      try {
        const query = new URLSearchParams()
        Object.entries(hypothesisEvidenceFilters.value).forEach(([key, value]) => {
          if (value) query.set(key, value)
        })
        const data = await api(`/companies/${route.params.id}/hypothesis-evidence${query.toString() ? `?${query.toString()}` : ''}`)
        hypothesisEvidence.value = data || null
      } catch (err) {
        hypothesisEvidenceError.value = err.message || '假设验证加载失败'
        hypothesisEvidence.value = null
      }
    }

    async function resetHypothesisEvidenceFilters() {
      hypothesisEvidenceFilters.value = { hypothesis_relation: '', impact_direction: '', impact_strength: '', affected_aspect: '', review_status: '', source_name: '', source_type: '', has_ingestion_run: '' }
      await loadHypothesisEvidence()
    }

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const companies = await api('/companies').catch(() => [])
        company.value = Array.isArray(companies) ? companies.find((item) => String(item.id) === String(route.params.id)) || null : null
        const [summaryResult, evidenceResult, linesResult, riskResult, announcementResult, newsResult, financialResult, hypothesisResult, hypothesisEvidenceResult, researchNotesResult] = await Promise.allSettled([
          api(`/companies/${route.params.id}/logic-summary`),
          api(`/companies/${route.params.id}/evidence`),
          api(`/companies/${route.params.id}/business-lines`),
          api(`/risks?company_id=${route.params.id}`),
          api(`/announcements?company_id=${route.params.id}`),
          api(`/news?company_id=${route.params.id}`),
          api(`/companies/${route.params.id}/financials`),
          api(`/companies/${route.params.id}/hypotheses`),
          api(`/companies/${route.params.id}/hypothesis-evidence`),
          api(`/research-notes?company_id=${route.params.id}`)
        ])
        summary.value = summaryResult.status === 'fulfilled' ? summaryResult.value : null
        evidence.value = evidenceResult.status === 'fulfilled' && Array.isArray(evidenceResult.value) ? evidenceResult.value : []
        businessLines.value = linesResult.status === 'fulfilled' && Array.isArray(linesResult.value) ? linesResult.value : []
        risks.value = riskResult.status === 'fulfilled' && Array.isArray(riskResult.value) ? riskResult.value : []
        announcements.value = announcementResult.status === 'fulfilled' && Array.isArray(announcementResult.value) ? announcementResult.value : []
        news.value = newsResult.status === 'fulfilled' && Array.isArray(newsResult.value) ? newsResult.value : []
        financials.value = financialResult.status === 'fulfilled' && Array.isArray(financialResult.value) ? financialResult.value : []
        hypothesis.value = hypothesisResult.status === 'fulfilled' ? hypothesisResult.value?.hypothesis || null : null
        hypothesisEvidence.value = hypothesisEvidenceResult.status === 'fulfilled' ? hypothesisEvidenceResult.value || null : null
        researchNotes.value = researchNotesResult.status === 'fulfilled' && Array.isArray(researchNotesResult.value) ? researchNotesResult.value : []
      } catch (err) {
        error.value = err.message || '公司详情加载失败'
      } finally {
        loading.value = false
      }
    }

    watch(() => route.params.id, load, { immediate: true })
    return { route, company, businessLines, summary, evidence, risks, announcements, news, financials, hypothesis, hypothesisForm, hypothesisEditing, hypothesisMessage, hypothesisError, hypothesisEvidence, hypothesisEvidenceError, researchNotes, relationForms, editingRelationId, hypothesisEvidenceFilters, loading, error, statusLabel, directionLabel, analysisLabel, impactLabel, lineStats, editHypothesis, saveHypothesis, viewLabel, priorityLabel, hypothesisStatusLabel, relationLabel, aspectLabel, sourceLabel, ingestionStatusLabel, noteTypeLabel, conclusionLabel, relationForm, editRelation, saveRelation, loadHypothesisEvidence, resetHypothesisEvidenceFilters }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Company</p><h1>{{ company ? company.name : '公司详情' }}</h1></div>
        <div class="action-row">
          <router-link :to="'/discipline-checks/new?company_id=' + route.params.id" class="secondary-link">买入前纪律检查</router-link>
          <router-link :to="'/report-drafts/new?company_id=' + route.params.id" class="secondary-link">生成研究快照</router-link>
          <router-link to="/companies" class="secondary-link">返回自选股</router-link>
        </div>
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
        <p v-if="summary?.review_status" class="muted">逻辑摘要复核状态：{{ summary.review_status }}<span v-if="summary.review_note"> ｜ {{ summary.review_note }}</span></p>
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
                <div class="summary-row"><span>{{ item.evidence_type || '-' }}</span><span>{{ impactLabel(item.impact_direction) }}</span><span>复核 {{ item.review_status || '-' }}</span></div>
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

      <section class="logic-panel">
        <div class="logic-header">
          <div>
            <p class="eyebrow">Investment Hypothesis</p>
            <h2>投资假设</h2>
          </div>
          <button @click="editHypothesis">{{ hypothesis ? '编辑' : '创建投资假设' }}</button>
        </div>
        <div v-if="hypothesisMessage" class="notice ok">{{ hypothesisMessage }}</div>
        <div v-if="hypothesisError" class="notice error">{{ hypothesisError }}</div>
        <EmptyState v-if="!loading && !hypothesis && !hypothesisEditing" title="暂无投资假设" description="可创建一份结构化假设，用来记录为什么关注这家公司以及后续如何证伪。" />
        <div v-if="hypothesis && !hypothesisEditing">
          <div class="summary-row">
            <span>当前结论 {{ viewLabel(hypothesis.current_view) }}</span>
            <span>跟踪优先级 {{ priorityLabel(hypothesis.tracking_priority) }}</span>
            <span>更新 {{ hypothesis.updated_at || '-' }}</span>
          </div>
          <div class="thesis-grid">
            <div>
              <span class="field-label">核心投资假设</span>
              <p>{{ hypothesis.thesis || '待人工完善' }}</p>
            </div>
            <div>
              <span class="field-label">备注</span>
              <p>{{ hypothesis.note || '暂无备注' }}</p>
            </div>
          </div>
          <div class="logic-columns">
            <div>
              <h3>业务线拆解</h3>
              <div v-if="hypothesis.business_lines?.length" class="mini-list">
                <div v-for="line in hypothesis.business_lines" :key="line.name" class="mini-item">
                  <strong>{{ line.name }}（{{ priorityLabel(line.importance) }}）</strong>
                  <span>{{ line.description || '暂无说明' }}</span>
                </div>
              </div>
              <p v-else class="muted">暂无业务线拆解。</p>
            </div>
            <div>
              <h3>关键观察指标</h3>
              <div class="summary-row"><span v-for="item in hypothesis.watch_metrics || []" :key="item">{{ item }}</span></div>
            </div>
          </div>
          <div class="logic-columns">
            <div>
              <h3>正向证据规则</h3>
              <div class="mini-list"><div v-for="item in hypothesis.positive_evidence_rules || []" :key="item" class="mini-item">{{ item }}</div></div>
            </div>
            <div>
              <h3>反向证据规则</h3>
              <div class="mini-list"><div v-for="item in hypothesis.negative_evidence_rules || []" :key="item" class="mini-item">{{ item }}</div></div>
            </div>
          </div>
          <h3>逻辑失效条件</h3>
          <div class="mini-list"><div v-for="item in hypothesis.invalidation_conditions || []" :key="item" class="mini-item">{{ item }}</div></div>
        </div>
        <form v-if="hypothesisEditing" class="panel-form hypothesis-form" @submit.prevent="saveHypothesis">
          <label><span class="field-label">当前结论</span><select v-model="hypothesisForm.current_view"><option value="bullish">偏积极</option><option value="neutral">中性观察</option><option value="cautious">谨慎</option><option value="negative">偏负面</option></select></label>
          <label><span class="field-label">跟踪优先级</span><select v-model="hypothesisForm.tracking_priority"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
          <label><span class="field-label">核心投资假设</span><textarea v-model="hypothesisForm.thesis" rows="4" placeholder="为什么关注这家公司"></textarea></label>
          <label><span class="field-label">业务线 JSON</span><textarea v-model="hypothesisForm.business_lines_text" rows="8" placeholder='[{"name":"智能座舱","description":"...","keywords":["域控"],"importance":"high","watch_points":["收入增速"]}]'></textarea></label>
          <label><span class="field-label">关键观察指标，每行一项</span><textarea v-model="hypothesisForm.watch_metrics_text" rows="5"></textarea></label>
          <label><span class="field-label">正向证据规则，每行一项</span><textarea v-model="hypothesisForm.positive_evidence_rules_text" rows="5"></textarea></label>
          <label><span class="field-label">反向证据规则，每行一项</span><textarea v-model="hypothesisForm.negative_evidence_rules_text" rows="5"></textarea></label>
          <label><span class="field-label">逻辑失效条件，每行一项</span><textarea v-model="hypothesisForm.invalidation_conditions_text" rows="5"></textarea></label>
          <label><span class="field-label">备注</span><textarea v-model="hypothesisForm.note" rows="3"></textarea></label>
          <div class="action-row">
            <button type="submit">保存投资假设</button>
            <button type="button" class="secondary" @click="hypothesisEditing = false">取消</button>
          </div>
        </form>
      </section>

      <section class="logic-panel">
        <div class="logic-header">
          <div>
            <p class="eyebrow">Hypothesis Evidence</p>
            <h2>假设验证</h2>
          </div>
          <span class="status-badge" :class="hypothesisEvidence?.hypothesis_status || 'unknown'">{{ hypothesisStatusLabel(hypothesisEvidence?.hypothesis_status) }}</span>
        </div>
        <div v-if="hypothesisEvidenceError" class="notice error">{{ hypothesisEvidenceError }}</div>
        <form class="panel-form" @submit.prevent="loadHypothesisEvidence">
          <select v-model="hypothesisEvidenceFilters.hypothesis_relation"><option value="">全部关系</option><option value="supports">支持假设</option><option value="contradicts">反驳假设</option><option value="neutral">中性相关</option><option value="watch">需要观察</option><option value="unrelated">无关</option></select>
          <select v-model="hypothesisEvidenceFilters.impact_direction"><option value="">全部方向</option><option value="positive">正面</option><option value="negative">负面</option><option value="neutral">中性</option><option value="unknown">未知</option></select>
          <select v-model="hypothesisEvidenceFilters.impact_strength"><option value="">全部强度</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select>
          <select v-model="hypothesisEvidenceFilters.affected_aspect"><option value="">全部维度</option><option value="revenue">收入</option><option value="profit">利润</option><option value="margin">毛利率</option><option value="cashflow">现金流</option><option value="order">订单</option><option value="shareholder">股东行为</option><option value="valuation">估值</option><option value="industry">行业</option><option value="policy">政策</option><option value="risk">风险</option><option value="business_line">业务线</option><option value="other">其他</option></select>
          <select v-model="hypothesisEvidenceFilters.review_status"><option value="">全部复核状态</option><option value="pending">待复核</option><option value="approved">已确认</option><option value="rejected">已驳回</option><option value="edited">人工修改</option></select>
          <select v-model="hypothesisEvidenceFilters.source_name"><option value="">全部数据源</option><option value="akshare">AKShare</option><option value="local">本地 fallback</option></select>
          <select v-model="hypothesisEvidenceFilters.source_type"><option value="">全部来源类型</option><option value="announcement">公告</option><option value="news">新闻</option><option value="financial">财务</option><option value="manual">人工</option><option value="ai">AI</option></select>
          <select v-model="hypothesisEvidenceFilters.has_ingestion_run"><option value="">全部采集记录</option><option value="true">有采集记录</option><option value="false">无采集记录</option></select>
          <div class="action-row">
            <button type="submit">筛选证据</button>
            <button type="button" class="secondary" @click="resetHypothesisEvidenceFilters">重置</button>
          </div>
        </form>
        <div class="metric-grid compact" v-if="hypothesisEvidence?.summary">
          <div class="metric"><span>支持</span><strong>{{ hypothesisEvidence.summary.supports_count ?? 0 }}</strong></div>
          <div class="metric"><span>反驳</span><strong>{{ hypothesisEvidence.summary.contradicts_count ?? 0 }}</strong></div>
          <div class="metric"><span>观察</span><strong>{{ hypothesisEvidence.summary.watch_count ?? 0 }}</strong></div>
          <div class="metric"><span>待复核</span><strong>{{ hypothesisEvidence.summary.pending_review_count ?? 0 }}</strong></div>
          <div class="metric"><span>已确认</span><strong>{{ hypothesisEvidence.summary.approved_count ?? 0 }}</strong></div>
          <div class="metric"><span>已驳回</span><strong>{{ hypothesisEvidence.summary.rejected_count ?? 0 }}</strong></div>
        </div>
        <EmptyState v-if="!loading && !hypothesisEvidence?.items?.length" title="当前暂无关联证据" description="可以先从信息流或人工复核项中维护证据关系。" />
        <div v-else class="card-list">
          <article v-for="item in hypothesisEvidence.items" :key="'hypothesis-evidence-' + item.evidence_id" class="data-card review-card">
            <div class="logic-header">
              <div>
                <div class="card-title">{{ item.title || '-' }}</div>
                <div class="summary-row">
                  <span>{{ item.source || '-' }}</span>
                  <span>{{ item.source_date || item.created_at || '-' }}</span>
                  <span>复核 {{ item.review_status || '-' }}</span>
                  <span>{{ relationLabel(item.hypothesis_relation) }}</span>
                  <span>{{ directionLabel(item.impact_direction) }}</span>
                  <span>{{ priorityLabel(item.impact_strength) }}</span>
                  <span>{{ aspectLabel(item.affected_aspect) }}</span>
                </div>
                <div class="summary-row">
                  <span>数据源 {{ sourceLabel(item.source_name) }}</span>
                  <span>来源日期 {{ item.source_date || '-' }}</span>
                  <span>{{ ingestionStatusLabel(item.ingestion_status) }}</span>
                  <router-link v-if="item.ingestion_run_id" :to="'/ingestion?run_id=' + item.ingestion_run_id" class="secondary-link">采集批次 #{{ item.ingestion_run_id }}</router-link>
                  <span v-else>无采集记录</span>
                  <span v-if="item.is_fallback_source">本地来源</span>
                  <span>{{ item.raw_payload_available ? '有原始载荷' : '无原始载荷' }}</span>
                </div>
              </div>
              <div class="action-row">
                <router-link :to="'/evidence/' + item.evidence_id" class="secondary-link">查看详情</router-link>
                <button class="secondary" @click="editRelation(item)">编辑关系</button>
              </div>
            </div>
            <p>{{ item.evidence_summary || item.content || item.summary || '暂无摘要' }}</p>
            <p class="muted">{{ item.relation_note || '暂无关系说明' }}</p>
            <form v-if="editingRelationId === item.evidence_id" class="panel-form hypothesis-form" @submit.prevent="saveRelation(item)">
              <label><span class="field-label">与假设关系</span><select v-model="relationForm(item).hypothesis_relation"><option value="supports">支持假设</option><option value="contradicts">反驳假设</option><option value="neutral">中性相关</option><option value="watch">需要观察</option><option value="unrelated">无关</option></select></label>
              <label><span class="field-label">影响方向</span><select v-model="relationForm(item).impact_direction"><option value="positive">正面</option><option value="negative">负面</option><option value="neutral">中性</option><option value="unknown">未知</option></select></label>
              <label><span class="field-label">影响强度</span><select v-model="relationForm(item).impact_strength"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
              <label><span class="field-label">影响维度</span><select v-model="relationForm(item).affected_aspect"><option value="revenue">收入</option><option value="profit">利润</option><option value="margin">毛利率</option><option value="cashflow">现金流</option><option value="order">订单</option><option value="shareholder">股东行为</option><option value="valuation">估值</option><option value="industry">行业</option><option value="policy">政策</option><option value="risk">风险</option><option value="business_line">业务线</option><option value="other">其他</option></select></label>
              <label><span class="field-label">证据摘要</span><textarea v-model="relationForm(item).evidence_summary" rows="3"></textarea></label>
              <label><span class="field-label">关系说明</span><textarea v-model="relationForm(item).relation_note" rows="3"></textarea></label>
              <div class="action-row">
                <button type="submit">保存关系</button>
                <button type="button" class="secondary" @click="editingRelationId = null">取消</button>
              </div>
            </form>
          </article>
        </div>
      </section>

      <section class="logic-panel">
        <div class="logic-header">
          <div>
            <p class="eyebrow">Research Notes</p>
            <h2>研究记录</h2>
          </div>
          <router-link :to="'/research-notes/new?company_id=' + route.params.id + (hypothesis?.id ? '&hypothesis_id=' + hypothesis.id : '')" class="secondary-link">新增研究记录</router-link>
        </div>
        <EmptyState v-if="!loading && researchNotes.length === 0" title="暂无研究记录" description="看完证据后，可在这里沉淀人工阶段性判断和引用证据链。" />
        <div v-else class="mini-list">
          <router-link v-for="note in researchNotes.slice(0, 5)" :key="'company-note-' + note.id" :to="'/research-notes/' + note.id" class="mini-item">
            <strong>{{ note.title }}</strong>
            <span>{{ noteTypeLabel(note.note_type) }} ｜ {{ conclusionLabel(note.conclusion_direction) }} ｜ 引用 {{ note.evidence_count ?? 0 }} ｜ 未确认 {{ note.unreviewed_evidence_count ?? 0 }}</span>
            <span>{{ note.summary || '暂无摘要' }}</span>
          </router-link>
        </div>
        <router-link v-if="researchNotes.length > 5" :to="'/research-notes?company_id=' + route.params.id" class="secondary-link">查看全部研究记录</router-link>
      </section>

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
              <td>{{ item.title || '-' }}</td><td>{{ item.business_line_name || '未归因' }}</td><td>{{ directionLabel(item.direction) }}</td><td>{{ item.evidence_type || '-' }}</td><td>{{ item.review_status || '-' }}<span v-if="item.review_note">：{{ item.review_note }}</span></td><td>{{ item.edited_content || item.reason || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

export default CompanyDetail
