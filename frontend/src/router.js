import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.js'
import Companies from './pages/Companies.js'
import CompanyDetail from './pages/CompanyDetail.js'
import Feed from './pages/Feed.js'
import Risks from './pages/Risks.js'
import Reports from './pages/Reports.js'
import Jobs from './pages/Jobs.js'
import NotFound from './pages/NotFound.js'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/companies', name: 'Companies', component: Companies },
  { path: '/companies/:id', name: 'CompanyDetail', component: CompanyDetail },
  { path: '/feed', name: 'Feed', component: Feed },
  { path: '/risks', name: 'Risks', component: Risks },
  { path: '/reports', name: 'Reports', component: Reports },
  { path: '/jobs', name: 'Jobs', component: Jobs },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound }
]

const router = createRouter({ history: createWebHistory(), routes })

export default router
