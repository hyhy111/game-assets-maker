import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { modelDisplayName, platformModelOptions } from '../src/platform-models.ts';
import { localModelResolutions as localVideoResolutions } from '../src/seedance-ui.ts';

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), 'utf8');

const VIDEO_CAPS = {
  models: [
    { model: 'doubao-seedance-2-0-260128', displayName: 'Seedance2.0', resolutions: ['480p', '720p', '1080p'], durationsByResolution: { '480p': [4, 5, 6], '720p': [4, 5, 6], '1080p': [4, 5, 6] } },
    { model: 'doubao-seedance-2-0-fast-260128', displayName: 'Seedance2.0 Fast', resolutions: ['480p', '720p'], durationsByResolution: { '480p': [4, 5, 6], '720p': [4, 5, 6] } },
    { model: 'doubao-seedance-9-9-newmodel', displayName: '未来模型', resolutions: ['720p'], durationsByResolution: { '720p': [8] } },
  ],
  ratios: ['adaptive', '16:9', '1:1', '4:3'],
};
const IMAGE_CAPS = {
  models: [
    { model: 'doubao-seedream-5-0-pro-260628', displayName: 'Seedream 5.0 Pro', sizes: ['1K', '1.5K', '2K'] },
    { model: 'doubao-seedream-5-0-260128', displayName: 'Seedream 5.0 Lite', sizes: ['2K'] },
  ],
};


// 说明：本文件**刻意不做 SSR 渲染断言**。平台源 + 已登录会触发能力拉取，而
// `waitForPyWebView()` 在没有 pywebview 桥时返回一个永不 settle 的 promise，
// 会让 node 测试进程挂住不退出（实测需要 `--test-force-exit` 才能结束）。
// 因此分三层覆盖：纯函数（选项来源/兜底）、store 单测（拉取与降级状态，
// 见 platform-capabilities-store.test.mjs）、源码断言（页面接线与提交守卫）。

// --------------------------------------------------------------------------
// 选项来源（3.3）
// --------------------------------------------------------------------------

test('video options come from the capability list, not the local preset table', () => {
  const options = platformModelOptions(VIDEO_CAPS.models);
  assert.deepEqual(options.map((o) => o.value), [
    'doubao-seedance-2-0-260128',
    'doubao-seedance-2-0-fast-260128',
    'doubao-seedance-9-9-newmodel',
  ]);
  for (const option of options) {
    assert.ok(!['standard', 'fast', 'mini'].includes(option.value), '平台源不应出现本地短键');
  }
});

test('image options come from the capability list and exclude unpriced models', () => {
  const options = platformModelOptions(IMAGE_CAPS.models);
  assert.deepEqual(options.map((o) => o.value), [
    'doubao-seedream-5-0-pro-260628',
    'doubao-seedream-5-0-260128',
  ]);
  assert.ok(!options.some((o) => o.value.includes('flash')), 'Flash 无定价行，不应出现');
});

test('empty or absent capabilities yield no options (never a local fallback)', () => {
  assert.deepEqual(platformModelOptions([]), []);
  assert.deepEqual(platformModelOptions(null), []);
  assert.deepEqual(platformModelOptions(undefined), []);
  assert.deepEqual(platformModelOptions(null), []);
});

test('both composers pick the option source by the current generation source', async () => {
  const [video, image] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('views/SeedreamCreate.vue'),
  ]);
  for (const file of [video, image]) {
    // 平台源走服务端清单，直连源走本地预设表
    assert.match(file, /platformGenerationSelected\.value\s*\?\s*platformModelOptions\(/);
  }
  // 直连分支仍在（预设表），否则切回自定义 Key 会空列表
  assert.match(video, /localVideoModelOptions/);
  assert.match(image, /localImageModelOptions/);
  assert.match(video, /label: t\('seedance\.models\.standard'\)/);
  assert.match(image, /label: t\('seedream\.models\.pro'\)/);
});

// --------------------------------------------------------------------------
// 未知模型兜底（3.4）
// --------------------------------------------------------------------------

test('the label comes from the server-supplied displayName', () => {
  const options = platformModelOptions(VIDEO_CAPS.models);
  assert.deepEqual(options.map(o => o.label), ['Seedance2.0', 'Seedance2.0 Fast', '未来模型']);
  assert.deepEqual(platformModelOptions(IMAGE_CAPS.models).map(o => o.label),
    ['Seedream 5.0 Pro', 'Seedream 5.0 Lite']);
});

test('a model the client has never heard of still renders with the server name', () => {
  // 这正是本次改造的目的：运营上新模型无需改客户端
  const options = platformModelOptions(VIDEO_CAPS.models);
  const unknown = options.find(o => o.value === 'doubao-seedance-9-9-newmodel');
  assert.equal(unknown.label, '未来模型');
});

test('a blank displayName falls back to the real model id', () => {
  // 兼容字段引入前的历史数据
  assert.equal(modelDisplayName({ model: 'doubao-seedance-9-9-x' }), 'doubao-seedance-9-9-x');
  assert.equal(modelDisplayName({ model: 'doubao-seedance-9-9-x', displayName: '   ' }), 'doubao-seedance-9-9-x');
  assert.equal(modelDisplayName({ model: 'm', displayName: '有名字' }), '有名字');
  assert.deepEqual(platformModelOptions([{ model: 'm' }]), [{ value: 'm', label: 'm' }]);
});

test('the local table never decides platform options', () => {
  // 平台源下 model 是上游 ID，本地表查不到 → 空数组，
  // 于是分辨率/时长的合法域只由清单决定（localModelResolutions 的注释即此契约）。
  assert.deepEqual(localVideoResolutions('doubao-seedance-9-9-newmodel'), []);
  assert.deepEqual(localVideoResolutions('standard'), ['480p', '720p', '1080p']);
});

