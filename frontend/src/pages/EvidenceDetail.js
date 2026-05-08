import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const EvidenceDetail = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const detail = ref(null)
    const loading = ref(false)
    const error = ref('')
    const message = ref('')
    const reviewForm = ref({ note: '', edited_content: '' })
    const linkForm = ref(emptyLinkForm())
    const rawLoaded = ref(false)

    function emptyLinkForm() {
      return {
        hypothesis_id: null,
        hypothesis_relation: 'watch',
        impact_direction: 'unknown',
        impact_strength: 'low',
        affected_aspect: 'other',
        evidence_summary: '',
        relation_note: ''
      }
    }

    async function load(includeRaw = false) {
      loading.value = true
      error.value = ''
      try {
        const data = await api(`/evidence/${route.params.id}${includeRaw ? '?include_raw=true' : ''}`)
        detail.value = data
        rawLoaded.value = includeRaw
        reviewForm.value = {
          note: data.review?.review_note || '',
          edited_content: data.review?.edited_content || data.content?.content || ''
        }
        linkForm.value = {
          hypothesis_id: data.hypothesis_link?.hypothesis_id || null,
          hypothesis_relation: data.hypothesis_link?.hypothesis_relation || 'watch',
          impact_direction: data.hypothesis_link?.impact_direction || 'unknown',
          impact_strength: data.hypothesis_link?.impact_strength || 'low',
          affected_aspect: data.hypothesis_link?.affected_aspect || 'other',
          evidence_summary: data.hypothesis_link?.evidence_summary || data.content?.summary || '',
          relation_note: data.hypothesis_link?.relation_note || ''
        }
      } catch (err) {
        error.value = err.message || '证据详情加载失败'
        detail.value = null
      } finally {
        loading.value = false
      }
    }

    async function decide(status) {
      error.value = ''
      message.value = ''
      try {
        await api(`/review/items/${route.params.id}/decision`, {
          method: 'POST',
          body: JSON.stringify({
            status,
            note: reviewForm.value.note,
            edited_content: reviewForm.value.edited_content,
            ...(status === 'rejected' ? {} : linkForm.value)
          })
        })
        message.value = status === 'approved' ? '证据已确认。' : status === 'rejected' ? '证据已驳回。' : '证据已编辑确认。'
        await load(rawLoaded.value)
      } catch (err) {
        error.value = err.message || '复核操作失败'
      }
    }

    async function saveLink() {
      error.value = ''
      message.value = ''
      try {
        await api(`/evidence/${route.params.id}/hypothesis-link`, {
          method: 'PUT',
          body: JSON.stringify(linkForm.value)
        })
        message.value = '假设关系已保存。'
        await load(rawLoaded.value)
      } catch (err) {
        error.value = err.message || '假设关系保存失败'
      }
    }

    async function loadRawPayload() {
      await load(true)
    }

    function reviewLabel(status) {
      return { pending: '待复核', approved: '已确认', rejected: '已驳回', edited: '已编辑确认' }[status] || '待复核'
    }

    function relationLabel(value) {
      return { supports: '支持假设', contradicts: '反驳假设', neutral: '中性相关', watch: '需要观察', unrelated: '无关' }[value] || '需要观察'
    }

    function directionLabel(value) {
      return { positive: '正向', negative: '负向', neutral: '中性', unknown: '未知' }[value] || '未知'
    }

    function statusLabel(value) {
      return { unknown: '证据不足', stable: '假设稳定', watching: '需要观察', risk_rising: '风险上升', weakened: '假设削弱' }[value] || '证据不足'
    }

    function sourceLabel(name) {
      return { akshare: 'AKShare', local: '本地 fallback' }[name] || name || '未记录来源'
    }

    function ingestionStatusLabel(status) {
      return { success: '采集成功', partial_success: '部分成功', failed: '采集失败', skipped: '跳过' }[status] || '无采集记录'
    }

    function priorityLabel(value) {
      return { high: '高', medium: '中', low: '低' }[value] || value || '-'
    }

    function viewLabel(value) {
      return { bullish: '偏积极', neutral: '中性观察', cautious: '谨慎', negative: '偏负面' }[value] || value || '-'
    }

    function pretty(value) {
      if (!value) return '-'
      return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
    }

    function noteTypeLabel(value) {
      return { daily_note: '日常记录', event_review: '事件复盘', hypothesis_update: '假设更新', risk_review: '风险复核', financial_review: '财务复核', manual_note: '手动记录' }[value] || value || '-'
    }

    function conclusionLabel(value) {
      return { strengthen: '强化假设', weaken: '削弱假设', watch: '需要观察', neutral: '中性', risk: '风险提示' }[value] || value || '-'
    }

    watch(() => route.params.id, () => load(false))
    onMounted(() => load(false))

    return { detail, loading, error, message, reviewForm, linkForm, rawLoaded, load, decide, saveLink, loadRawPayload, reviewLabel, relationLabel, directionLabel, statusLabel, sourceLabel, ingestionStatusLabel, priorityLabel, viewLabel, pretty, noteTypeLabel, conclusionLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Evidence</p><h1>证据详情</h1></div>
        <router-link to="/feed" class="secondary-link">返回信息流</router-link>
      </div>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-if="loading" class="notice">正在加载证据详情...</div>
      <EmptyState v-if="!loading && !detail" title="未找到证据" description="该证据不存在，或接口暂时不可用。" />

      <template v-if="detail">
        <section class="logic-panel">
          <div class="logic-header">
            <div><p class="eyebrow">Content</p><h2>证据内容</h2></div>
            <span class="status-badge pending">{{ reviewLabel(detail.review.review_status) }}</span>
          </div>
          <h3>{{ detail.content.title || '-' }}</h3>
          <p>{{ detail.content.summary || detail.content.content || '暂无摘要' }}</p>
          <p class="muted">分类：{{ detail.content.category || '-' }} ｜ 来源日期：{{ detail.content.source_date || '-' }} ｜ 创建：{{ detail.content.created_at || '-' }}</p>
          <p class="muted">更新：{{ detail.content.updated_at || '-' }}</p>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Source Trace</p><h2>来源追踪</h2></div></div>
          <div class="summary-row">
            <span>数据源 {{ sourceLabel(detail.source_trace.source_name) }}</span>
            <span>来源类型 {{ detail.source_trace.source_type || '-' }}</span>
            <span>{{ ingestionStatusLabel(detail.source_trace.ingestion_status) }}</span>
            <span>{{ detail.source_trace.is_fallback_source ? '本地来源' : '外部/历史来源' }}</span>
            <span>{{ detail.source_trace.raw_payload_available ? '有原始载荷' : '无原始载荷' }}</span>
          </div>
          <div class="summary-row">
            <a v-if="detail.source_trace.source_url" :href="detail.source_trace.source_url" target="_blank" rel="noreferrer">打开原始链接</a>
            <router-link v-if="detail.source_trace.ingestion_run_id" :to="'/ingestion?run_id=' + detail.source_trace.ingestion_run_id" class="secondary-link">采集批次 #{{ detail.source_trace.ingestion_run_id }}</router-link>
            <span v-else>无采集记录</span>
            <span>content_hash {{ detail.source_trace.content_hash || '-' }}</span>
          </div>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Review</p><h2>复核状态</h2></div></div>
          <div class="summary-row">
            <span>状态 {{ reviewLabel(detail.review.review_status) }}</span>
            <span>复核人 {{ detail.review.reviewer || '-' }}</span>
            <span>复核时间 {{ detail.review.reviewed_at || '-' }}</span>
          </div>
          <label class="field-label">复核备注</label>
          <textarea v-model="reviewForm.note" rows="2" placeholder="记录确认、驳回或修正原因"></textarea>
          <label class="field-label">编辑后确认内容</label>
          <textarea v-model="reviewForm.edited_content" rows="4" placeholder="需要人工修正时填写"></textarea>
          <div class="action-row">
            <button @click="decide('approved')">确认</button>
            <button class="secondary" @click="decide('rejected')">驳回</button>
            <button class="secondary" @click="decide('edited')">编辑后确认</button>
          </div>
          <div class="code-panel" v-if="detail.review.original_content || detail.review.edited_content">
            <h3>原始/编辑内容</h3>
            <pre>{{ detail.review.original_content || '-' }}</pre>
            <pre>{{ detail.review.edited_content || '-' }}</pre>
          </div>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Hypothesis Link</p><h2>投资假设关系</h2></div></div>
          <form class="panel-form hypothesis-form" @submit.prevent="saveLink">
            <label><span class="field-label">与假设关系</span><select v-model="linkForm.hypothesis_relation"><option value="supports">支持假设</option><option value="contradicts">反驳假设</option><option value="neutral">中性相关</option><option value="watch">需要观察</option><option value="unrelated">无关</option></select></label>
            <label><span class="field-label">影响方向</span><select v-model="linkForm.impact_direction"><option value="positive">正向</option><option value="negative">负向</option><option value="neutral">中性</option><option value="unknown">未知</option></select></label>
            <label><span class="field-label">影响强度</span><select v-model="linkForm.impact_strength"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
            <label><span class="field-label">影响维度</span><select v-model="linkForm.affected_aspect"><option value="revenue">收入</option><option value="profit">利润</option><option value="margin">毛利率</option><option value="cashflow">现金流</option><option value="order">订单</option><option value="shareholder">股东行为</option><option value="valuation">估值</option><option value="industry">行业</option><option value="policy">政策</option><option value="risk">风险</option><option value="business_line">业务线</option><option value="other">其他</option></select></label>
            <label><span class="field-label">证据摘要</span><textarea v-model="linkForm.evidence_summary" rows="3"></textarea></label>
            <label><span class="field-label">关系说明</span><textarea v-model="linkForm.relation_note" rows="3"></textarea></label>
            <div class="action-row"><button type="submit">保存关系</button></div>
          </form>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Hypothesis Context</p><h2>假设上下文</h2></div><span class="status-badge">{{ statusLabel(detail.hypothesis_context.hypothesis_status) }}</span></div>
          <div class="summary-row">
            <span>当前视图 {{ viewLabel(detail.hypothesis_context.current_view) }}</span>
            <span>优先级 {{ priorityLabel(detail.hypothesis_context.tracking_priority) }}</span>
            <span>业务线 {{ detail.hypothesis_context.matched_business_line || '无' }}</span>
          </div>
          <p>{{ detail.hypothesis_context.thesis || '暂无关联投资假设。' }}</p>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Raw Payload</p><h2>原始载荷</h2></div><button v-if="detail.raw_payload.available && !rawLoaded" @click="loadRawPayload">加载原始载荷</button></div>
          <EmptyState v-if="!detail.raw_payload.available" title="暂无原始载荷" description="旧数据或人工证据可能没有保存原始 payload。" />
          <div v-else class="code-panel">
            <h3>预览</h3>
            <pre>{{ detail.raw_payload.preview || '-' }}</pre>
            <template v-if="rawLoaded">
              <h3>完整数据</h3>
              <pre>{{ pretty(detail.raw_payload.data) }}</pre>
            </template>
          </div>
        </section>

        <section class="logic-panel">
          <div class="logic-header">
            <div><p class="eyebrow">Research Notes</p><h2>关联研究记录</h2></div>
            <div class="action-row">
              <router-link :to="'/research-notes/new?company_id=' + (detail.company.id || '') + '&hypothesis_id=' + (detail.hypothesis_link.hypothesis_id || '') + '&evidence_id=' + detail.id" class="secondary-link">基于此证据创建研究记录</router-link>
              <router-link :to="'/report-drafts/new?company_id=' + (detail.company.id || '') + '&hypothesis_id=' + (detail.hypothesis_link.hypothesis_id || '') + '&evidence_id=' + detail.id" class="secondary-link">基于此证据生成快照</router-link>
              <router-link :to="'/discipline-checks/new?company_id=' + (detail.company.id || '')" class="secondary-link">基于公司做纪律检查</router-link>
            </div>
          </div>
          <EmptyState v-if="!detail.related_research_notes?.length" title="暂无研究记录引用" description="可以基于这条证据创建人工研究记录，沉淀阶段性判断。" />
          <div v-else class="mini-list">
            <router-link v-for="note in detail.related_research_notes" :key="'related-note-' + note.id" :to="'/research-notes/' + note.id" class="mini-item">
              <strong>{{ note.title }}</strong>
              <span>{{ noteTypeLabel(note.note_type) }} ｜ {{ conclusionLabel(note.conclusion_direction) }} ｜ {{ note.status || '-' }}</span>
            </router-link>
          </div>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Links</p><h2>相关跳转</h2></div></div>
          <div class="action-row">
            <router-link v-if="detail.links.company_detail" :to="detail.links.company_detail" class="secondary-link">公司详情</router-link>
            <router-link v-if="detail.links.ingestion_detail" :to="detail.links.ingestion_detail" class="secondary-link">采集详情</router-link>
            <router-link to="/feed" class="secondary-link">信息流</router-link>
            <router-link to="/review" class="secondary-link">复核中心</router-link>
          </div>
        </section>
      </template>
    </section>`
}

export default EvidenceDetail
