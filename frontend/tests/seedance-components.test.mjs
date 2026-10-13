import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const seedanceTaskFixture = (overrides = {}) => ({
  local_id: 'local-1',
  remote_id: 'remote-1',
  remote_status: 'succeeded',
  sync_status: {},
  download_status: 'downloaded',
  cache_status: 'complete',
  protected: false,
  request: {
    prompt: 'A hero raises a sword',
    model: 'standard',
    resolution: '720p',
    ratio: '16:9',
    duration: 5,
    generate_audio: false,
    return_last_frame: true,
    priority: 0,
    execution_expires_after: 3600,
  },
  input_urls: { first_frame: 'http://localhost/first.png' },
  output_urls: {
    video: 'http://localhost/video.mp4',
    thumbnail: 'http://localhost/thumbnail.jpg',
    returned_last_frame: 'http://localhost/returned.png',
  },
  file_size_bytes: 1024,
  created_at: '2026-07-26T10:00:00Z',
  updated_at: '2026-07-26T10:05:00Z',
  finished_at: '2026-07-26T10:05:00Z',
  download_url_received_at: '2026-07-26T10:05:00Z',
  elapsed_seconds: 300,
  remote: {},
  error: null,
  retry_of: null,
  handoffs: [],
  ...overrides,
});

test('shared Seedance header removes section navigation and retains global actions', async () => {
  const html = await renderSfc('components/seedance/SeedanceTopNav.vue');
  assert.doesNotMatch(html, /创建任务|任务列表|结果预览/);
  assert.doesNotMatch(html, /href="\/video-generation\/(?:create|tasks|preview)"/);
  assert.match(html, /title="设置"/);
  assert.match(html, /title="返回项目列表"/);
  assert.match(html, /lucide-globe/);
  assert.match(html, /lucide-settings/);
  assert.match(html, /lucide-home-icon/);
  assert.match(html, /sticky top-0 z-30/);
  assert.doesNotMatch(html, /<nav/);
  assert.match(html, /<button type="button"[^>]*title="Switch to English"/);
});

test('Seedance create screen uses one compact composer with collapsed parameters', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/video-generation/create',
  });
  assert.match(html, /首帧图片/);
  assert.match(html, /尾帧图片/);
  assert.match(html, /提示词/);
  assert.match(html, /16:9/);
  assert.match(html, /自适应/);
  assert.match(html, /参数摘要/);
  assert.doesNotMatch(html, /高级选项|优先级|任务超时/);
  assert.match(html, /data-test="seedance-composer"/);
  assert.match(html, /class="[^"]*seedance-prompt-surface[^"]*border-\[#3b3b3b\][^"]*bg-\[#1f1f1f\][^"]*"[^>]*data-test="seedance-composer"/);
  assert.match(html, /data-test="seedance-prompt"/);
  assert.match(html, /data-test="seedance-frame-strip"/);
  assert.match(html, /min-h-\[282px\]/);
  assert.doesNotMatch(html, /min-h-\[282px\][^\"]*(?:border|rounded-\[20px\]|bg-\[#191a1f\]|shadow-inner)/);
  assert.match(html, /描述角色如何运动，包括动作过程、朝向、镜头和音效/);
  assert.match(html, />\s*首帧\s*</);
  assert.match(html, />\s*尾帧\s*</);
  assert.match(html, /data-test="seedance-frame-required"[^>]*>\s*\*\s*</);
  assert.match(html, /data-test="seedance-frame-optional"[^>]*>\s*（可选）\s*</);
  assert.match(html, /data-test="seedance-model"/);
  assert.doesNotMatch(html, /<select[^>]*data-test="seedance-model"/);
  assert.match(html, /data-test="seedance-parameter-summary"/);
  assert.match(html, /class="[^"]*border-\[#3b3b3b\][^"]*bg-\[#1f1f1f\][^"]*"[^>]*data-test="seedance-parameter-panel"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /data-test="seedance-parameter-panel"[^>]*style="display:none;"/);
  assert.match(html, /data-test="seedance-submit"/);
  assert.match(html, /class="[^"]*bg-\[#ffbd5c\][^"]*hover:bg-\[#ffc975\][^"]*disabled:bg-\[#4a4a4a\][^"]*"[^>]*data-test="seedance-submit"/);
  assert.match(html, /<button[^>]*data-test="seedance-duration"/);
  assert.doesNotMatch(html, /<select[^>]*data-test="seedance-duration"/);
  const createSource = await readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8');
  // 时长选项改由 durationOptions 计算属性提供：直连源 = 本地 DURATION_OPTIONS，
  // 平台源 = 能力清单给的档位。见 openspec: gam-platform-capabilities 3.1。
  assert.match(createSource, /v-for="duration in durationOptions"/);
  assert.match(createSource, /: \[\.\.\.DURATION_OPTIONS\]/);
  assert.match(createSource, /\{\{ duration \}\}s/);
  assert.doesNotMatch(createSource, /:value="(?:-1|7|15)"/);
  assert.match(html, /aria-describedby="seedance-first-frame-help"/);
  assert.match(html, /aria-required="true"/);
});

test('Seedance resolution control fits the three remaining resolution options', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'));
  assert.match(source, /class="grid w-3\/4 grid-cols-3 gap-1 rounded-xl bg-black\/15 p-1" data-test="seedance-resolution"/);
  assert.match(source, /form\.resolution === resolution \? 'bg-primary\/20 text-primary-200 shadow-sm'/);
  assert.doesNotMatch(source, /grid-cols-4[^\n]*data-test="seedance-resolution"/);
});

test('Seedance ratio picker uses the same compact segmented style as resolution', async () => {
  const html = await renderSfc('components/seedance/SeedanceRatioPicker.vue', {
    props: { modelValue: '16:9', adaptiveLabel: '自适应' },
  });

  assert.match(html, /data-test="seedance-ratio"/);
  assert.match(html, /grid-cols-4 gap-1 rounded-xl bg-black\/15 p-1/);
  assert.match(html, /bg-primary\/20 text-primary-200 shadow-sm/);
  assert.doesNotMatch(html, /border-primary|shapeClass/);
});

test('Seedance create screen offers a one-click copy button for the prompt', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/video-generation/create',
  });
  assert.match(html, /lucide-copy-icon/);
  assert.match(html, /title="复制"/);
});

