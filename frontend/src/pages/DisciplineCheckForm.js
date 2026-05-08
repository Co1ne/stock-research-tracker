import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const CHECKLIST_LABELS = {
  has_clear_thesis: '核心逻辑清晰，不是临时起意',
  evidence_reviewed: '关键证据已经人工复核',
  risk_reviewed: '主要风险已经逐条看过',
  position_within_limit: '仓位符合个人纪律上限',
  invalidation_defined: '证伪条件和处理预案明确',
  no_pending_key_evidence: '不依赖待复核关键证据',
  no_rejected_core_evidence: '不依赖已驳回核心证据'
}
const REVIEW_LABELS = { pending: '待复核', approved: '已确认', rejected: '已驳回', edited: '已编辑确认' }
const RESULT_LABELS = { passed: '纪律检查通过', blocked: '存在阻断项' }
const STATUS_LABELS = { draft: '草稿', completed: '已完成', archived: '已归档' }

function emptyChecklist() {
  return Object.fromEntries(Object.keys(CHECKLIST_LABELS).map((key) => [key, false]))
}

const DisciplineCheckForm = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const router = useRouter()
    const isEdit = ref(Boolean(route.params.id))
    const companies = ref([])
    const options = ref(null)
    const check = ref(null)
    const loading = ref(false)
    const saving = ref(false)
    const error = ref('')
    const message = ref('')
    const form = ref({
      company_id: '',
      hypothesis_id: '',
      title: '',
      status: 'draft',
      thesis_snapshot: '',
      action_reason: '',
      position_plan: '',
      max_position_pct: '',
      risk_acknowledgement: '',
      invalidation_plan: '',
      checklist: emptyChecklist(),
      cited_evidence_ids: [],
      cited_research_note_ids: []
    })

    async function loadCompanies() {
      companies.value = await api('/companies').catch(() => [])
      if (!form.value.company_id && companies.value[0]) form.value.company_id = companies.value[0].id
    }

    async function loadOptions() {
      if (!form.value.company_id) {
        options.value = null
        return
      }
      try {
        options.value = await api(`/companies/${form.value.company_id}/discipline-check-options`)
        if (!form.value.hypothesis_id && options.value?.hypothesis?.id) form.value.hypothesis_id = options.value.hypothesis.id
        if (!form.value.thesis_snapshot && options.value?.hypothesis?.thesis) form.value.thesis_snapshot = options.value.hypothesis.thesis
      } catch (err) {
        error.value = err.message || '纪律检查选项加载失败'
        options.value = null
      }
    }

    async function loadExisting() {
      if (!route.params.id) return
      const data = await api(`/discipline-checks/${route.params.id}`)
      check.value = data
      form.value = {
        company_id: data.company_id || '',
        hypothesis_id: data.hypothesis_id || '',
        title: data.title || '',
        status: data.status || 'draft',
        thesis_snapshot: data.thesis_snapshot || '',
        action_reason: data.action_reason || '',
        position_plan: data.position_plan || '',
        max_position_pct: data.max_position_pct ?? '',
        risk_acknowledgement: data.risk_acknowledgement || '',
        invalidation_plan: data.invalidation_plan || '',
        checklist: { ...emptyChecklist(), ...(data.checklist || {}) },
        cited_evidence_ids: data.cited_evidence_ids || [],
        cited_research_note_ids: data.cited_research_note_ids || []
      }
    }

    function toggleList(field, id) {
      const value = Number(id)
      if (form.value[field].includes(value)) {
        form.value[field] = form.value[field].filter((item) => item !== value)
      } else {
        form.value[field] = [...form.value[field], value]
      }
    }

    function payload() {
      return {
        company_id: Number(form.value.company_id),
        hypothesis_id: form.value.hypothesis_id ? Number(form.value.hypothesis_id) : null,
        title: form.value.title,
        status: form.value.status,
        thesis_snapshot: form.value.thesis_snapshot,
        action_reason: form.value.action_reason,
        position_plan: form.value.position_plan,
        max_position_pct: form.value.max_position_pct === '' ? null : Number(form.value.max_position_pct),
        risk_acknowledgement: form.value.risk_acknowledgement,
        invalidation_plan: form.value.invalidation_plan,
        checklist: form.value.checklist,
        cited_evidence_ids: form.value.cited_evidence_ids,
        cited_research_note_ids: form.value.cited_research_note_ids
      }
    }

    async function save() {
      saving.value = true
      error.value = ''
      message.value = ''
      try {
        const data = isEdit.value
          ? await api(`/discipline-checks/${route.params.id}`, { method: 'PUT', body: JSON.stringify(payload()) })
          : await api('/discipline-checks', { method: 'POST', body: JSON.stringify(payload()) })
        check.value = data
        message.value = '纪律检查单已保存。'
        if (!isEdit.value) {
          isEdit.value = true
          router.replace(`/discipline-checks/${data.id}`)
        }
      } catch (err) {
        error.value = err.message || '纪律检查单保存失败'
      } finally {
        saving.value = false
      }
    }

    async function complete() {
      if (!route.params.id && !check.value?.id) {
        await save()
      }
      const id = route.params.id || check.value?.id
      if (!id) return
      saving.value = true
      error.value = ''
      message.value = ''
      try {
        check.value = await api(`/discipline-checks/${id}/complete`, { method: 'POST' })
        form.value.status = check.value.status
        message.value = '纪律检查已标记为通过。'
      } catch (err) {
        error.value = err.message || '仍存在阻断项，暂不能完成纪律检查'
        await loadExisting().catch(() => {})
      } finally {
        saving.value = false
      }
    }

    function reviewLabel(value) {
      return REVIEW_LABELS[value] || value || '-'
    }

    function resultLabel(value) {
      return RESULT_LABELS[value] || value || '-'
    }

    function statusLabel(value) {
      return STATUS_LABELS[value] || value || '-'
    }

    watch(() => form.value.company_id, async () => {
      if (!loading.value) await loadOptions()
    })

    onMounted(async () => {
      loading.value = true
      error.value = ''
      try {
        if (route.query.company_id) form.value.company_id = route.query.company_id
        await loadCompanies()
        await loadExisting()
        await loadOptions()
      } catch (err) {
        error.value = err.message || '纪律检查页面加载失败'
      } finally {
        loading.value = false
      }
    })

    return { route, isEdit, companies, options, check, loading, saving, error, message, form, CHECKLIST_LABELS, toggleList, save, complete, reviewLabel, resultLabel, statusLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Discipline Form</p><h1>{{ isEdit ? '纪律检查详情' : '新建买入前纪律检查' }}</h1></div>
        <router-link to="/discipline-checks" class="secondary-link">返回纪律检查</router-link>
      </div>
      <p class="muted">该表单只用于个人纪律留痕，不构成任何交易建议。只有阻断项清零后，才能标记为“纪律检查通过”。</p>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-if="loading" class="notice">正在加载纪律检查表单...</div>

      <section v-if="check" class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Gate Result</p><h2>纪律闸门</h2></div>
          <span class="status-badge" :class="check.discipline_result === 'passed' ? 'stable' : 'risk_rising'">{{ resultLabel(check.discipline_result) }}</span>
        </div>
        <div class="metric-grid compact">
          <div class="metric"><span>状态</span><strong>{{ statusLabel(check.status) }}</strong></div>
          <div class="metric"><span>引用证据</span><strong>{{ check.evidence_count ?? 0 }}</strong></div>
          <div class="metric"><span>已确认</span><strong>{{ check.reviewed_evidence_count ?? 0 }}</strong></div>
          <div class="metric"><span>未确认</span><strong>{{ check.unreviewed_evidence_count ?? 0 }}</strong></div>
          <div class="metric"><span>已驳回</span><strong>{{ check.rejected_evidence_count ?? 0 }}</strong></div>
        </div>
        <div v-if="check.blockers?.length" class="notice error">
          <strong>当前阻断项</strong>
          <div v-for="item in check.blockers" :key="item">{{ item }}</div>
        </div>
        <div v-else class="notice ok">阻断项已清零，可完成纪律检查。</div>
      </section>

      <section class="logic-panel">
        <div class="logic-header"><div><p class="eyebrow">Core Form</p><h2>核心信息</h2></div></div>
        <form class="panel-form hypothesis-form" @submit.prevent="save">
          <label><span class="field-label">公司</span><select v-model="form.company_id" required><option value="">请选择公司</option><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option></select></label>
          <label><span class="field-label">标题</span><input v-model="form.title" required placeholder="例如：某公司买入前纪律检查" /></label>
          <label><span class="field-label">状态</span><select v-model="form.status"><option value="draft">草稿</option><option value="archived">归档</option></select></label>
          <label><span class="field-label">最大计划仓位比例（%）</span><input v-model="form.max_position_pct" type="number" min="0.1" max="100" step="0.1" required placeholder="例如 8" /></label>
          <label><span class="field-label">核心逻辑快照</span><textarea v-model="form.thesis_snapshot" rows="4" placeholder="这家公司为什么值得持续跟踪，逻辑来自哪里"></textarea></label>
          <label><span class="field-label">本次行动理由</span><textarea v-model="form.action_reason" rows="4" placeholder="为什么现在需要做纪律检查，引用了哪些已复核事实"></textarea></label>
          <label><span class="field-label">仓位纪律</span><textarea v-model="form.position_plan" rows="3" placeholder="计划仓位、分批原则、不得突破的纪律上限"></textarea></label>
          <label><span class="field-label">主要风险确认</span><textarea v-model="form.risk_acknowledgement" rows="4" placeholder="列出已经看过并接受继续跟踪的不确定性"></textarea></label>
          <label><span class="field-label">证伪/退出预案</span><textarea v-model="form.invalidation_plan" rows="4" placeholder="哪些事实出现后，必须降级观察或复盘"></textarea></label>
          <div class="action-row">
            <button type="submit" :disabled="saving">{{ saving ? '保存中...' : '保存草稿' }}</button>
            <button type="button" class="secondary" @click="complete" :disabled="saving || (!isEdit && !check)">完成纪律检查</button>
          </div>
        </form>
      </section>

      <section class="logic-panel">
        <div class="logic-header"><div><p class="eyebrow">Checklist</p><h2>纪律确认项</h2></div></div>
        <div class="mini-list">
          <label v-for="(label, key) in CHECKLIST_LABELS" :key="key" class="mini-item">
            <span><input type="checkbox" v-model="form.checklist[key]" /> {{ label }}</span>
          </label>
        </div>
      </section>

      <div class="logic-columns">
        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Research Notes</p><h2>引用研究记录</h2></div><span class="status-badge pending">已选 {{ form.cited_research_note_ids.length }}</span></div>
          <EmptyState v-if="!options?.research_notes?.length" title="暂无研究记录" description="建议先把已复核证据沉淀为研究记录。" />
          <div v-else class="mini-list">
            <label v-for="note in options.research_notes" :key="'discipline-note-' + note.id" class="mini-item">
              <span><input type="checkbox" :checked="form.cited_research_note_ids.includes(note.id)" @change="toggleList('cited_research_note_ids', note.id)" /> {{ note.title }}</span>
              <span>引用 {{ note.evidence_count ?? 0 }} ｜ 未确认 {{ note.unreviewed_evidence_count ?? 0 }}</span>
            </label>
          </div>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Evidence</p><h2>引用证据</h2></div><span class="status-badge pending">已选 {{ form.cited_evidence_ids.length }}</span></div>
          <EmptyState v-if="!options?.evidence_items?.length" title="暂无证据" description="请先采集、分析并复核证据。" />
          <div v-else class="mini-list">
            <label v-for="item in options.evidence_items" :key="'discipline-evidence-' + item.id" class="mini-item">
              <span><input type="checkbox" :checked="form.cited_evidence_ids.includes(item.id)" @change="toggleList('cited_evidence_ids', item.id)" /> {{ item.title }}</span>
              <span>复核 {{ reviewLabel(item.review_status) }} ｜ {{ item.hypothesis_relation || '-' }} ｜ <router-link :to="'/evidence/' + item.id">证据详情</router-link></span>
            </label>
          </div>
        </section>
      </div>
    </section>`
}

export default DisciplineCheckForm
