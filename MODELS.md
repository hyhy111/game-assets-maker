# 去背模型下载与存储

本说明适用于 Game Assets Maker 的本地背景移除功能。步骤 02 保留 **U²-Net（rembg）**；Windows 提供 **BiRefNet Lite FP16**（默认）和 **BiRefNet Standard FP16**，macOS 保留 **BiRefNet（Comfy-Org）**。它与 Seedream／Seedance 云端生成模型无关，本地去背不需要登录、积分或 API Key。

仓库和当前发布包均不包含模型权重。模型下载到本地后可重复使用，不必每次处理都下载。

## Windows：BiRefNet ONNX FP16

在步骤 02 或设置中选择 Lite 或 Standard。仅显式点击下载才获取所选模型，来源为 ModelScope 或 Hugging Face。两种模型独立校验、缓存，切换选择不会删除另一份模型或修改已有透明帧；成功重新处理后才替换结果。下载与处理均不需要登录。

| 模型 | 固定版本 | 字节数（十进制 MB） | SHA-256 |
| --- | --- | ---: | --- |
| Lite FP16 | `7a387b7aa4fa82a33adf7a0f32e2ea6678106a08` | 114538221（114.5 MB） | `d39b897ceb16ae654c1731f3dba0cf9b368d9cae74b5a57459b455cc8bfec402` |
| Standard FP16 | `7ad37b089f4e810d5a1bb1b08ae9c35435a7d5bd` | 489666272（489.7 MB） | `3654c741eb80bd926ada8fed1713b506ccf8d30eb1f6487e87eb9f234f33df09` |

安装模式分别存于 `~/.gam/models/birefnet-lite-onnx/model_fp16.onnx` 与 `~/.gam/models/birefnet-standard-onnx/model_fp16.onnx`，遵守 `GAM_DATA_ROOT`。源码模式使用对应的仓库 `models/` 子目录。下载完成后须通过大小、SHA-256 及初始化检查，才能离线运行。当前 Windows ONNX 使用 CPU，固定 1024×1024 输入并恢复原图尺寸，保留源 alpha 及 BiRefNet 边缘去色。

Windows uses pinned Lite/Standard FP16 ONNX files, downloaded explicitly and cached independently. Sizes above use decimal MB. Validated models work offline on CPU without PyTorch; macOS retains its existing Comfy-Org backend.

## macOS：BiRefNet（Comfy-Org）

