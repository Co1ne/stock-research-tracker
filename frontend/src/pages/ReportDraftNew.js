import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const REVIEW_LABELS = { pending: '待复核', approved: '已确认', rejected: '已驳回', edited: '已编辑确认' }
const RELATION_LABELS = { supports: '支持假设', contradicts: '反驳假设', neutral: '中性相关', watch: '需要观察', unrelated: '无关' }
const NOTE_TYPE_LABELS = { daily_note: '日常记录', event_review: '事件复盘', hypothesis_update: '假设更新', risk_review: '风险复核', financial_review: '财务复核', manual_note: '手动记录' }
const DIRECTION_LABELS = { strengthen: '强化假设', weaken: '削弱假设', watch: '需要观察', neutral: '中性', risk: '风险提示' }

const ReportDraftNew = {
  components: { EmptyState },
  setup() {
    const route = useRoute()
    const companies = ref([])
    const options = ref(null)
    const loading = ref(false)
    const generating = ref(false)
    const error = ref('')
    const message = ref('')
    const companyId = ref('')
    const selectedResearchNoteIds = ref([])
    const selectedEvidenceIds = ref([])
    const includeHypothesis = ref(true)
    const includeEvidenceTrace = ref(true)
    const includeUnreviewedWarning = ref(true)
    const draft = ref(null)

    async function loadCompanies() {
      companies.value = await api('/companies').catch(() => [])
      if (!companyId.value && companies.value[0]) companyId.value = companies.value[0].id
    }

    async function loadOptions() {
      if (!companyId.value) {
        options.value = null
        return
      }
      loading.value = true
      error.value = ''
      try {
        options.value = await api(`/companies/${companyId.value}/report-draft-options`)
        applyRouteSelections()
      } catch (err) {
        error.value = err.message || '快照选项加载失败'
        options.value = null
      } finally {
        loading.value = false
      }
    }

    function applyRouteSelections() {
      const noteId = Number(route.query.research_note_id || 0)
      const evidenceId = Number(route.query.evidence_id || 0)
      if (noteId && !selectedResearchNoteIds.value.includes(noteId)) selectedResearchNoteIds.value = [...selectedResearchNoteIds.value, noteId]
      if (evidenceId && !selectedEvidenceIds.value.includes(evidenceId)) selectedEvidenceIds.value = [...selectedEvidenceIds.value, evidenceId]
    }

    function toggleList(listRef, id) {
      const value = Number(id)
      if (listRef.value.includes(value)) {
        listRef.value = listRef.value.filter((item) => item !== value)
      } else {
        listRef.value = [...listRef.value, value]
      }
    }

    function toggleResearchNote(id) {
      toggleList(selectedResearchNoteIds, id)
    }

    function toggleEvidence(id) {
      toggleList(selectedEvidenceIds, id)
    }

    async function generate() {
      if (!companyId.value) {
        error.value = '请选择公司'
        return
      }
      generating.value = true
      error.value = ''
      message.value = ''
      try {
        draft.value = await api('/report-drafts/preview', {
          method: 'POST',
          body: JSON.stringify({
            company_id: Number(companyId.value),
            research_note_ids: selectedResearchNoteIds.value,
            evidence_ids: selectedEvidenceIds.value,
            include_hypothesis: includeHypothesis.value,
            include_evidence_trace: includeEvidenceTrace.value,
            include_unreviewed_warning: includeUnreviewedWarning.value
          })
        })
        message.value = '研究快照草稿已生成。'
      } catch (err) {
        error.value = err.message || '生成研究快照失败'
        draft.value = null
      } finally {
        generating.value = false
      }
    }

    async function copyMarkdown() {
      if (!draft.value?.markdown) return
      try {
        await navigator.clipboard.writeText(draft.value.markdown)
        message.value = 'Markdown 已复制。'
      } catch (err) {
        message.value = '当前浏览器未允许自动复制，可直接选中文本手动复制。'
      }
    }

    function reviewLabel(value) {
      return REVIEW_LABELS[value] || value || '-'
    }

    function relationLabel(value) {
      return RELATION_LABELS[value] || value || '-'
    }

    function noteTypeLabel(value) {
      return NOTE_TYPE_LABELS[value] || value || '-'
    }

    function directionLabel(value) {
      return DIRECTION_LABELS[value] || value || '-'
    }

    watch(companyId, () => {
      selectedResearchNoteIds.value = []
      selectedEvidenceIds.value = []
      draft.value = null
      loadOptions()
    })

    onMounted(async () => {
      if (route.query.company_id) companyId.value = route.query.company_id
      await loadCompanies()
      await loadOptions()
    })

    return { companies, options, loading, generating, error, message, companyId, selectedResearchNoteIds, selectedEvidenceIds, includeHypothesis, includeEvidenceTrace, includeUnreviewedWarning, draft, loadOptions, toggleResearchNote, toggleEvidence, generate, copyMarkdown, reviewLabel, relationLabel, noteTypeLabel, directionLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Report Draft</p><h1>生成研究快照草稿</h1></div>
        <router-link to="/" class="secondary-link">返回工作台</router-link>
      </div>
      <p class="muted">选择公司、研究记录和证据，系统只按已有字段拼装 Markdown 草稿，不生成自动投资结论。</p>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>

      <section class="logic-panel">
        <div class="logic-header"><div><p class="eyebrow">Scope</p><h2>选择范围</h2></div></div>
        <form class="panel-form" @submit.prevent="generate">
          <label><span class="field-label">公司</span><select v-model="companyId" required><option value="">请选择公司</option><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option></select></label>
          <label><span class="field-label">包含内容</span><span class="summary-row"><span><input type="checkbox" v-model="includeHypothesis" /> 投资假设</span><span><input type="checkbox" v-model="includeEvidenceTrace" /> 来源追踪</span><span><input type="checkbox" v-model="includeUnreviewedWarning" /> 未复核提示</span></span></label>
          <div class="action-row"><button type="submit" :disabled="generating">{{ generating ? '生成中...' : '生成草稿' }}</button></div>
        </form>
      </section>

      <section class="logic-panel">
        <div class="logic-header"><div><p class="eyebrow">Hypothesis</p><h2>投资假设摘要</h2></div></div>
        <div v-if="loading" class="notice">正在加载可选内容...</div>
        <EmptyState v-if="!loading && !options?.hypothesis" title="暂无投资假设" description="仍可生成基础公司快照，建议后续补充投资假设。" />
        <template v-if="options?.hypothesis">
          <p>{{ options.hypothesis.thesis || '暂无核心假设' }}</p>
          <div class="summary-row">
            <span>当前结论 {{ options.hypothesis.current_view || '-' }}</span>
            <span>优先级 {{ options.hypothesis.tracking_priority || '-' }}</span>
            <span>假设状态 {{ options.hypothesis.hypothesis_status || '-' }}</span>
          </div>
        </template>
      </section>

      <div class="logic-columns">
        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Research Notes</p><h2>选择研究记录</h2></div><span class="status-badge pending">已选 {{ selectedResearchNoteIds.length }}</span></div>
          <EmptyState v-if="!options?.research_notes?.length" title="暂无研究记录" description="可以先从证据详情页创建研究记录，或生成基础快照。" />
          <div v-else class="mini-list">
            <label v-for="note in options.research_notes" :key="'draft-note-' + note.id" class="mini-item">
              <span><input type="checkbox" :checked="selectedResearchNoteIds.includes(note.id)" @change="toggleResearchNote(note.id)" /> {{ note.title }}</span>
              <span>{{ noteTypeLabel(note.note_type) }} ｜ {{ directionLabel(note.conclusion_direction) }} ｜ 引用 {{ note.evidence_count ?? 0 }} ｜ 未确认 {{ note.unreviewed_evidence_count ?? 0 }}</span>
            </label>
          </div>
        </section>

        <section class="logic-panel">
          <div class="logic-header"><div><p class="eyebrow">Evidence</p><h2>选择证据</h2></div><span class="status-badge pending">已选 {{ selectedEvidenceIds.length }}</span></div>
          <EmptyState v-if="!options?.evidence_items?.length" title="暂无证据" description="可先采集并复核证据，再生成更完整的快照。" />
          <div v-else class="mini-list">
            <label v-for="item in options.evidence_items" :key="'draft-evidence-' + item.id" class="mini-item">
              <span><input type="checkbox" :checked="selectedEvidenceIds.includes(item.id)" @change="toggleEvidence(item.id)" /> {{ item.title }}</span>
              <span>复核 {{ reviewLabel(item.review_status) }} ｜ {{ relationLabel(item.hypothesis_relation) }} ｜ {{ item.source_name || '-' }} ｜ <router-link :to="'/evidence/' + item.id">详情</router-link></span>
            </label>
          </div>
        </section>
      </div>

      <section class="logic-panel">
        <div class="logic-header"><div><p class="eyebrow">Markdown</p><h2>草稿预览</h2></div><button v-if="draft?.markdown" @click="copyMarkdown">复制 Markdown</button></div>
        <div v-if="draft?.warnings?.length" class="notice error">
          <div v-for="item in draft.warnings" :key="item">{{ item }}</div>
        </div>
        <EmptyState v-if="!draft?.markdown" title="尚未生成草稿" description="选择内容后点击“生成草稿”，这里会显示可复制 Markdown。" />
        <textarea v-else v-model="draft.markdown" rows="24"></textarea>
      </section>
    </section>`
}

export default ReportDraftNew
