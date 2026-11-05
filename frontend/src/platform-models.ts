import type { PlatformModelCapability } from '@/types';

/**
 * 平台源模型下拉项的构造。
 *
 * 单独成模块（而不是放进 seedance-ui / seedream-ui）有两个原因：
 *  1. 视频与图片两个源的构造逻辑完全一致，放一处避免两份实现漂移；
 *  2. 放在某个 ui 模块里会让另一个模块产生**运行时**跨模块依赖，
 *     而测试用 Node 的类型剥离直接跑 .ts，相对导入必须带扩展名——
 *     共享模块把这个问题绕开了。
 */

export interface ModelOption {
  value: string;
  label: string;
  disabled?: boolean;
  reason?: string;
}

/**
 * 展示名优先，为空（字段引入前的历史数据）回退真实模型标识。
 *
 * 客户端**不再内置平台源的模型名映射**：运营在后台填了展示名，
 * 新模型就能直接出现在下拉框里，无需改客户端发版。
 */
export function modelDisplayName(entry: { model: string; displayName?: string }): string {
  const name = typeof entry.displayName === 'string' ? entry.displayName.trim() : '';
  return name || entry.model;
}

/**
 * 平台源模型下拉项：`value` 是建单用的上游模型 ID，`label` 是用户在界面上看到的名字。
 *
 * 清单为空（未加载/拉取失败）时返回空数组——**绝不回退到本地预设表**，
 * 否则会把"选中后必然失败"的组合重新放出来（见 gam-platform-capabilities design D3）。
 */
export function platformModelOptions(
  models: readonly PlatformModelCapability[] | null | undefined,
): ModelOption[] {
  return (models ?? []).map((entry) => ({
    value: entry.model,
    label: modelDisplayName(entry),
  }));
}
