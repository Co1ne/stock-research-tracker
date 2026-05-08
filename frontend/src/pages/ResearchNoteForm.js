import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const ResearchNoteForm = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const router = useRouter()
    const companies = ref([])
    const evidenceRows = ref([])
    const loading = ref(false)
    const error = ref('')
    const message = ref('')
    const evidenceFilter = ref({ review_status: '', hypothesis_relation: '' })
    const form = ref({
      company_id: '',
      hypothesis_id: '',
      title: '',
      note_type: 'manual_note',
      conclusion_direction: 'watch',
      summary: '',
      content: '',
      status: 'active',
      cited_evidence_ids: []
    })

    async function loadCompanies() {
      companies.value = await api('/companies').catch(() => [])
    }

    async function loadEvidence() {
      if (!form.value.company_id) {
        evidenceRows.value = []
        return
      }
      try {
        const query = new URLSearchParams()
        Object.entries(evidenceFilter.value).forEach(([key, value]) => {
          if (value) query.set(key, value)
        })
        const data = await api(`/companies/${form.value.company_id}/hypothesis-evidence${query.toString() ? `?${query.toString()}` : ''}`)
        evidenceRows.value = data?.items || []
        if (!form.value.hypothesis_id && data?.hypothesis_id) form.value.hypothesis_id = data.hypothesis_id
      } catch (err) {
        error.value = err.message || '证据列表加载失败'
        evidenceRows.value = []
      }
    }

    async function preloadFromEvidence() {
      const evidenceId = route.query.evidence_id
      if (!evidenceId) return
      try {
        const detail = await api(`/evidence/${evidenceId}`)
        form.value.company_id = route.query.company_id || detail.company?.id || ''
        form.value.hypothesis_id = route.query.hypothesis_id || detail.hypothesis_link?.hypothesis_id || ''
        form.value.cited_evidence_ids = [Number(evidenceId)]
        form.value.title = `${detail.company?.name || '公司'}：${detail.content?.title || '证据复核'}`
        form.value.summary = detail.hypothesis_link?.evidence_summary || detail.content?.summary || ''
        form.value.content = detail.hypothesis_link?.relation_note || detail.content?.content || ''
      } catch (err) {
        error.value = err.message || '证据预加载失败'
      }
    }

    function toggleEvidence(id) {
      const value = Number(id)
      if (form.value.cited_evidence_ids.includes(value)) {
        form.value.cited_evidence_ids = form.value.cited_evidence_ids.filter((item) => item !== value)
      } else {
        form.value.cited_evidence_ids = [...form.value.cited_evidence_ids, value]
      }
    }

    async function save() {
      error.value = ''
      message.value = ''
      try {
        const payload = {
          company_id: Number(form.value.company_id),
          hypothesis_id: form.value.hypothesis_id ? Number(form.value.hypothesis_id) : null,
          title: form.value.title,
          note_type: form.value.note_type,
          conclusion_direction: form.value.conclusion_direction,
          summary: form.value.summary,
          content: form.value.content,
          status: form.value.status,
          cited_evidence_ids: form.value.cited_evidence_ids
        }
        const data = await api('/research-notes', { method: 'POST', body: JSON.stringify(payload) })
        message.value = '研究记录已创建。'
        router.push(`/research-notes/${data.id}`)
      } catch (err) {
        error.value = err.message || '研究记录保存失败'
      }
    }

    watch(() => form.value.company_id, loadEvidence)
    onMounted(async () => {
      loading.value = true
      await loadCompanies()
      await preloadFromEvidence()
      if (!form.value.company_id && route.query.company_id) form.value.company_id = route.query.company_id
      await loadEvidence()
      loading.value = false
    })

    return { companies, evidenceRows, loading, error, message, evidenceFilter, form, loadEvidence, toggleEvidence, save }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">New Research Note</p><h1>新增研究记录</h1></div>
        <router-link to="/research-notes" class="secondary-link">返回研究记录</router-link>
      </div>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-if="loading" class="notice">正在准备研究记录表单...</div>
      <section class="logic-panel">
        <div class="logic-header"><div><p class="eyebrow">Manual Note</p><h2>人工研究记录</h2></div></div>
        <form class="panel-form hypothesis-form" @submit.prevent="save">
          <label><span class="field-label">公司</span><select v-model="form.company_id" required><option value="">请选择公司</option><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option></select></label>
          <label><span class="field-label">记录类型</span><select v-model="form.note_type"><option value="daily_note">日常记录</option><option value="event_review">事件复盘</option><option value="hypothesis_update">假设更新</option><option value="risk_review">风险复核</option><option value="financial_review">财务复核</option><option value="manual_note">手动记录</option></select></label>
          <label><span class="field-label">结论方向</span><select v-model="form.conclusion_direction"><option value="strengthen">强化假设</option><option value="weaken">削弱假设</option><option value="watch">需要观察</option><option value="neutral">中性</option><option value="risk">风险提示</option></select></label>
          <label><span class="field-label">状态</span><select v-model="form.status"><option value="draft">草稿</option><option value="active">有效</option><option value="archived">已归档</option></select></label>
          <label><span class="field-label">标题</span><input v-model="form.title" required placeholder="例如：减持公告事件复核" /></label>
          <label><span class="field-label">摘要</span><textarea v-model="form.summary" rows="3" placeholder="一句话说明这次复核的阶段性判断"></textarea></label>
          <label><span class="field-label">正文</span><textarea v-model="form.content" rows="8" placeholder="基于引用证据写下人工判断、后续观察点和仍需确认的问题"></textarea></label>
          <div class="action-row"><button type="submit">保存研究记录</button></div>
        </form>
      </section>

      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Cited Evidence</p><h2>选择引用证据</h2></div>
          <span class="status-badge pending">已选 {{ form.cited_evidence_ids.length }} 条</span>
        </div>
        <form class="panel-form" @submit.prevent="loadEvidence">
          <select v-model="evidenceFilter.review_status"><option value="">全部复核状态</option><option value="pending">待复核</option><option value="approved">已确认</option><option value="rejected">已驳回</option><option value="edited">已编辑确认</option></select>
          <select v-model="evidenceFilter.hypothesis_relation"><option value="">全部关系</option><option value="supports">支持假设</option><option value="contradicts">反驳假设</option><option value="neutral">中性相关</option><option value="watch">需要观察</option><option value="unrelated">无关</option></select>
          <button type="submit">筛选证据</button>
        </form>
        <EmptyState v-if="!form.company_id" title="请先选择公司" description="选择公司后可以引用该公司的假设验证证据。" />
        <EmptyState v-else-if="evidenceRows.length === 0" title="暂无可引用证据" description="可先采集数据、复核证据，再创建研究记录。" />
        <div v-else class="mini-list">
          <label v-for="item in evidenceRows" :key="'select-evidence-' + item.evidence_id" class="mini-item">
            <span><input type="checkbox" :checked="form.cited_evidence_ids.includes(item.evidence_id)" @change="toggleEvidence(item.evidence_id)" /> {{ item.title }}</span>
            <span>复核 {{ item.review_status }} ｜ 关系 {{ item.hypothesis_relation }} ｜ 来源 {{ item.source_name || '-' }}</span>
          </label>
        </div>
      </section>
    </section>`
}

export default ResearchNoteForm