test('Seedance prompt count turns yellow only after its displayed recommendation', async () => {
  const source = await readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8');
  assert.match(source, /promptInfo\.count > promptInfo\.limit\s*\? 'text-yellow-400'/);
  assert.doesNotMatch(source, /promptInfo\.count >= promptInfo\.limit\s*\? 'text-yellow-400'/);
});

test('Seedance task card renders real metadata and state-derived actions', async () => {
  const html = await renderSfc('components/seedance/SeedanceTaskCard.vue', {
    props: { task: seedanceTaskFixture(), sequence: '②' },
  });
  assert.match(html, /②/);
  assert.doesNotMatch(html, /A hero raises a sword/);
  assert.match(html, /720p/);
  assert.match(html, /16:9/);
  assert.match(html, /查看详情/);
  assert.match(html, /再次生成/);
  assert.match(html, /使用尾帧继续生成/);
  assert.match(html, /删除/);
  assert.doesNotMatch(html, /取消任务|重新生成|重试下载/);

  const queued = await renderSfc('components/seedance/SeedanceTaskCard.vue', {
    props: {
      task: seedanceTaskFixture({
        remote_status: 'queued',
        download_status: 'pending',
        output_urls: {},
      }),
    },
  });
  assert.match(queued, /取消任务/);
  assert.doesNotMatch(queued, /查看详情|续生成|删除/);

  const cleared = await renderSfc('components/seedance/SeedanceTaskCard.vue', {
    props: {
      task: seedanceTaskFixture({
        cache_status: 'cleared',
        download_status: 'cleared',
        output_urls: {},
      }),
    },
  });
  assert.match(cleared, /缓存已清理/);
  assert.doesNotMatch(cleared, /seedance\.status\.cleared/);
});

test('Seedance generation information provides a one-click full-prompt copy control', async () => {
  const html = await renderSfc('components/seedance/SeedanceGenerationInfo.vue', {
    props: {
      task: seedanceTaskFixture(),
      output: { resolution: '720p', ratio: '16:9', duration: '5s', fps: '24' },
    },
  });
  assert.match(html, /完整提示词/);
  assert.match(html, /aria-label="复制提示词"/);
  assert.match(html, /lucide-copy/);
});

