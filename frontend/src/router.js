import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.js'
import Companies from './pages/Companies.js'
import CompanyDetail from './pages/CompanyDetail.js'
import Feed from './pages/Feed.js'
import Risks from './pages/Risks.js'
import Reports from './pages/Reports.js'
import Jobs from './pages/Jobs.js'
import Review from './pages/Review.js'
import Ingestion from './pages/Ingestion.js'
import EvidenceDetail from './pages/EvidenceDetail.js'
import ResearchNotes from './pages/ResearchNotes.js'
import ResearchNoteDetail from './pages/ResearchNoteDetail.js'
import ResearchNoteForm from './pages/ResearchNoteForm.js'
import ReportDraftNew from './pages/ReportDraftNew.js'
import DisciplineChecks from './pages/DisciplineChecks.js'
import DisciplineCheckForm from './pages/DisciplineCheckForm.js'
import NotFound from './pages/NotFound.js'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/companies', name: 'Companies', component: Companies },
  { path: '/companies/:id', name: 'CompanyDetail', component: CompanyDetail },
  { path: '/feed', name: 'Feed', component: Feed },
  { path: '/risks', name: 'Risks', component: Risks },
  { path: '/reports', name: 'Reports', component: Reports },
  { path: '/jobs', name: 'Jobs', component: Jobs },
  { path: '/review', name: 'Review', component: Review },
  { path: '/ingestion', name: 'Ingestion', component: Ingestion },
  { path: '/evidence/:id', name: 'EvidenceDetail', component: EvidenceDetail },
  { path: '/research-notes', name: 'ResearchNotes', component: ResearchNotes },
  { path: '/research-notes/new', name: 'ResearchNoteNew', component: ResearchNoteForm },
  { path: '/research-notes/:id', name: 'ResearchNoteDetail', component: ResearchNoteDetail },
  { path: '/report-drafts/new', name: 'ReportDraftNew', component: ReportDraftNew },
  { path: '/discipline-checks', name: 'DisciplineChecks', component: DisciplineChecks },
  { path: '/discipline-checks/new', name: 'DisciplineCheckNew', component: DisciplineCheckForm },
  { path: '/discipline-checks/:id', name: 'DisciplineCheckDetail', component: DisciplineCheckForm },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: NotFound }
]

const router = createRouter({ history: createWebHistory(), routes })

export default router
