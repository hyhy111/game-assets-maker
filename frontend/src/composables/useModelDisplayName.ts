import { onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAICreationStore } from '@/stores/aiCreation';
import { useAuthStore } from '@/stores/auth';
import type { PlatformCapabilities } from '@/types';

type MediaKind = 'video' | 'image';

// Include exact model IDs saved by older clients so task history has labels offline.
const LOCAL_LABEL_KEYS: Record<MediaKind, Record<string, string>> = {
  video: {
    standard: 'seedance.models.standard',
    fast: 'seedance.models.fast',
    mini: 'seedance.models.mini',
    'doubao-seedance-2-0-260128': 'seedance.models.standard',
    'doubao-seedance-2-0-fast-260128': 'seedance.models.fast',
    'doubao-seedance-2-0-mini-260615': 'seedance.models.mini',
  },
  image: {
    pro: 'seedream.models.pro',
    flash: 'seedream.models.flash',
    lite: 'seedream.models.lite',
    'doubao-seedream-5-0-pro-260628': 'seedream.models.pro',
    'doubao-seedream-5-0-flash-260915': 'seedream.models.flash',
    'doubao-seedream-5-0-260128': 'seedream.models.lite',
  },
};

function serverDisplayName(capabilities: PlatformCapabilities | null, model: string): string | null {
  if (!capabilities) return null;
  const entries = [...(capabilities.video?.models ?? []), ...(capabilities.image?.models ?? [])];
  const hit = entries.find((entry) => entry.model === model);
  const name = hit?.displayName?.trim();
  return name ? name : null;
}

/** Prefer the current platform name, then a local label, then the saved ID. */
export function useModelDisplayName() {
  const workspace = useAICreationStore();
  const auth = useAuthStore();
  const { t } = useI18n();

  // 详情页/任务列表也要能显示服务端名字，所以这一层自己把能力清单拉起来
  // （store 内部按 in-flight 去重，重复调用不会多发请求）。
  onMounted(() => {
    if (auth.isLoggedIn) void workspace.ensureCapabilities();
  });

  function modelName(model: string | null | undefined, kind?: MediaKind): string {
    if (!model) return '';
    const fromServer = serverDisplayName(workspace.capabilities, model);
    if (fromServer) return fromServer;

    const key = kind ? LOCAL_LABEL_KEYS[kind][model] : (LOCAL_LABEL_KEYS.video[model] ?? LOCAL_LABEL_KEYS.image[model]);
    if (key) {
      const text = t(key);
      // t() 在词条缺失时返回 key 本身——那种情况下退回模型标识，别把 key 当文案渲染
      if (text && text !== key) return text;
    }
    return model;
  }

  return { modelName };
}
