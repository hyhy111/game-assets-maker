# 模型文件管理

本项目使用 rembg 进行背景移除，支持将模型文件与应用一起打包分发。

## 模型存储位置

模型文件存储在项目目录的 `models/rembg/` 文件夹中：

```
game_assets_maker/
├── models/
│   └── rembg/
│       ├── u2net.onnx              # 默认模型 (~176MB)
│       ├── u2netp.onnx             # 轻量版 (~4MB)
│       ├── u2net_human_seg.onnx    # 人像专用 (~176MB)
│       └── ...
```

## 下载模型

### 方法一：下载所有模型（推荐）

```bash
python scripts/download_models.py
```

这会下载所有捆绑的模型（约 530MB）：
- `u2net` - 通用模型（推荐，效果最佳）
- `isnet-general-use` - ISNet 通用场景
- `isnet-anime` - ISNet 动漫专用

### 方法二：下载特定模型

```bash
python scripts/download_models.py u2net
```

## 模型大小参考

| 模型 | 大小 | 用途 |
|------|------|------|
| u2net | ~176MB | 通用（推荐） |
| isnet-general-use | ~176MB | 通用场景 |
| isnet-anime | ~176MB | 动漫专用 |

## 分发应用时的注意事项

### 必需模型

如果打包分发应用，**至少包含** `u2net.onnx`（默认模型），否则用户首次使用时会自动下载（需要网络连接）。

### 打包清单

分发前确保模型文件存在：

```bash
# 检查模型是否存在
ls models/rembg/

# 如果没有，先下载
python scripts/download_models.py
```

### .gitignore 设置

模型文件较大，不应提交到 Git：

```gitignore
# Models
models/rembg/*.onnx
```

（已添加到项目 .gitignore）

## 用户侧行为

- **模型已打包**：用户开箱即用，无需下载
- **模型未打包**：首次使用时自动下载（需要网络）
- **切换模型**：如果选择的模型不存在，也会自动下载

## 自定义模型目录

如需更改模型存储位置，修改 `backend/core/smart_remove_background.py` 中的：

```python
_MODELS_DIR = _PROJECT_ROOT / 'models' / 'rembg'
```
