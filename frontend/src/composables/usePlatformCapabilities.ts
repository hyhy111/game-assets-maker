import { watch } from 'vue';
import { useAICreationStore } from '@/stores/aiCreation';
import { useAuthStore } from '@/stores/auth';

/**
 * 平台可售能力清单的**加载时机**（store 只管状态，时机由使用方驱动）。
 *
 * 为什么时机不放在 store 里：那会让工作区 store 隐式依赖并实例化 auth store——
 * 任何碰过工作区 store 的代码都会顺带触发 auth 的启动副作用。分开后依赖方向明确：
 * 创建页本来就同时依赖两者。
 *
 * 三个时机：
 *  - **切到平台源**：每次重新拉取（不读缓存）。运营随时可能在后台上下架模型、
 *    改定价或改展示名；读缓存会让用户对着一个已经下架/改名的模型发懵。
 *    切换源是低频的显式操作，一次只读请求的代价可以忽略。
 *  - **登录后**：若已选中平台源，同样重新拉取（换账号可能换了可见范围）。
 *  - **登出**：清空，避免把上一个账号的能力清单留给下一个人。
 *
 * 两个创建页各调一次是安全的：store 内部按 in-flight Promise 去重，
 * 同一时刻的重复调用只会发一次请求。
 */
export function usePlatformCapabilities() {
  const workspace = useAICreationStore();
  const auth = useAuthStore();

  watch(
    () => workspace.generationSource,
    (source) => {
      if (source !== 'forfuner-ai') return;
      if (!auth.isLoggedIn) return;
      void workspace.ensureCapabilities(true);
    },
  );

  watch(
    () => auth.isLoggedIn,
    (loggedIn) => {
      if (!loggedIn) {
        workspace.clearCapabilities();
        return;
      }
      if (workspace.generationSource === 'forfuner-ai') void workspace.ensureCapabilities(true);
    },
    { immediate: true },
  );

  return {
    /** 降级提示上的"重试"：强制重拉。 */
    reload: () => workspace.ensureCapabilities(true),
  };
}
