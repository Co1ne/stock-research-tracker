import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const NOTE_TYPE_LABELS = {
  daily_note: '日常记录',
  event_review: '事件复盘',
  hypothesis_update: '假设更新',
  risk_review: '风险复核',
  financial_review: '财务复核',
  manual_note: '手动记录'
}
const DIRECTION_LABELS = { strengthen: '强化假设', weaken: '削弱假设', watch: '需要观察', neutral: '中性', risk: '风险提示' }
const STATUS_LABELS = { draft: '草稿', active: '有效', archived: '已归档' }
const REVIEW_LABELS = { pending: '待复核', approved: '已确认', rejected: '已驳回', edited: '已编辑确认' }
const RELATION_LABELS = { supports: '支持假设', contradicts: '反驳假设', neutral: '中性相关', watch: '需要观察', unrelated: '无关' }
const DIRECTION_IMPACT_LABELS = { positive: '正向', negative: '负向', neutral: '中性', unknown: '未知' }
const STRENGTH_LABELS = { high: '高', medium: '中', low: '低' }
const ASPECT_LABELS = { revenue: '收入', profit: '利润', margin: '毛利率', cashflow: '现金流', order: '订单', shareholder: '股东行为', valuation: '估值', industry: '行业', policy: '政策', risk: '风险', business_line: '业务线', other: '其他' }