test('Seedance status badge visibly distinguishes every task lifecycle state', async () => {
  const scenarios = [
    ['queued', { remote_status: 'queued', download_status: 'pending' }, '排队中'],
    ['running', { remote_status: 'running', download_status: 'pending' }, '正在生成'],
    ['downloading', { remote_status: 'succeeded', download_status: 'downloading' }, '正在下载'],
    ['succeeded', {}, '下载完成'],
    ['failed', { remote_status: 'failed', download_status: 'pending' }, '生成失败'],
    ['expired', { remote_status: 'expired', download_status: 'pending' }, '远程记录已失效'],
    ['cleared', { cache_status: 'cleared', download_status: 'cleared' }, '缓存已清理'],
  ];

  for (const [name, overrides, label] of scenarios) {
    const html = await renderSfc('components/seedance/SeedanceStatusBadge.vue', {
      props: { task: seedanceTaskFixture(overrides) },
    });
    assert.match(html, new RegExp(`>\\s*${label}<`), name);
    if (name === 'succeeded') {
      assert.match(html, /backdrop-blur[^\"]*bg-success\/15[^\"]*text-success/);
    }
  }
});

test('Seedance result components render only real task media and metadata', async () => {
  const task = seedanceTaskFixture();
  const [stage, strip, info] = await Promise.all([
    renderSfc('components/seedance/SeedanceVideoStage.vue', {
      props: {
        phase: 'succeeded',
        videoUrl: task.output_urls.video,
        summary: task.request.prompt,
      },
    }),
    renderSfc('components/seedance/SeedanceMediaStrip.vue', { props: { task } }),
    renderSfc('components/seedance/SeedanceGenerationInfo.vue', {
      props: {
        task,
        output: { resolution: '720p', ratio: '16:9', duration: '5', fps: '24' },
      },
    }),
  ]);
  assert.match(stage, /<video/);
  assert.match(stage, /video\.mp4/);
  assert.match(strip, /first\.png/);
  assert.match(strip, /returned\.png/);
  assert.match(info, /remote-1/);
  assert.match(info, /720p/);
  assert.match(info, /16:9/);
  assert.match(info, /总 Token 数/);
  assert.doesNotMatch(info, /\busage\b/);

  const cleared = await renderSfc('components/seedance/SeedanceVideoStage.vue', {
    props: { phase: 'cleared', videoUrl: task.output_urls.video, summary: '' },
  });
  assert.match(cleared, /缓存素材已清理/);
  assert.doesNotMatch(cleared, /<video/);
});

test('Seedance preview provides existing-role and new-role handoff modes', async () => {
  const html = await renderSfc('components/seedance/SeedanceHandoffPanel.vue', {
    props: {
      task: seedanceTaskFixture(),
      disabled: false,
      roles: [{ name: 'hero', projectCount: 2 }],
    },
  });
  assert.match(html, /送入逐帧动画流水线/);
  assert.match(html, /已有角色/);
  assert.match(html, /新建角色/);
  assert.match(html, /hero/);
  assert.match(html, /已有动画 2 个/);
  assert.doesNotMatch(html, /hero \(2\)/);
  assert.match(html, /动画名称/);

  const disabled = await renderSfc('components/seedance/SeedanceHandoffPanel.vue', {
    props: { task: seedanceTaskFixture(), disabled: true, roles: [] },
  });
  assert.match(disabled, /<button[^>]+disabled[^>]*>[^<]*创建逐帧动画/s);
});

test('Seedance image picker renders the generated preview instead of its local path', async () => {
  const html = await renderSfc('components/seedance/SeedanceImagePicker.vue', {
    props: {
      modelValue: '/tmp/rabbit.jpeg',
      previewUrl: 'data:image/png;base64,thumbnail',
      label: '首帧图片',
      help: '选择图片',
      helpId: 'first-frame-help',
      selectLabel: '选择图片',
      changeLabel: '更换',
      editLabel: '图片编辑',
      removeLabel: '移除',
      selectedLabel: '图片已选择',
    },
  });
  assert.match(html, /src="data:image\/png;base64,thumbnail"/);
  assert.match(html, /rabbit\.jpeg/);
  assert.doesNotMatch(html, /src="\/tmp\/rabbit\.jpeg"/);
  assert.match(html, /更换[\s\S]*图片编辑[\s\S]*移除/);
  assert.match(html, /data-test="seedance-edit-image"/);
});

test('compact Seedance frame card keeps preview editing and removal controls', async () => {
  const html = await renderSfc('components/seedance/SeedanceImagePicker.vue', {
    props: {
      modelValue: '/tmp/rabbit.jpeg',
      previewUrl: 'data:image/png;base64,thumbnail',
      label: '首帧图片',
      cardLabel: '首帧',
      help: '必填',
      helpId: 'first-frame-help',
      selectLabel: '选择图片',
      changeLabel: '更换',
      editLabel: '图片编辑',
      removeLabel: '移除',
      selectedLabel: '图片已选择',
      compact: true,
    },
  });
  assert.match(html, /src="data:image\/png;base64,thumbnail"/);
  assert.match(html, /title="图片编辑"/);
  assert.match(html, /title="移除"/);
  assert.doesNotMatch(html, /rabbit\.jpeg/);
});

test('Seedance frame cards accept generated image drops for first and last frame targets', async () => {
  const [picker, create] = await Promise.all([
    readFile(new URL('../src/components/seedance/SeedanceImagePicker.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'),
  ]);

  assert.match(picker, /@dragenter="onDragEnter"/);
  assert.match(picker, /@dragover="onDragOver"/);
  assert.match(picker, /@drop="onDrop"/);
  assert.match(picker, /emit\('drop-image', result\.candidate\)/);
  assert.match(create, /@drop-image="dropCandidateFrame\('first_frame', \$event\)"/);
  assert.match(create, /@drop-image="dropCandidateFrame\('last_frame', \$event\)"/);
  assert.match(create, /dropAsFirstFrame/);
  assert.match(create, /dropAsLastFrame/);
});

test('Seedance create image editing preserves generation layout with the copied path', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'));
  assert.match(source, /@edit="openImageEditor\('first_frame'\)"/);
  assert.match(source, /@edit="openImageEditor\('last_frame'\)"/);
  assert.match(source, /api\.seedance\.getEditableImage\(sourcePath\)/);
  assert.match(source, /editorGenerationLayout\.value = result\.data\.generation_layout/);
  assert.match(source, /sourcePath, imageDataUrl, editSourceDataUrl, generationLayout/);
  assert.match(source, /editorEditSourceUrl\.value = result\.data\.edit_source_data_url/);
  assert.match(source, /:generation-layout="editorGenerationLayout"/);
  assert.match(source, /resize-enabled/);
  assert.match(source, /form\[field\] = result\.data\.path/);
});

test('Seedance image editor opens resize controls directly and places restore between cancel and apply', async () => {
  const html = await renderSfc('components/seedream/SeedreamImageEraser.vue', {
    props: {
      imageUrl: 'data:image/png;base64,image',
      saving: false,
      resizeEnabled: true,
      title: '图片编辑',
    },
  });
  assert.match(html, /data-test="image-editor-resize-controls"/);
  assert.doesNotMatch(html, /image-editor-resize-toggle/);
  assert.match(html, /取消[\s\S]*data-test="image-editor-restore-original"[\s\S]*复原为原图[\s\S]*data-test="seedream-eraser-apply"/);
  assert.match(html, /bg-success/);
  assert.match(html, /角色占画面高度/);
  assert.match(html, /底部留白/);
  assert.doesNotMatch(html, /image-editor-height-preset-/);
  assert.match(html, /data-test="image-editor-measured-height-px"/);
  assert.match(html, /参考线测量高度/);
  assert.doesNotMatch(html, /data-test="image-editor-estimated-video-heights"/);
  assert.doesNotMatch(html, /data-test="image-editor-bottom-distance-px"/);
  assert.doesNotMatch(html, /角色目标高度（px）|距离底边（px）/);
});

test('Seedance settings uses the shared workspace without losing safe controls', async () => {
  const [html, source] = await Promise.all([
    renderSfc('views/SeedanceSettings.vue', {
    route: '/video-generation/settings',
    piniaState: {
      seedance: {
        tasks: [],
        currentTask: null,
        settings: {
          api_key_configured: true,
          cache_dir: '/tmp/seedance',
          default_model: 'standard',
          default_resolution: '720p',
          default_ratio: 'adaptive',
          default_duration: -1,
          default_generate_audio: false,
          default_return_last_frame: true,
          default_priority: 0,
          default_expires_after: 3600,
          retention_days: 0,
          last_cleanup_at: null,
        },
        cacheStatus: {
          total_bytes: 0,
          clearable_bytes: 0,
          task_count: 0,
          protected_task_count: 0,
        },
        loading: false,
        error: null,
      },
      config: {
        config: {
          language: 'zh',
          theme: 'dark',
          logger_enabled: true,
          logger_config: {},
          seedance: {},
        },
        loading: false,
        error: null,
      },
      seedream: {
        settings: {
          default_count: 2,
          default_model: 'pro',
          default_resolution: '1K',
          default_ratio: '16:9',
        },
        error: null,
      },
    },
    }),
    readFile(new URL('../src/views/SeedanceSettings.vue', import.meta.url), 'utf8'),
  ]);
  assert.match(html, />设置</);
  assert.match(html, /API Key/);
  assert.match(html, /测试连接/);
  assert.match(html, /默认生成参数/);
  assert.match(source, /:options="seedanceDurationOptions"/);
  assert.match(source, /DURATION_OPTIONS\.map\(value/);
  assert.match(html, /data-test="seedream-settings-model"/);
  assert.match(source, /\{ value: 'flash', label: t\('seedream\.models\.flash'\) \}/);
  assert.doesNotMatch(html, /value="v45"|value="v40"/);
  assert.match(html, /应用设置/);
  assert.doesNotMatch(html, /默认 FPS/);
  assert.match(html, /启用日志/);
  assert.match(html, /type="checkbox" checked/);
  assert.match(html, /form="seedance-settings-form"/);
  assert.match(html, /id="seedance-settings-form"/);
  assert.match(html, /缓存管理/);
  assert.match(html, /value="\/tmp\/seedance"/);
  assert.match(html, /h-\[42px\] shrink-0/);
  assert.match(html, /autocomplete="new-password"/);
  assert.match(html, /从不/);
  assert.doesNotMatch(html, /Seedance Studio/);
  assert.doesNotMatch(html, /href="\/video-generation\/create"/);
  assert.doesNotMatch(html, /href="\/video-generation\/tasks"/);
  assert.match(html, /ml-auto flex items-center gap-2/);
});

test('a connection failure does not replace a loaded settings form with a load failure panel', async () => {
  const html = await renderSfc('views/SeedanceSettings.vue', {
    route: '/video-generation/settings',
    piniaState: {
      seedance: {
        tasks: [], currentTask: null,
        settings: {
          api_key_configured: false, cache_dir: '/tmp/seedance', default_model: 'standard',
          default_resolution: '720p', default_ratio: 'adaptive', default_duration: 4,
          default_generate_audio: false, default_return_last_frame: false, default_priority: 0,
          default_expires_after: 3600, retention_days: 0, last_cleanup_at: null,
        },
        cacheStatus: null, loading: false,
        error: { code: 'API_KEY_NOT_CONFIGURED', message: 'Configure an API key before continuing', field: 'api_key' },
      },
      config: { config: { logger_enabled: false, paid_generation_confirmation_enabled: true }, loading: false, error: null },
      seedream: { settings: { default_count: 2, default_model: 'pro', default_resolution: '1K', default_ratio: '16:9' }, error: null },
    },
  });
  assert.match(html, /id="seedance-settings-form"/);
  assert.doesNotMatch(html, /部分设置加载失败/);
});

test('Seedance generation info displays total_tokens when the API returns a numeric value', async () => {
  const task = seedanceTaskFixture({
    remote: { usage: { total_tokens: 12345 } },
  });
  const html = await renderSfc('components/seedance/SeedanceGenerationInfo.vue', {
    props: {
      task,
      output: { resolution: '720p', ratio: '16:9', duration: '5s', fps: '24' },
    },
  });
  assert.match(html, /12,345/);
  assert.match(html, /总 Token 数/);
  assert.doesNotMatch(html, /API 未返回/);
});

test('Seedance generation info shows unavailable fallback when total_tokens is missing', async () => {
  const task = seedanceTaskFixture({ remote: {} });
  const html = await renderSfc('components/seedance/SeedanceGenerationInfo.vue', {
    props: {
      task,
      output: { resolution: '720p', ratio: '16:9', duration: '5s', fps: '24' },
    },
  });
  assert.match(html, /API 未返回/);
  assert.doesNotMatch(html, />12345/);
});

test('Seedance generation info shows unavailable fallback when total_tokens is not a number', async () => {
  const task = seedanceTaskFixture({
    remote: { usage: { total_tokens: 'not-a-number' } },
  });
  const html = await renderSfc('components/seedance/SeedanceGenerationInfo.vue', {
    props: {
      task,
      output: { resolution: '720p', ratio: '16:9', duration: '5s', fps: '24' },
    },
  });
  assert.match(html, /API 未返回/);
  assert.doesNotMatch(html, /not-a-number/);
});

test('Seedance create form does not show paid confirmation modal on initial render', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/video-generation/create',
  });
  assert.doesNotMatch(html, /paid-confirm-title/);
  assert.doesNotMatch(html, /paidConfirmTitle/);
  assert.doesNotMatch(html, /paidConfirmBody/);
});

