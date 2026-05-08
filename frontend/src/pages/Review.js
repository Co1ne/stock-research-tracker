import { onMounted, reactive, ref } from 'vue'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'

const Review = {
  components: { EmptyState },
  setup() {
    const items = ref([])
    const loading = ref(false)
    const error = ref('')
    const message = ref('')
    const drafts = reactive({})

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const data = await api('/review/pending')
        items.value = Array.isArray(data) ? data : []
        items.value.forEach((item) => {
          if (!drafts[item.id]) {
            drafts[item.id] = {
              note: '',
              edited_content: item.edited_content || item.summary || item.reason || item.content || '',
              hypothesis_id: item.hypothesis_id || null,
              hypothesis_relation: item.hypothesis_relation || 'watch',
              impact_direction: item.impact_direction || item.direction || 'unknown',
              impact_strength: item.impact_strength || 'low',
              affected_aspect: item.affected_aspect || 'other',
              evidence_summary: item.evidence_summary || item.summary || item.reason || item.content || '',
              relation_note: item.relation_note || ''
            }
          }
        })
      } catch (err) {
        error.value = err.message || '待复核列表加载失败'
      } finally {
        loading.value = false
      }
    }

    async function decide(item, status) {
      error.value = ''
      message.value = ''
      try {
        const draft = drafts[item.id] || { note: '', edited_content: '' }
        const relationPayload = status === 'rejected' ? {} : {
          hypothesis_id: draft.hypothesis_id,
          hypothesis_relation: draft.hypothesis_relation,
          impact_direction: draft.impact_direction,
          impact_strength: draft.impact_strength,
          affected_aspect: draft.affected_aspect,
          evidence_summary: draft.evidence_summary,
          relation_note: draft.relation_note
        }
        await api(`/review/items/${item.id}/decision`, {
          method: 'POST',
          body: JSON.stringify({
            status,
            note: draft.note,
            edited_content: draft.edited_content,
            ...relationPayload
          })
        })
        message.value = status === 'approved' ? '已确认复核项。' : status === 'rejected' ? '已驳回复核项。' : '已保存人工修改。'
        await load()
      } catch (err) {
        error.value = err.message || '复核提交失败'
      }
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

    function typeLabel(type) {
      return {
        announcement: '公告',
        news: '新闻',
        financial: '财务',
        evidence: '证据'
      }[type] || type || '复核项'
    }

    function statusLabel(status) {
      return {
        pending: '待复核',
        approved: '已确认',
        rejected: '已驳回',
        edited: '人工修改后确认'
      }[status] || '待复核'
    }

    function sourceLabel(name) {
      return { akshare: 'AKShare', local: '本地 fallback' }[name] || name || '未记录来源'
    }

    function ingestionStatusLabel(status) {
      return { success: '采集成功', partial_success: '部分成功', failed: '采集失败', skipped: '跳过' }[status] || '无采集记录'
    }

    onMounted(load)
    return { items, loading, error, message, drafts, load, decide, typeLabel, statusLabel, relationLabel, sourceLabel, ingestionStatusLabel }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div>
          <p class="eyebrow">Manual Review</p>
          <h1>人工复核</h1>
        </div>
        <button @click="load" :disabled="loading">刷新</button>
      </div>
      <p class="muted">对系统沉淀的证据进行确认、驳回或人工修正。这里不输出买卖建议，只记录可追溯的投研判断。</p>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>
      <div v-if="loading" class="notice">正在加载待复核项目...</div>
      <EmptyState v-if="!loading && items.length === 0" title="暂无待复核项目" description="风险证据、不确定证据或需人工确认的信息会进入这里。" />
      <div v-else class="card-list">
        <article v-for="item in items" :key="item.id" class="data-card review-card">
          <div class="logic-header">
            <div>
              <div class="card-title">{{ item.title || item.source_title || '-' }}</div>
              <div class="summary-row">
                <span>{{ item.company_name || item.stock_code || '-' }}</span>
                <span>{{ typeLabel(item.source_type || item.type) }}</span>
                <span>{{ item.business_line_name || '未归因' }}</span>
                <span>{{ relationLabel(item.hypothesis_relation) }}</span>
                <span>{{ item.impact_direction || 'unknown' }}</span>
                <span>{{ item.impact_strength || 'low' }}</span>
                <span>{{ item.affected_aspect || 'other' }}</span>
                <span class="status-badge pending">{{ statusLabel(item.review_status) }}</span>
              </div>
            </div>
            <router-link v-if="item.company_id" :to="'/companies/' + item.company_id" class="secondary-link">查看公司</router-link>
          </div>
          <p>{{ item.summary || item.reason || item.content || '暂无摘要' }}</p>
          <p class="muted">来源：{{ item.source_title || item.source || '-' }} ｜ 创建：{{ item.created_at || '-' }}</p>
          <div class="summary-row">
            <span>数据源 {{ sourceLabel(item.source_name) }}</span>
            <span>来源类型 {{ typeLabel(item.source_type || item.type) }}</span>
            <span>来源日期 {{ item.source_date || '-' }}</span>
            <span>{{ ingestionStatusLabel(item.ingestion_status) }}</span>
            <router-link v-if="item.ingestion_run_id" :to="'/ingestion?run_id=' + item.ingestion_run_id" class="secondary-link">采集批次 #{{ item.ingestion_run_id }}</router-link>
            <span v-else>无采集记录</span>
            <span v-if="item.is_fallback_source">本地来源</span>
          </div>
          <label class="field-label" :for="'note-' + item.id">复核备注</label>
          <textarea :id="'note-' + item.id" v-model="drafts[item.id].note" rows="2" placeholder="例如：确认有效、来源不可靠、需要继续跟踪..." />
          <label class="field-label" :for="'edit-' + item.id">人工修正内容</label>
          <textarea :id="'edit-' + item.id" v-model="drafts[item.id].edited_content" rows="4" placeholder="如需修正系统摘要，可在这里编辑后确认。" />
          <div class="panel-form review-relation-form">
            <label><span class="field-label">与假设关系</span><select v-model="drafts[item.id].hypothesis_relation"><option value="supports">支持假设</option><option value="contradicts">反驳假设</option><option value="neutral">中性相关</option><option value="watch">需要观察</option><option value="unrelated">无关</option></select></label>
            <label><span class="field-label">影响方向</span><select v-model="drafts[item.id].impact_direction"><option value="positive">正面</option><option value="negative">负面</option><option value="neutral">中性</option><option value="unknown">未知</option></select></label>
            <label><span class="field-label">影响强度</span><select v-model="drafts[item.id].impact_strength"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
            <label><span class="field-label">影响维度</span><select v-model="drafts[item.id].affected_aspect"><option value="revenue">收入</option><option value="profit">利润</option><option value="margin">毛利率</option><option value="cashflow">现金流</option><option value="order">订单</option><option value="shareholder">股东行为</option><option value="valuation">估值</option><option value="industry">行业</option><option value="policy">政策</option><option value="risk">风险</option><option value="business_line">业务线</option><option value="other">其他</option></select></label>
            <label><span class="field-label">证据摘要</span><textarea v-model="drafts[item.id].evidence_summary" rows="3" placeholder="这条证据说明了什么"></textarea></label>
            <label><span class="field-label">关系说明</span><textarea v-model="drafts[item.id].relation_note" rows="3" placeholder="为什么认为它支持、反驳或需要观察"></textarea></label>
          </div>
          <div class="action-row">
            <router-link :to="'/evidence/' + item.id" class="secondary-link">查看详情</router-link>
            <button @click="decide(item, 'approved')">确认</button>
            <button class="secondary" @click="decide(item, 'rejected')">驳回</button>
            <button class="secondary" @click="decide(item, 'edited')">编辑后确认</button>
          </div>
        </article>
      </div>
    </section>`
}

export default Review
