import { createApp, ref, onMounted } from 'vue'

const App = {
  setup() {
    const companyId = ref(1)
    const summary = ref(null)
    const evidence = ref([])
    const load = async () => {
      summary.value = await (await fetch(`/api/companies/${companyId.value}/logic-summary`)).json()
      evidence.value = await (await fetch(`/api/companies/${companyId.value}/evidence`)).json()
    }
    const analyzeAnnouncement = async () => {
      const id = prompt('输入公告ID')
      if (!id) return
      await fetch(`/api/announcements/${id}/analyze-logic`, { method: 'POST' })
      await load()
    }
    onMounted(load)
    return { companyId, summary, evidence, analyzeAnnouncement, load }
  },
  template: `<main style='max-width:980px;margin:24px auto;font-family:Arial'>
  <h1>投资逻辑验证</h1>
  <button @click='analyzeAnnouncement'>AI 分析逻辑影响（公告）</button>
  <button @click='load'>刷新</button>
  <div v-if='summary'>
    <h3>最近30天逻辑状态</h3>
    <p>正面: {{summary.positive_count}} 负面: {{summary.negative_count}} 风险: {{summary.risk_count}} 总体: {{summary.overall_status}}</p>
    <h3>按业务线</h3>
    <ul><li v-for='line in summary.business_lines'>{{line.name}} / +{{line.positive_count}} / -{{line.negative_count}} / {{line.latest_evidence.join('；')}}</li></ul>
  </div>
  <h3>证据列表</h3>
  <table border='1' cellpadding='6'><tr><th>标题</th><th>方向</th><th>类型</th><th>置信度</th><th>原因</th></tr>
  <tr v-for='e in evidence'><td>{{e.title}}</td><td>{{e.direction}}</td><td>{{e.evidence_type}}</td><td>{{e.confidence}}</td><td>{{e.reason}}</td></tr></table>
  </main>`
}
createApp(App).mount('#app')