在「背景移除」选择 **BiRefNet**，首次使用时从 [魔搭 ModelScope](https://modelscope.cn/models/Comfy-Org/BiRefNet) 或 [Hugging Face](https://huggingface.co/Comfy-Org/BiRefNet/blob/35767b272f2846752a3aee1259abdd4586f735c8/background_removal/birefnet.safetensors) 下载约 424 MiB 的权重。两个来源共用同一个本地文件，并校验同一个 SHA-256。Hugging Face 下载地址固定到提交 `35767b2`。GAM 使用 PyTorch 在本地推理，Apple Silicon 在 MPS 可用时使用 MPS，其余情况使用 CPU。BiRefNet 的 macOS 运行时要求 macOS 14 或更新版本。

已下载的权重也可复制到模型目录并命名为 `birefnet.safetensors`。安装版默认路径是 `~/.gam/models/birefnet-comfy/birefnet.safetensors`，设置 `GAM_DATA_ROOT` 时使用该数据根。源码开发模式使用仓库的 `models/birefnet-comfy/`。应用校验 Comfy-Org 权重的 SHA-256，校验通过后可离线使用。推理代码沿用 [ZhengPeng7 的 BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet)，按 MIT 许可随应用分发。

## U²-Net（rembg）

## 安装版：在应用中下载

1. 打开项目的“步骤 2：背景移除”。
2. 缺少有效模型时，界面显示需要下载；选择 ModelScope 或 GitHub 下载源，点击下载。
3. 等待下载和初始化完成，状态变为就绪后再开始处理。下载失败可更换来源并重试。

默认下载源为 ModelScope。应用会显示下载／初始化状态；本地已有有效模型时只需初始化，不重新下载。首次缺少模型时需要用户选择来源并点击下载，不是启动应用后自动下载。

## 模型文件位置

| 运行方式 | 模型目录 |
| --- | --- |
| 源码开发模式（默认） | 仓库根目录的 `models/rembg/` |
| 安装版／`GAM_DATA_MODE=installed` | 用户主目录的 `.gam/models/rembg/` |
| 安装数据模式且设置 `GAM_DATA_ROOT` | `<GAM_DATA_ROOT>/models/rembg/` |

最终文件名均为 `u2net.onnx`。例如，macOS 默认安装目录为 `~/.gam/models/rembg/u2net.onnx`；Windows 位于用户主目录的 `.gam\models\rembg\u2net.onnx`。安装版模型位于可写的用户数据目录，更新或替换应用包不需要重新下载。

需要自定义数据根时，在启动应用前设置 `GAM_DATA_ROOT`；源码启动还需使用 `GAM_DATA_MODE=installed` 才会将模型放到该数据根。该配置影响应用数据根，不是单独的模型目录设置。源码开发模式的模型位置仍固定在仓库内，不随 `GAM_DATA_ROOT` 改变。无需修改 `_MODELS_DIR` 源码，也不要依赖外部 `U2NET_HOME` 覆盖应用路径，应用会自行设置它。

## 源码开发：提前下载

在仓库根目录、完成 Python 依赖安装后运行：

```bash
uv run python scripts/download_models.py u2net
```

不传模型名也只下载 U2Net：

```bash
uv run python scripts/download_models.py
```

此脚本使用 ModelScope，始终保存到仓库内的 `models/rembg/`，不会按安装版数据根选择目录。它用于本地开发准备，不代替安装版界面的下载流程；该脚本用于准备 U²-Net 权重。

## 离线使用与手动准备

离线前完成模型下载和初始化检查。也可以将已有的有效 `u2net.onnx` 复制到对应运行模式的模型目录，再打开步骤 2 等待初始化。应用使用 MD5 校验模型内容，预期值为：

```text
60024c5c889badc19c04ad937298a77b
```

只创建同名文件或使用不匹配的模型无法通过校验。有效模型就绪后，视频抽帧、去背和后处理可在本地运行；云端图像／视频生成仍需要网络。

## 故障排查

| 状态／现象 | 检查与处理 |
| --- | --- |
| 一直提示需要下载 | 确认文件位于当前运行模式的目录，文件名为 `u2net.onnx`，内容校验通过；仓库模型不会自动成为安装版模型 |
| 下载失败 | 检查网络、磁盘空间和目录写权限；在界面切换 ModelScope／GitHub 来源并重试 |
| 下载后初始化失败 | 查看界面错误并重试；确认模型校验通过。若仍失败，检查应用错误日志中的运行环境／推理初始化错误，无需修改模型路径源码 |
| 更新应用后找不到模型 | 检查是否改用了不同数据模式或 `GAM_DATA_ROOT`；安装版默认仍读取用户主目录的 `.gam` |

Windows 安装数据模式还会尝试将 `%LOCALAPPDATA%/VideoToSheet/models/rembg/u2net.onnx` 中校验有效的旧模型复制到当前模型目录，保留旧文件；这不适用于仓库模型或其他模型类型。

## 打包与版本控制

当前发布配置不捆绑模型权重，无需为打包提前下载全部模型。用户首次使用去背时通过界面下载，或提前向用户数据目录放入有效模型。模型权重属于本地下载数据，不应提交到 Git；仓库已忽略 `models/`。


## Windows BiRefNet 与可选 NVIDIA 加速

Windows 基础安装包使用 CPU ONNX Runtime，不携带 PyTorch、模型或 CUDA 组件；无需安装 Python。本地抽帧、去背、后处理不要求登录、积分或 API Key。macOS 继续使用原 Comfy-Org 权重与 PyTorch/MPS；不显示 Windows ONNX 模型或组件下载。

| Windows 模型 | 下载字节数 | 用途 |
| --- | ---: | --- |
| BiRefNet Lite FP16 | 114,538,221（约 109.2 MiB） | 新项目默认，下载较小 |
| BiRefNet 标准 FP16 | 489,666,272（约 467.0 MiB） | 可按素材效果选择 |

只下载所选模型，两模型独立缓存；已有项目保留有效选择。U²-Net 继续可用。准备模型时使用模型卡的魔搭／备份来源；NVIDIA 加速组件使用独立的阿里 PyPI 镜像／官方 PyPI 来源，两个来源选择分别保存。

GPU 加速完全可选。固定 7 个 wheel 总下载量为 **1,298,542,822 字节（约 1.21 GiB）**，解包还需额外磁盘空间。点击准备后 GAM 自动校验、解包和真实推理检查，无需 pip、CUDA Toolkit 或系统 Python；显卡驱动需由用户正常安装。已测 RTX 4060 Ti 16GB，不据此承诺其他显卡或设置未经实测的显存门槛。组件就绪从下一任务生效，准备过程中已就绪的模型仍可使用 CPU。

下载可以取消或退出，下次在相应卡片继续；有效文件会复用，支持服务端范围请求时续传。换源仍核对固定文件身份和完整 SHA-256，不兼容续传或损坏的文件会重新获取。不要删除用户数据目录中的下载进度。模型与组件全部就绪后可断网复用，升级应用不要求重新准备。

GPU 初始化、显存不足或进程错误会显示原因，当前失败帧及后续帧继续使用同一模型的 CPU；整批成功后才替换现有结果，取消或最终失败保留旧结果。反馈问题时请附应用版本、Windows/显卡/驱动、所选模型和来源、卡片原始错误与日志，注明是在下载、校验、初始化还是处理中失败，勿附 API Key 或个人素材。
