# Test Fixtures

原始真实素材只放在被 Git 忽略的 `tests/private_media/`，按角色/动作组织：

```text
tests/private_media/
  <role>/
    <action>.mp4
```

这里可能包含人物、客户或未发布内容；不要用 `git add -f` 提交，也不要把原始路径或内容写入测试报告。
从仓库根目录生成最多 3 帧、最大边 256 像素的紧凑回归视频：

```bash
uv run python scripts/generate_test_fixtures.py \
  --source tests/private_media \
  --max-frames 3 \
  --max-dimension 256 \
  --skip-rembg
```

紧凑素材输出到同样被忽略的 `tests/fixtures/videos/`，保留 `<role>/<action>.mp4` 结构。生成器只读取原始视频，不会复制原文件；`--skip-rembg` 保证素材生成不需要模型。省略该参数时也只会使用已经存在的本地模型，不会下载模型。

测试素材目录结构：

```text
tests/fixtures/
  videos/
    <role>/
      <action>.mp4
  trim_sources/
    <role>/
      <action>/
        frame_000001.png
        frame_000002.png
  legacy_projects/
    <action>/
      cache/global_params.json
      output/02_no_bg/*.png
```

The pytest suite uses these assets when present. If they are missing, it generates
small synthetic videos and transparent PNG frames in a temporary directory so the
default tests remain self-contained.
