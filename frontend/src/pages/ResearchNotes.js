import { onMounted, ref } from 'vue'
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

const DIRECTION_LABELS = {
  strengthen: '强化假设',
  weaken: '削弱假设',
  watch: '需要观察',
  neutral: '中性',
  risk: '风险提示'
}

const STATUS_LABELS = { draft: '草稿', active: '有效', archived: '已归档' }

const ResearchNotes = {
  components: { EmptyState },
  setup() {
    const notes = ref([])
    const companies = ref([])
    const loading = ref(false)
    const error = ref('')
    const filters = ref({ company_id: '', note_type: '', conclusion_direction: '', status: '' })

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const query = new URLSearchParams()
        Object.entries(filters.value).forEach(([key, value]) => {
          if (value) query.set(key, value)
        })
        const [noteRows, companyRows] = await Promise.all([
          api(`/research-notes${query.toString() ? `?${query.toString()}` : ''}`),
          api('/companies').catch(() => [])
        ])
        notes.value = Array.isArray(noteRows) ? noteRows : []
        companies.value = Array.isArray(companyRows) ? companyRows : []
      } catch (err) {
        error.value = err.message || '研究记录加载失败'
        notes.value = []
      } finally {
        loading.value = false
      }
    }

    function resetFilters() {
      filters.value = { company_id: '', note_type: '', conclusion_direction: '', status: '' }
      load()
    }

    function noteTypeLabel(value) {
      return NOTE_TYPE_LABELS[value] || value || '-'
    }

    function directionLabel(value) {
      return DIRECTION_LABELS[value] || value || '-'
    }

    function statusLabel(value) {
      return STATUS_LABELS[value] || value || '-'
    }

    onMounted(load)
    return { notes, companies, loading, error, filters, load, resetFilters, noteTypeLabel, directionLabel, statusLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Research Notes</p><h1>研究记录</h1></div>
        <router-link to="/research-notes/new" class="secondary-link">新增研究记录</router-link>
      </div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <form class="panel-form" @submit.prevent="load">
        <select v-model="filters.company_id">
          <option value="">全部公司</option>
          <option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option>
        </select>
        <select v-model="filters.note_type">
          <option value="">全部类型</option>
          <option value="daily_note">日常记录</option>
          <option value="event_review">事件复盘</option>
          <option value="hypothesis_update">假设更新</option>
          <option value="risk_review">风险复核</option>
          <option value="financial_review">财务复核</option>
          <option value="manual_note">手动记录</option>
        </select>
        <select v-model="filters.conclusion_direction">
          <option value="">全部方向</option>
          <option value="strengthen">强化假设</option>
          <option value="weaken">削弱假设</option>
          <option value="watch">需要观察</option>
          <option value="neutral">中性</option>
          <option value="risk">风险提示</option>
        </select>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="active">有效</option>
          <option value="archived">已归档</option>
        </select>
        <div class="action-row">
          <button type="submit">筛选</button>
          <button type="button" class="secondary" @click="resetFilters">重置</button>
        </div>
      </form>
      <div v-if="loading" class="notice">正在加载研究记录...</div>
      <EmptyState v-if="!loading && notes.length === 0" title="暂无研究记录" description="可以从证据详情页基于已读证据创建人工研究记录。" />
      <div v-else class="card-list">
        <article v-for="item in notes" :key="item.id" class="data-card">
          <div class="logic-header">
            <div>
              <router-link :to="'/research-notes/' + item.id" class="card-title">{{ item.title }}</router-link>
              <div class="summary-row">
                <span>{{ item.company_name || item.stock_code || '-' }}</span>
                <span>{{ noteTypeLabel(item.note_type) }}</span>
                <span>{{ directionLabel(item.conclusion_direction) }}</span>
                <span>{{ statusLabel(item.status) }}</span>
                <span>更新 {{ item.updated_at || '-' }}</span>
              </div>
            </div>
            <router-link :to="'/research-notes/' + item.id" class="secondary-link">查看详情</router-link>
          </div>
          <p>{{ item.summary || '暂无摘要' }}</p>
          <div class="summary-row">
            <span>引用证据 {{ item.evidence_count ?? 0 }}</span>
            <span>已确认 {{ item.reviewed_evidence_count ?? 0 }}</span>
            <span>未确认 {{ item.unreviewed_evidence_count ?? 0 }}</span>
            <span v-if="(item.reviewed_evidence_count ?? 0) < (item.evidence_count ?? 0)">包含未确认或未复核证据</span>
          </div>
        </article>
      </div>
    </section>`
}

export default ResearchNotes