const ResearchNoteDetail = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const detail = ref(null)
    const loading = ref(false)
    const error = ref('')
    const message = ref('')
    const editing = ref(false)
    const form = ref(emptyForm())

    function emptyForm() {
      return { title: '', note_type: 'manual_note', conclusion_direction: 'watch', summary: '', content: '', status: 'active', cited_evidence_ids_text: '' }
    }

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const data = await api(`/research-notes/${route.params.id}`)
        detail.value = data
        form.value = {
          title: data.title || '',
          note_type: data.note_type || 'manual_note',
          conclusion_direction: data.conclusion_direction || 'watch',
          summary: data.summary || '',
          content: data.content || '',
          status: data.status || 'active',
          cited_evidence_ids_text: (data.cited_evidence_ids || []).join(',')
        }
      } catch (err) {
        error.value = err.message || '研究记录加载失败'
        detail.value = null
      } finally {
        loading.value = false
      }
    }

    function evidenceIdsFromText() {
      return String(form.value.cited_evidence_ids_text || '').split(',').map((item) => item.trim()).filter(Boolean).map((item) => Number(item))
    }

    async function save() {
      error.value = ''
      message.value = ''
      try {
        const data = await api(`/research-notes/${route.params.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            company_id: detail.value.company_id,
            hypothesis_id: detail.value.hypothesis_id,
            title: form.value.title,
            note_type: form.value.note_type,
            conclusion_direction: form.value.conclusion_direction,
            summary: form.value.summary,
            content: form.value.content,
            status: form.value.status,
            cited_evidence_ids: evidenceIdsFromText()
          })
        })
        detail.value = data
        editing.value = false
        message.value = '研究记录已保存。'
      } catch (err) {
        error.value = err.message || '研究记录保存失败'
      }
    }

    async function archiveNote() {
      error.value = ''
      message.value = ''
      try {
        detail.value = await api(`/research-notes/${route.params.id}/archive`, { method: 'POST' })
        message.value = '研究记录已归档。'
      } catch (err) {
        error.value = err.message || '归档失败'
      }
    }

    function qualityMessage() {
      const rows = detail.value?.cited_evidence_details || []
      if (!rows.length) return '尚未引用证据。'
      if (rows.some((item) => item.review_status === 'rejected')) return '包含已驳回证据，请谨慎使用。'
      if (rows.some((item) => item.review_status === 'pending')) return '包含待复核证据。'
      return '引用证据均已人工确认。'
    }

    function label(map, value) {
      return map[value] || value || '-'
    }

    watch(() => route.params.id, load)
    onMounted(load)
    return { detail, loading, error, message, editing, form, load, save, archiveNote, qualityMessage, label, NOTE_TYPE_LABELS, DIRECTION_LABELS, STATUS_LABELS, REVIEW_LABELS, RELATION_LABELS, DIRECTION_IMPACT_LABELS, STRENGTH_LABELS, ASPECT_LABELS }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Research Note</p><h1>研究记录详情</h1></div>
        <router-link to="/research-notes" class="secondary-link">返回研究记录</router-link>
      </div>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-if="loading" class="notice">正在加载研究记录...</div>
      <EmptyState v-if="!loading && !detail" title="未找到研究记录" description="该研究记录不存在，或接口暂时不可用。" />
      <template v-if="detail">
        <section class="logic-panel">
          <div class="logic-header">
            <div><p class="eyebrow">Summary</p><h2>{{ detail.title }}</h2></div>
            <div class="action-row">
              <router-link :to="'/report-drafts/new?company_id=' + detail.company_id + '&research_note_id=' + detail.id" class="secondary-link">基于此记录生成快照</router-link>
              <button class="secondary" @click="editing = !editing">{{ editing ? '取消编辑' : '编辑' }}</button>
              <button class="secondary" @click="archiveNote">归档</button>
            </div>
          </div>
          <div class="summary-row">
            <span>{{ detail.company_name || detail.stock_code || '-' }}</span>
            <span>{{ label(NOTE_TYPE_LABELS, detail.note_type) }}</span>
            <span>{{ label(DIRECTION_LABELS, detail.conclusion_direction) }}</span>
            <span>{{ label(STATUS_LABELS, detail.status) }}</span>
            <span>更新 {{ detail.updated_at || '-' }}</span>
          </div>
          <div class="notice" :class="detail.unreviewed_evidence_count ? 'error' : 'ok'">{{ qualityMessage() }}</div>
          <h3>摘要</h3>
          <p>{{ detail.summary || '暂无摘要' }}</p>
          <h3>正文</h3>
          <p>{{ detail.content || '暂无正文' }}</p>
        </section>

        <section v-if="editing" class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Edit</p><h2>编辑研究记录</h2></div></div>
          <form class="panel-form hypothesis-form" @submit.prevent="save">
            <label><span class="field-label">标题</span><input v-model="form.title" required /></label>
            <label><span class="field-label">记录类型</span><select v-model="form.note_type"><option value="daily_note">日常记录</option><option value="event_review">事件复盘</option><option value="hypothesis_update">假设更新</option><option value="risk_review">风险复核</option><option value="financial_review">财务复核</option><option value="manual_note">手动记录</option></select></label>
            <label><span class="field-label">结论方向</span><select v-model="form.conclusion_direction"><option value="strengthen">强化假设</option><option value="weaken">削弱假设</option><option value="watch">需要观察</option><option value="neutral">中性</option><option value="risk">风险提示</option></select></label>
            <label><span class="field-label">状态</span><select v-model="form.status"><option value="draft">草稿</option><option value="active">有效</option><option value="archived">已归档</option></select></label>
            <label><span class="field-label">摘要</span><textarea v-model="form.summary" rows="3"></textarea></label>
            <label><span class="field-label">正文</span><textarea v-model="form.content" rows="8"></textarea></label>
            <label><span class="field-label">引用证据 ID，逗号分隔</span><input v-model="form.cited_evidence_ids_text" placeholder="例如 3,5,8" /></label>
            <div class="action-row"><button type="submit">保存</button></div>
          </form>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Evidence</p><h2>引用证据</h2></div></div>
          <div class="summary-row">
            <span>引用 {{ detail.evidence_count ?? 0 }}</span>
            <span>已确认 {{ detail.reviewed_evidence_count ?? 0 }}</span>
            <span>未确认 {{ detail.unreviewed_evidence_count ?? 0 }}</span>
          </div>
          <EmptyState v-if="!detail.cited_evidence_details?.length" title="暂无引用证据" description="研究记录需要引用可追溯证据，后续可以继续编辑补充。" />
          <div v-else class="mini-list">
            <div v-for="item in detail.cited_evidence_details" :key="'note-evidence-' + item.evidence_id" class="mini-item">
              <strong>{{ item.title }}</strong>
              <span>{{ item.source_name || '未记录来源' }} / {{ item.source_type || '-' }} / {{ item.source_date || '-' }}</span>
              <span>复核 {{ label(REVIEW_LABELS, item.review_status) }} ｜ {{ label(RELATION_LABELS, item.hypothesis_relation) }} ｜ {{ label(DIRECTION_IMPACT_LABELS, item.impact_direction) }} ｜ 强度 {{ label(STRENGTH_LABELS, item.impact_strength) }} ｜ 维度 {{ label(ASPECT_LABELS, item.affected_aspect) }}</span>
              <router-link :to="'/evidence/' + item.evidence_id" class="secondary-link">查看证据详情</router-link>
            </div>
          </div>
        </section>
      </template>
    </section>`
}

export default ResearchNoteDetail