test('Seedance create form wires paid confirmation before task creation and protects against duplicates', async () => {
  const create = await readFile(
    new URL('../src/views/SeedanceCreate.vue', import.meta.url),
    'utf8',
  );

  // Confirmation modal state and template exist
  assert.match(create, /const paidConfirmModal = ref\(false\)/);
  assert.match(create, /paidConfirmModalRoot/);
  assert.match(create, /aria-labelledby="paid-confirm-title"/);
  assert.match(create, /aria-describedby="paid-confirm-description"/);
  assert.match(create, /@click\.self="cancelPaidAction"/);
  assert.match(create, /@keydown="onPaidConfirmKeydown"/);
  assert.match(create, /trapModalTab\(event, paidConfirmModalRoot\.value\)/);

  // submit() opens the confirmation modal AFTER preflight but BEFORE createTask
  assert.match(create, /pendingRequest = request/);
  assert.match(create, /paidConfirmModal\.value = true/);
  // createTask is NOT called in submit() — only in confirmPaidAction
  const submitMatch = create.match(/async function submit\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(submitMatch, 'submit function should exist');
  assert.doesNotMatch(submitMatch[0], /store\.createTask/);

  // confirmPaidAction delegates task creation without changing the global preference.
  const confirmMatch = create.match(/async function confirmPaidAction\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(confirmMatch, 'confirmPaidAction function should exist');
  assert.match(confirmMatch[0], /createPendingTask\(\)/);
  assert.doesNotMatch(create, /skipPaidConfirmation|paid_generation_confirmation_enabled: false/);
  assert.doesNotMatch(confirmMatch[0], /router\.push/);
  // Guard against duplicate confirmation
  assert.match(confirmMatch[0], /if \(submitting\.value \|\| !pendingRequest \|\| platformConfirmBlocked\.value\) return/);

  const createPendingMatch = create.match(/async function createPendingTask\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(createPendingMatch, 'createPendingTask function should exist');
  assert.match(createPendingMatch[0], /store\.createTask\(request, source\)/);
  assert.match(createPendingMatch[0], /workspace\.setCurrentGeneration\(\{ kind: 'video', localId: task\.local_id \}\)/);

  // cancelPaidAction does NOT call createTask
  const cancelMatch = create.match(/function cancelPaidAction\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(cancelMatch, 'cancelPaidAction function should exist');
  assert.doesNotMatch(cancelMatch[0], /store\.createTask/);
  assert.match(cancelMatch[0], /paidConfirmModal\.value = false/);
  assert.match(cancelMatch[0], /pendingRequest = null/);

  // Confirm and cancel buttons are both disabled while submitting
  assert.match(create, /:loading="submitting" :disabled="submitting \|\| platformConfirmBlocked" @click="confirmPaidAction"/);
  assert.match(create, /:disabled="submitting" @click="cancelPaidAction"/);
});