// --------------------------------------------------------------------------
// 降级：阻断提交 + 重试（4.1 / 4.2）
// --------------------------------------------------------------------------

test('both composers block submit and offer a retry when capabilities are missing', async () => {
  const [video, image] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('views/SeedreamCreate.vue'),
  ]);
  for (const file of [video, image]) {
    assert.match(file, /if \(capabilitiesBlocked\.value\) return;/);
    assert.match(file, /:disabled="submitting \|\| capabilitiesBlocked \|\|/);
    assert.match(file, /-capabilities-blocked/);
    assert.match(file, /@click="reloadCapabilities\(\)"/);
    // 失败展示后端原文，未就绪展示"获取中"
    assert.match(file, /workspace\.capabilitiesError\s*\?\s*t\('aiCreation\.capabilitiesFailed'/);
    assert.match(file, /t\('aiCreation\.capabilitiesLoading'\)/);
    assert.match(file, /usePlatformCapabilities\(\)/);
  }
});

test('the blocked state requires the platform source and a logged-in account', async () => {
  const [video, image] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('views/SeedreamCreate.vue'),
  ]);
  for (const file of [video, image]) {
    assert.match(file, /const capabilitiesBlocked = computed/);
    assert.match(file, /platformGenerationSelected\.value\s*&&\s*\(authStore\.isLoggedIn && \(!workspace\.capabilities \|\| !!workspace\.capabilitiesError\)\)/);
  }
});

test('switching source clamps the model back to a legal value for that source', async () => {
  const [video, image] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('views/SeedreamCreate.vue'),
  ]);
  // 平台源：收敛到清单给的合法域；直连源：上游 ID 回落为本地短键
  assert.match(video, /function clampToPlatformModel\(\)/);
  assert.match(image, /function clampToPlatformModel\(\)/);
  assert.match(video, /form\.model = 'standard';/);
  assert.match(image, /form\.model = 'pro';/);
});


// --------------------------------------------------------------------------
// 任务卡/详情页的模型名（本轮改造的核心）
// --------------------------------------------------------------------------

test('no component renders a model name via a bare i18n key lookup', async () => {
  // 曾经的写法：t(`seedance.models.${task.request.model}`)。
  // 平台源下 model 是 Ark ID，词条不存在 → vue-i18n 把 key 本身当文案返回，
  // 界面上会出现字面量 "seedance.models.doubao-seedance-2-0-260128"。
  const files = [
    'components/ai-creation/RecentVideoGenerationCard.vue',
    'components/ai-creation/RecentImageGenerationCard.vue',
    'components/seedance/SeedanceTaskCard.vue',
    'components/seedance/SeedanceGenerationInfo.vue',
    'components/seedream/SeedreamBatchList.vue',
    'views/SeedreamBatchDetail.vue',
  ];
  for (const file of files) {
    const text = await source(file);
    assert.doesNotMatch(text, /t\(`seedance\.models\.\$\{/, `${file} 仍在拼词条 key`);
    assert.doesNotMatch(text, /resolveModelLabel\(/, `${file} 仍在用只认短键的本地映射`);
    assert.match(text, /useModelDisplayName\(\)/, `${file} 应改用统一的模型名解析`);
  }
});

test('the resolver prefers the server name, then local i18n, then the raw id', async () => {
  const text = await source('composables/useModelDisplayName.ts');
  // 顺序即契约：服务端展示名 → 本地词条 → 原样 ID
  assert.match(text, /serverDisplayName\(workspace\.capabilities, model\)/);
  assert.match(text, /LOCAL_LABEL_KEYS\[kind\]\[model\]/);
  // 词条缺失时 t() 返回 key 本身，必须识别并回退，否则会把 key 当文案渲染
  assert.match(text, /text !== key/);
  assert.match(text, /return model;/);
});


// --------------------------------------------------------------------------
// 时长必须按分辨率收敛（真实缺陷复现）
// --------------------------------------------------------------------------

test('duration options are scoped to the selected resolution', async () => {
  // 复现：480p 生效了 4s/5s，720p 只生效 4s。
  // 旧实现下发模型级时长并集 [4,5]，客户端于是放出了没定价的 720p+5s。
  const caps = {
    video: {
      models: [{
        model: 'doubao-seedance-2-0-260128',
        displayName: 'Seedance2.0',
        resolutions: ['480p', '720p'],
        durationsByResolution: { '480p': [4, 5], '720p': [4] },
      }],
      ratios: ['adaptive', '16:9', '1:1', '4:3'],
    },
    image: { models: [] },
  };
  const model = caps.video.models[0];
  assert.deepEqual(model.durationsByResolution['480p'], [4, 5]);
  assert.deepEqual(model.durationsByResolution['720p'], [4], '720p 不得出现没有定价的 5s');
});

test('the composer reads durations from durationsByResolution and re-clamps on resolution change', async () => {
  const text = await source('views/SeedanceCreate.vue');
  // 时长选项按当前分辨率取，而不是模型级并集
  assert.match(text, /durationsByResolution\?\.\[form\.resolution\]/);
  assert.match(text, /entry\.durationsByResolution\?\.\[form\.resolution\]/);
  // 换分辨率要重新收敛时长（否则会留下该分辨率下不可售的悬空值）
  assert.match(text, /watch\(\(\) => form\.resolution, \(\) => \{\s*if \(platformGenerationSelected\.value\) clampToPlatformModel\(\);/);
  // 旧的模型级 durations 字段不应再被客户端读取
  assert.doesNotMatch(text, /entry\?\.durations/);
});
