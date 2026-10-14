# 字段与界面显示名称

说明图片／视频生成选项、草稿状态、参数建议和界面操作时，使用下表中与当前页面、界面语言一致的显示名称。字段名用于内部 CLI／API 请求；只有用户明确询问字段、要求代码或排查技术问题时，才在技术说明中展示字段名。模型选项也使用界面显示名称。

## 图片生成

| 字段 | CLI 参数 | 中文界面名称 | 英文界面名称 | 翻译键 |
|---|---|---|---|---|
| `prompt` | `--prompt` / `--prompt-file` | 提示词 | Prompt | `seedream.create.promptTitle` |
| `model` | `--model` | 模型 | Model | `seedream.create.model` |
| `resolution` | `--resolution` | 分辨率 | Resolution | `seedream.create.resolution` |
| `ratio` | `--ratio` | 宽高比 | Aspect Ratio | `seedream.create.ratio` |
| `count` | `--count` | 生成数量 | Image Count | `seedream.create.count` |
| `reference_image` | `--reference-image` / `--clear-reference-image` | 参考图 | Reference Image | `seedream.create.referenceImage` |

## 视频生成

| 字段 | CLI 参数 | 中文界面名称 | 英文界面名称 | 翻译键 |
|---|---|---|---|---|
| `prompt` | `--prompt` / `--prompt-file` | 提示词 | Prompt | `seedance.create.promptTitle` |
| `first_frame` | `--first-frame` / `--clear-first-frame` | 首帧图片（卡片：首帧） | First Frame Image（卡片：Start） | `seedance.create.firstFrame` / `firstFrameShort` |
| `last_frame` | `--last-frame` / `--clear-last-frame` | 尾帧图片（卡片：尾帧） | Last Frame Image（卡片：End） | `seedance.create.lastFrame` / `lastFrameShort` |
| `model` | `--model` | 模型 | Model | `seedance.create.model` |
| `resolution` | `--resolution` | 分辨率 | Resolution | `seedance.create.resolution` |
| `ratio` | `--ratio` | 画面比例 | Aspect Ratio | `seedance.create.ratio` |
| `duration` | `--duration` | 时长 | Duration | `seedance.create.duration` |
| `generate_audio` | `--generate-audio` / `--no-generate-audio` | 生成音频 | Generate Audio | `seedance.create.generateAudio` |
| `return_last_frame` | `--return-last-frame` / `--no-return-last-frame` | 返回尾帧 | Return Last Frame | `seedance.create.returnLastFrame` |

## 生成方式与模型选项

生成方式由界面单独管理；下表用于说明当前选项，不代表草稿补丁可以切换生成方式。

| 内部字段／取值 | 中文界面名称 | 英文界面名称 | 翻译键 |
|---|---|---|---|
| `source` / `generationSource` | 生成方式 | Generation source | `aiCreation.generationSource` |
| `api-key` | 自定义 Key | Custom API key | `aiCreation.customApiKey` |
| `forfuner-ai` | ForFuner AI | ForFuner AI | `aiCreation.forfunerAI` |
| 图片模型 `pro` | Seedream 5.0 Pro | Seedream 5.0 Pro | `seedream.models.pro` |
| 图片模型 `flash` | Seedream 5.0 Flash | Seedream 5.0 Flash | `seedream.models.flash` |
| 视频模型 `standard` | Seedance2.0 | Seedance2.0 | `seedance.models.standard` |
| 视频模型 `fast` | Seedance2.0 Fast | Seedance2.0 Fast | `seedance.models.fast` |
| 视频模型 `mini` | Seedance2.0 Mini | Seedance2.0 Mini | `seedance.models.mini` |
| 视频比例 `adaptive` | 自适应 | Adaptive | `seedance.create.adaptive` |

平台模型按界面实际显示名称说明。

## 表述示例与查阅来源

核对草稿后可以这样说明：“提示词和首帧图片已填入，时长已设为推荐的 5 秒。‘生成音频’目前关闭，其余生成参数保持原值；请在 gam 中检查后手动发送。”状态和值必须来自实际回执。

“生成音频”和“返回尾帧”位于视频生成的参数面板中；需要引导用户操作时，使用这些开关名称。

本表按 `frontend/src/views/SeedreamCreate.vue`、`frontend/src/views/SeedanceCreate.vue` 及 `frontend/src/locales/zh-CN.ts`、`frontend/src/locales/en.ts` 核对。表外选项或界面名称变化时，以实际界面为准；源码环境可查相应组件与翻译键。没有可见控件的内部字段，用用户能理解的作用说明，避免引导用户寻找不存在的控件。
