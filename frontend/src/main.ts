import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './styles/main.css'
import i18n from './locales'
import { useProcessStore } from '@/stores/process'
import { useSeedanceStore } from '@/stores/seedance'
import { useSeedreamStore } from '@/stores/seedream'
import { useAuthStore } from '@/stores/auth'

// Views
import ProjectManager from './views/ProjectManager.vue'
import ProjectCreate from './views/ProjectCreate.vue'
import EditorLayout from './views/Editor/EditorLayout.vue'
import BatchTrim from './views/BatchTrim.vue'

const routes = [
  { path: '/', component: ProjectManager },
  {
    path: '/login',
    component: () => import('./views/Login.vue'),
    beforeEnter: () => (useAuthStore().isLoggedIn ? { path: '/' } : true)
  },
  {
    path: '/register',
    component: () => import('./views/Register.vue'),
    beforeEnter: () => (useAuthStore().isLoggedIn ? { path: '/' } : true)
  },
  { path: '/create', component: ProjectCreate },
  { path: '/editor', component: EditorLayout },
  { path: '/batch-trim', component: BatchTrim },
  { path: '/ai-creation', component: () => import('./views/AICreationWorkspace.vue') },
  { path: '/ai-creation/settings', component: () => import('./views/SeedanceSettings.vue') },
  { path: '/video-generation/create', redirect: (to: { query: Record<string, unknown> }) => ({ path: '/ai-creation', query: { ...to.query, mode: 'video' } }) },
  { path: '/video-generation/tasks', redirect: { path: '/ai-creation', query: { mode: 'video' } } },
  { path: '/video-generation/preview', redirect: { path: '/ai-creation', query: { mode: 'video' } } },
  { path: '/video-generation/tasks/:localTaskId', component: () => import('./views/SeedancePreview.vue') },
  { path: '/video-generation/settings', redirect: '/ai-creation/settings' },
  { path: '/image-generation/create', redirect: (to: { query: Record<string, unknown> }) => ({ path: '/ai-creation', query: { ...to.query, mode: 'image' } }) },
  { path: '/image-generation/batches', redirect: { path: '/ai-creation', query: { mode: 'image' } } },
  { path: '/image-generation/batches/:batchId', component: () => import('./views/SeedreamBatchDetail.vue') },
  { path: '/image-generation/batch-detail', redirect: { path: '/ai-creation', query: { mode: 'image' } } },
  { path: '/image-generation/settings', redirect: '/ai-creation/settings' }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

const pinia = createPinia()

const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(i18n)
app.mount('#app')

// Initialize progress listeners after app mount
const processStore = useProcessStore()
processStore.initProgressListeners()

const seedanceStore = useSeedanceStore()
seedanceStore.initEventListeners()

const seedreamStore = useSeedreamStore()
seedreamStore.initEventListeners()
