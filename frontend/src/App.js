const App = {
  setup() {
    return {
      navItems: [
        { to: '/', label: 'Dashboard' },
        { to: '/companies', label: '自选股' },
        { to: '/feed', label: '信息流' },
        { to: '/risks', label: '风险事件' },
        { to: '/reports', label: '报告中心' },
        { to: '/jobs', label: '任务状态' }
      ]
    }
  },
  template: `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand">Stock Research</div>
        <nav><router-link v-for="item in navItems" :key="item.to" :to="item.to">{{ item.label }}</router-link></nav>
      </aside>
      <main class="main-content"><router-view /></main>
    </div>`
}

export default App
