import { onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAICreationStore } from '@/stores/aiCreation';
import { useAuthStore } from '@/stores/auth';
import type { PlatformCapabilities } from '@/types';

type MediaKind = 'video' | 'image';

/**
 * 直连源（自付 API Key）的模型名仍来自本地词条——那是客户端自己的预设表，
 * 与平台侧无关。平台源的模型**不在这里**，它的名字由服务端下发。
 */
const LOCAL_LABEL_KEYS: Record<MediaKind, Record<string, string>> = {
  video: {
    standard: 'seedance.models.standard',
    fast: 'seedance.models.fast',
    mini: 'seedance.models.mini',
  },
  image: {
    pro: 'seedream.models.pro',
    flash: 'seedream.models.flash',
    lite: 'seedream.models.lite',
  },
};

function serverDisplayName(capabilities: PlatformCapabilities | null, model: string): string | null {
  if (!capabilities) return null;
  const entries = [...(capabilities.video?.models ?? []), ...(capabilities.image?.models ?? [])];
  const hit = entries.find((entry) => entry.model === model);
  const name = hit?.displayName?.trim();
  return name ? name : null;
}

/**
 * 把任务/批次里存的模型标识解析成给用户看的名字。
 *
 * 解析顺序（任一步命中即返回）：
 *  1. **服务端下发的展示名**——平台源的模型标识是 Ark ID，名字只有服务端知道
 *  2. 本地词条——直连源的短键（standard/pro…）
 *  3. 原样显示模型标识——宁可用 ID，也不能显示成坏掉的词条 key
 *
 * 第 3 步是关键：此前直接写 `t(\`seedance.models.${model}\`)`，平台源下会命中
 * 不存在的词条，vue-i18n 把 **key 本身**当文案返回，界面上就会出现
 * `seedance.models.doubao-seedance-2-0-260128` 这种东西。
 */
export function useModelDisplayName() {
  const workspace = useAICreationStore();
  const auth = useAuthStore();
  const { t } = useI18n();

  // 详情页/任务列表也要能显示服务端名字，所以这一层自己把能力清单拉起来
  // （store 内部按 in-flight 去重，重复调用不会多发请求）。
  onMounted(() => {
    if (auth.isLoggedIn) void workspace.ensureCapabilities();
  });

  function modelName(model: string | null | undefined, kind: MediaKind): string {
    if (!model) return '';
    const fromServer = serverDisplayName(workspace.capabilities, model);
    if (fromServer) return fromServer;

    const key = LOCAL_LABEL_KEYS[kind][model];
    if (key) {
      const text = t(key);
      // t() 在词条缺失时返回 key 本身——那种情况下退回模型标识，别把 key 当文案渲染
      if (text && text !== key) return text;
    }
    return model;
  }

  return { modelName };
}
