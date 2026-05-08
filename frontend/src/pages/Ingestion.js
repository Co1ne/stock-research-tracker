import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import EmptyState from '../components/EmptyState.js'
import { useCompanies } from '../composables/useCompanies.js'

const Ingestion = {
  components: { EmptyState },
  setup() {
    const { companies, loadCompanies } = useCompanies()
    const route = useRoute()
    const runs = ref([])
    const selectedRun = ref(null)
    const loading = ref(false)
    const error = ref('')
    const message = ref('')
    const filters = ref({ company_id: '', source_name: '', source_type: '', status: '' })
    const triggerCompanyId = ref('')

    async function load() {
      loading.value = true
      error.value = ''
      try {
        const query = new URLSearchParams()
        Object.entries(filters.value).forEach(([key, value]) => {
          if (value) query.set(key, value)
        })
        const data = await api(`/ingestion/runs${query.toString() ? `?${query.toString()}` : ''}`)
        runs.value = Array.isArray(data) ? data : []
      } catch (err) {
        error.value = err.message || '采集记录加载失败'
      } finally {
        loading.value = false
      }
    }

    async function loadDetail(item) {
      selectedRun.value = selectedRun.value?.id === item.id ? null : item
      if (!selectedRun.value) return
      try {
        selectedRun.value = await api(`/ingestion/runs/${item.id}`)
      } catch (err) {
        error.value = err.message || '采集详情加载失败'
      }
    }

    async function openRunById(id) {
      if (!id) return
      try {
        selectedRun.value = await api(`/ingestion/runs/${id}`)
      } catch (err) {
        error.value = err.message || '采集详情加载失败'
      }
    }

    async function triggerIngestion() {
      if (!triggerCompanyId.value) {
        error.value = '请选择要采集的公司'
        return
      }
      error.value = ''
      message.value = ''
      try {
        const result = await api(`/companies/${triggerCompanyId.value}/ingest`, {
          method: 'POST',
          body: JSON.stringify({ types: ['all'], force: false })
        })
        message.value = `采集已完成：${result.status}`
        await load()
      } catch (err) {
        error.value = err.message || '触发采集失败'
      }
    }

    function statusLabel(status) {
      return { success: '成功', partial_success: '部分成功', failed: '失败', skipped: '跳过' }[status] || status || '-'
    }

    function typeLabel(type) {
      return { announcement: '公告', news: '新闻', financial: '财务', company_profile: '公司资料' }[type] || type || '-'
    }

    function pretty(value) {
      if (!value) return '-'
      return JSON.stringify(value, null, 2)
    }

    onMounted(async () => {
      await loadCompanies()
      triggerCompanyId.value = companies.value[0]?.id || ''
      await load()
      await openRunById(route.query.run_id)
    })

    return { companies, runs, selectedRun, loading, error, message, filters, triggerCompanyId, load, loadDetail, triggerIngestion, statusLabel, typeLabel, pretty }
  },
  template: `
    <section class="page">
      <div class="page-header">
        <div><p class="eyebrow">Ingestion</p><h1>数据采集调试</h1></div>
        <button @click="load" :disabled="loading">刷新</button>
      </div>
      <p class="muted">查看公告、新闻、财务采集是否成功，定位失败来源。local 表示本地兜底数据，不代表外部真实来源。</p>
      <div v-if="message" class="notice ok">{{ message }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>

      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Manual Trigger</p><h2>手动触发采集</h2></div>
        </div>
        <div class="panel-form">
          <select v-model="triggerCompanyId">
            <option value="">选择公司</option>
            <option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option>
          </select>
          <button @click="triggerIngestion">采集全部类型</button>
        </div>
      </section>

      <section class="logic-panel">
        <div class="logic-header">
          <div><p class="eyebrow">Runs</p><h2>采集记录</h2></div>
        </div>
        <form class="panel-form" @submit.prevent="load">
          <select v-model="filters.company_id">
            <option value="">全部公司</option>
            <option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }} {{ company.code }}</option>
          </select>
          <select v-model="filters.source_name"><option value="">全部来源</option><option value="akshare">akshare</option><option value="local">local</option></select>
          <select v-model="filters.source_type"><option value="">全部类型</option><option value="announcement">公告</option><option value="news">新闻</option><option value="financial">财务</option></select>
          <select v-model="filters.status"><option value="">全部状态</option><option value="success">成功</option><option value="partial_success">部分成功</option><option value="failed">失败</option><option value="skipped">跳过</option></select>
          <button type="submit">筛选</button>
        </form>
        <div v-if="loading" class="notice">正在加载采集记录...</div>
        <EmptyState v-if="!loading && runs.length === 0" title="暂无采集记录" description="可先选择公司并触发采集，或等待定时任务执行。" />
        <div v-else class="card-list">
          <article v-for="item in runs" :key="item.id" class="data-card">
            <div class="logic-header">
              <div>
                <div class="card-title">{{ item.company_name || '全局采集' }} ｜ {{ item.source_name }} ｜ {{ typeLabel(item.source_type) }}</div>
                <div class="summary-row">
                  <span class="status-badge" :class="item.status">{{ statusLabel(item.status) }}</span>
                  <span>发现 {{ item.items_found ?? 0 }}</span>
                  <span>新增 {{ item.items_created ?? 0 }}</span>
                  <span>更新 {{ item.items_updated ?? 0 }}</span>
                  <span>{{ item.started_at || '-' }}</span>
                </div>
              </div>
              <button class="secondary" @click="loadDetail(item)">{{ selectedRun?.id === item.id ? '收起' : '详情' }}</button>
            </div>
            <p v-if="item.error_message" class="muted">错误：{{ item.error_message }}</p>
            <div v-if="selectedRun?.id === item.id" class="code-panel">
              <h3>请求参数</h3>
              <pre>{{ pretty(selectedRun.request_params) }}</pre>
              <h3>结果摘要</h3>
              <pre>{{ pretty(selectedRun.result_summary) }}</pre>
              <h3>原始错误</h3>
              <pre>{{ selectedRun.raw_error || '-' }}</pre>
              <h3>关联信息流</h3>
              <EmptyState v-if="!selectedRun.related_items?.feed_items?.length" title="暂无关联信息流" description="本次采集未创建或更新信息流记录，可能全部为重复数据。" />
              <div v-else class="mini-list">
                <div v-for="feed in selectedRun.related_items.feed_items" :key="'feed-' + feed.source_type + '-' + feed.id" class="mini-item">
                  <strong>{{ feed.company_name || '-' }}：{{ feed.title }}</strong>
                  <span>{{ typeLabel(feed.source_type) }} ｜ {{ feed.source_date || '-' }} ｜ 复核 {{ feed.review_status || '-' }}</span>
                  <router-link :to="'/companies/' + feed.company_id" class="secondary-link">公司详情</router-link>
                  <router-link v-if="feed.evidence_id" :to="'/evidence/' + feed.evidence_id" class="secondary-link">证据详情</router-link>
                </div>
              </div>
              <h3>关联证据</h3>
              <EmptyState v-if="!selectedRun.related_items?.evidence_items?.length" title="暂无关联证据" description="本次采集暂未生成证据，或证据来自历史采集。" />
              <div v-else class="mini-list">
                <router-link v-for="evidence in selectedRun.related_items.evidence_items" :key="'evidence-' + evidence.id" :to="'/evidence/' + evidence.id" class="mini-item">
                  <strong>{{ evidence.company_name || '-' }}：{{ evidence.title }}</strong>
                  <span>{{ typeLabel(evidence.source_type) }} ｜ {{ evidence.source_date || '-' }} ｜ {{ evidence.hypothesis_relation || '-' }} ｜ 复核 {{ evidence.review_status || '-' }}</span>
                </router-link>
              </div>
            </div>
          </article>
        </div>
      </section>
    </section>`
}

export default Ingestion
