import { createPinia } from 'pinia';
import { createSSRApp, h } from 'vue';
import { createI18n } from 'vue-i18n';
import { createMemoryHistory, createRouter } from 'vue-router';
import { renderToString } from '@vue/server-renderer';
import { createServer } from 'vite';
import en from '../src/locales/en.ts';
import zhCN from '../src/locales/zh-CN.ts';

// Issue #6 close-warning copy and Issue #7 board/detail copy. The main agent
// merges these into the locale files; tests assert the rendered text, so merge
// them here until the locales own them.
const seedreamTestMessages = {
  'zh-CN': {
    seedream: {
      close: {
        title: '图片生成仍在进行',
        body: '当前有 {count} 张图片正在生成。现在退出后将无法恢复生成结果，并且请求可能已经产生费用。',
        continue: '继续等待',
        exit: '仍然退出',
      },
      board: {
        title: '图片生成看板',
        subtitle: '查看所有图片生成批次',
        create: '新建生成',
        empty: '还没有图片生成批次。创建第一个批次开始生成候选图片。',
        untitled: '（无提示词）',
        countLabel: '{count} 张',
        viewDetail: '查看详情',
      },
      detail: {
        regenerate: '再次生成',
        delete: '删除批次',
        deleteConfirmation: '确认删除此批次及其所有本地图片缓存？此操作不可撤销，且不会删除单张图片。',
        deleteFailed: '删除失败，请稍后重试。',
        dimensions: '实际尺寸',
      },
    },
  },
  en: {
    seedream: {
      close: {
        title: 'Image generation in progress',
        body: '{count} image(s) are still generating. If you exit now, the results cannot be recovered and the requests may have already incurred charges.',
        continue: 'Keep waiting',
        exit: 'Exit anyway',
      },
      board: {
        title: 'Image Generation Board',
        subtitle: 'View all image generation batches',
        create: 'New Batch',
        empty: 'No image generation batches yet. Create one to start generating candidate images.',
        untitled: '(no prompt)',
        countLabel: '{count} image(s)',
        viewDetail: 'View details',
      },
      detail: {
        regenerate: 'Regenerate',
        delete: 'Delete Batch',
        deleteConfirmation: 'Delete this batch and all its local image cache? This cannot be undone and does not delete individual images.',
        deleteFailed: 'Deletion failed. Please try again.',
        dimensions: 'Dimensions',
      },
    },
  },
};

function withSeedreamTestMessages(localeMessages, locale) {
  const override = seedreamTestMessages[locale];
  if (!localeMessages || !override) return localeMessages;
  const existing = localeMessages.seedream || {};
  return {
    ...localeMessages,
    seedream: {
      ...existing,
      close: { ...(existing.close || {}), ...override.seedream.close },
      board: { ...(existing.board || {}), ...override.seedream.board },
      detail: { ...(existing.detail || {}), ...override.seedream.detail },
    },
  };
}

const testStorage = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => testStorage.get(key) ?? null,
    setItem: (key, value) => testStorage.set(key, String(value)),
  },
});

let vite;

async function getVite() {
  vite ??= await createServer({
    appType: 'custom',
    logLevel: 'silent',
    server: { middlewareMode: true },
  });
  return vite;
}

export async function renderSfc(path, {
  props = {},
  slots = {},
  route = '/',
  piniaState = {},
  configureSetup,
} = {}) {
  const server = await getVite();
  const module = await server.ssrLoadModule(`/src/${path}`);
  const component = configureSetup ? {
    ...module.default,
    setup(props, context) {
      const bindings = module.default.setup(props, context);
      configureSetup(bindings);
      return bindings;
    },
  } : module.default;
  const app = createSSRApp({ render: () => h(component, props, slots) });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { render: () => null } },
      { path: '/ai-creation', component: { render: () => null } },
      { path: '/ai-creation/settings', component: { render: () => null } },
      { path: '/video-generation/create', component: { render: () => null } },
      { path: '/video-generation/tasks', component: { render: () => null } },
      { path: '/video-generation/preview', component: { render: () => null } },
      { path: '/video-generation/tasks/:localTaskId', component: { render: () => null } },
      { path: '/video-generation/settings', component: { render: () => null } },
      { path: '/image-generation/create', component: { render: () => null } },
      { path: '/image-generation/batches', component: { render: () => null } },
      { path: '/image-generation/batches/:batchId', component: { render: () => null } },
      { path: '/image-generation/settings', component: { render: () => null } },
    ],
  });
  await router.push(route);
  await router.isReady();
  const pinia = createPinia();
  pinia.state.value = piniaState;
  app.use(pinia);
  app.use(router);
  app.use(createI18n({
    legacy: false,
    locale: 'zh-CN',
    fallbackLocale: 'en',
    messages: {
      'zh-CN': withSeedreamTestMessages(zhCN, 'zh-CN'),
      en: withSeedreamTestMessages(en, 'en'),
    },
  }));
  return renderToString(app);
}

export async function closeSfcRenderer() {
  await vite?.close();
  vite = undefined;
}
