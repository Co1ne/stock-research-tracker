import { onMounted, ref } from 'vue'
import { api } from '../api/client.js'
import { useCompanies } from '../composables/useCompanies.js'
import EmptyState from '../components/EmptyState.js'

const Companies = {
  components: { EmptyState },
  setup() {
    const { companies, loading, error, loadCompanies } = useCompanies()
    const form = ref({ code: '', name: '', thesis: '', disproof_conditions: '' })
    const saving = ref(false)
    const init = ref({ code: '', market: '' })
    const initLoading = ref(false)
    const initError = ref('')
    const initMessage = ref('')
    const initTask = ref(null)
    const initResult = ref(null)
    const initStep = ref('input')

    async function createCompany() {
      if (!form.value.code.trim() || !form.value.name.trim()) return
      saving.value = true
      error.value = ''
      try {
        await api('/companies', {
          method: 'POST',
          body: JSON.stringify({
            code: form.value.code.trim(),
            name: form.value.name.trim(),
            market: 'A',
            status: 'watching',
            thesis: form.value.thesis.trim() || null,
            disproof_conditions: form.value.disproof_conditions.trim() || null
          })
        })
        form.value = { code: '', name: '', thesis: '', disproof_conditions: '' }
        await loadCompanies()
      } catch (err) {
        error.value = err.message || '新增公司失败'
      } finally {
        saving.value = false
      }
    }

    function prepareDraft(result) {
      const copy = JSON.parse(JSON.stringify(result || {}))
      copy.basic_info = copy.basic_info || { code: init.value.code, name: '', market: '', industry: '', main_business: '' }
      copy.recent_announcements = copy.recent_announcements || []
      copy.recent_news = copy.recent_news || []
      copy.financial_summary = copy.financial_summary || {}
      copy.draft_disproof_text = (copy.draft_disproof_conditions || []).join('\n')
      copy.draft_business_lines = (copy.draft_business_lines || []).map((line) => ({
        ...line,
        keywords_text: (line.keywords || []).join(', '),
        key_metrics_text: (line.key_metrics || []).join(', ')
      }))
      return copy
    }

    async function startInitialize() {
      if (!init.value.code.trim()) {
        initError.value = '请输入股票代码'
        return
      }
      initLoading.value = true
      initError.value = ''
      initMessage.value = ''
      initTask.value = null
      initResult.value = null
      initStep.value = 'running'
      try {
        const started = await api('/companies/initialize', {
          method: 'POST',
          body: JSON.stringify({ code: init.value.code.trim(), market: init.value.market.trim() || null })
        })
        initTask.value = started
        const status = await api(`/companies/initialize/${started.task_id}`)
        initTask.value = status
        initResult.value = prepareDraft(status.result)
        initStep.value = 'confirm'
        if (status.status === 'failed') {
          initError.value = status.error_message || '初始化部分失败，可编辑草案或只保存基础信息。'
        }
      } catch (err) {
        initStep.value = 'manual'
        initError.value = err.message || '初始化失败，可手动创建公司。'
        form.value.code = init.value.code
      } finally {
        initLoading.value = false
      }
    }

    function addDraftLine() {
      if (!initResult.value) return
      initResult.value.draft_business_lines.push({ name: '', role: '', description: '', keywords_text: '', key_metrics_text: '', confidence: 'low', source: 'manual' })
    }

    function removeDraftLine(index) {
      initResult.value?.draft_business_lines.splice(index, 1)
    }

    async function confirmInitialize(saveResearch = true) {
      if (!initTask.value?.task_id || !initResult.value) return
      saving.value = true
      initError.value = ''
      try {
        const payload = {
          basic_info: initResult.value.basic_info,
          draft_thesis: initResult.value.draft_thesis,
          draft_disproof_conditions: (initResult.value.draft_disproof_text || '').split('\n').map((item) => item.trim()).filter(Boolean),
          draft_business_lines: initResult.value.draft_business_lines.map((line) => ({
            name: line.name,
            role: line.role,
            description: line.description,
            keywords: (line.keywords_text || '').split(',').map((item) => item.trim()).filter(Boolean),
            key_metrics: (line.key_metrics_text || '').split(',').map((item) => item.trim()).filter(Boolean),
            confidence: line.confidence || 'low',
            source: line.source || 'manual'
          })),
          save_research: saveResearch
        }
        const result = await api(`/companies/initialize/${initTask.value.task_id}/confirm`, { method: 'POST', body: JSON.stringify(payload) })
        initMessage.value = `已保存公司，ID: ${result.company_id}`
        initStep.value = 'done'
        await loadCompanies()
      } catch (err) {
        initError.value = err.message || '保存初始化结果失败'
      } finally {
        saving.value = false
      }
    }

    onMounted(loadCompanies)
    return { companies, loading, error, form, saving, createCompany, init, initLoading, initError, initMessage, initTask, initResult, initStep, startInitialize, addDraftLine, removeDraftLine, confirmInitialize }
  },
  template: `
    <section class="page">
      <div class="page-header"><div><p class="eyebrow">Watchlist</p><h1>自选股</h1><p class="muted">只输入股票代码，系统会尝试补全公司资料并生成投研草案。</p></div></div>

      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Smart Setup</p><h2>智能初始化公司</h2></div>
          <span class="status-badge" :class="initStep">{{ initStep === 'input' ? '输入代码' : initStep === 'running' ? '初始化中' : initStep === 'confirm' ? '确认草案' : initStep === 'done' ? '已保存' : '手动兜底' }}</span>
        </div>
        <form class="toolbar" @submit.prevent="startInitialize">
          <input v-model="init.code" placeholder="股票代码，如 002920" />
          <input v-model="init.market" placeholder="市场可选，如 SZ / SH" />
          <button type="submit" :disabled="initLoading">{{ initLoading ? '初始化中' : '开始初始化' }}</button>
        </form>
        <div class="step-list">
          <span :class="{ active: initStep === 'input' }">1 输入代码</span>
          <span :class="{ active: initStep === 'running' }">2 自动初始化</span>
          <span :class="{ active: initStep === 'confirm' }">3 草案确认</span>
          <span :class="{ active: initStep === 'done' }">4 保存结果</span>
        </div>
        <div v-if="initTask?.result?.stages?.length" class="mini-list">
          <div v-for="stage in initTask.result.stages" :key="stage.stage" class="mini-item">
            <strong>{{ stage.stage }}</strong>
            <span class="status-badge" :class="stage.status">{{ stage.status }}</span>
          </div>
        </div>
        <div v-if="initError" class="notice error">{{ initError }}</div>
        <div v-if="initMessage" class="notice ok">{{ initMessage }}</div>

        <div v-if="initResult && initStep === 'confirm'" class="draft-review">
          <h3>公司基础信息</h3>
          <div class="panel-form">
            <input v-model="initResult.basic_info.code" placeholder="股票代码" />
            <input v-model="initResult.basic_info.name" placeholder="公司名称" />
            <input v-model="initResult.basic_info.market" placeholder="市场" />
            <input v-model="initResult.basic_info.industry" placeholder="行业" />
            <textarea v-model="initResult.basic_info.main_business" placeholder="主营业务简介"></textarea>
          </div>
          <h3>投资逻辑草案</h3>
          <textarea v-model="initResult.draft_thesis" placeholder="系统生成的投资逻辑草案"></textarea>
          <h3>证伪条件 / 风险关注点</h3>
          <textarea v-model="initResult.draft_disproof_text" placeholder="每行一个关注点"></textarea>
          <h3>业务线草案</h3>
          <div class="card-list">
            <article v-for="(line, index) in initResult.draft_business_lines" :key="index" class="data-card">
              <div class="panel-form">
                <input v-model="line.name" placeholder="业务线名称" />
                <input v-model="line.role" placeholder="角色，如 core / growth" />
                <textarea v-model="line.description" placeholder="业务线描述"></textarea>
                <input v-model="line.keywords_text" placeholder="关键词，逗号分隔" />
                <input v-model="line.key_metrics_text" placeholder="关注指标，逗号分隔" />
                <select v-model="line.confidence"><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select>
                <button type="button" @click="removeDraftLine(index)">移除</button>
              </div>
            </article>
          </div>
          <button type="button" class="secondary-button" @click="addDraftLine">增加业务线</button>
          <h3>最近重要信息</h3>
          <div class="logic-columns">
            <div>
              <h3>公告</h3>
              <EmptyState v-if="initResult.recent_announcements.length === 0" title="暂无公告" description="数据源未返回最近公告或抓取失败。" />
              <div v-else class="mini-list"><div v-for="item in initResult.recent_announcements.slice(0, 5)" :key="item.title" class="mini-item">{{ item.title }}</div></div>
            </div>
            <div>
              <h3>新闻</h3>
              <EmptyState v-if="initResult.recent_news.length === 0" title="暂无新闻" description="数据源未返回相关新闻或抓取失败。" />
              <div v-else class="mini-list"><div v-for="item in initResult.recent_news.slice(0, 5)" :key="item.title" class="mini-item">{{ item.title }}</div></div>
            </div>
          </div>
          <h3>财务摘要</h3>
          <div class="summary-row">
            <span>报告期 {{ initResult.financial_summary.report_period || '暂缺' }}</span>
            <span>营收 {{ initResult.financial_summary.revenue ?? '暂缺' }}</span>
            <span>净利润 {{ initResult.financial_summary.net_profit ?? '暂缺' }}</span>
            <span>经营现金流 {{ initResult.financial_summary.operating_cash_flow ?? '暂缺' }}</span>
          </div>
          <div class="action-row">
            <button type="button" @click="confirmInitialize(true)" :disabled="saving">确认使用草案</button>
            <button type="button" @click="confirmInitialize(false)" :disabled="saving">只保存基础信息</button>
          </div>
        </div>
      </section>

      <h2>手动创建兜底</h2>
      <form class="toolbar" @submit.prevent="createCompany">
        <input v-model="form.code" placeholder="股票代码，如 600519" />
        <input v-model="form.name" placeholder="公司名称" />
        <textarea v-model="form.thesis" placeholder="投资逻辑，可选"></textarea>
        <textarea v-model="form.disproof_conditions" placeholder="证伪条件，可选"></textarea>
        <button type="submit" :disabled="saving">新增</button>
      </form>
      <div v-if="error" class="notice error">{{ error }}</div>
      <EmptyState v-if="!loading && companies.length === 0" title="暂无公司" description="新增公司后会显示在这里。" />
      <div class="table-wrap" v-else>
        <table>
          <thead><tr><th>代码</th><th>名称</th><th>市场</th><th>状态</th><th></th></tr></thead>
          <tbody>
            <tr v-for="company in companies" :key="company.id">
              <td>{{ company.code }}</td><td>{{ company.name }}</td><td>{{ company.market || '-' }}</td><td>{{ company.status || '-' }}</td>
              <td><router-link :to="'/companies/' + company.id">详情</router-link></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>`
}

export default Companies
