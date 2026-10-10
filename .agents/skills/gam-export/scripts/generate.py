#!/usr/bin/env python3
"""Godot Sprite Animator Generator

根据逐帧动画目录自动生成 Godot 动画配置文件（.tres）和预览场景（.tscn）
"""
import argparse
import math
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSET_SCRIPTS_DIR = SKILL_ROOT / "assets" / "Scripts"
SCRIPT_TARGETS = (
    ("animation_config.gd", "animation_config.gd.uid", "uid://c6cm0ymn1q8ji"),
    ("sprite_animator.gd", "sprite_animator.gd.uid", "uid://bxe3c7ku10pxn"),
)
ANIMATION_CONFIG_SCRIPT_PATH = "res://Scripts/animation_config.gd"
SPRITE_ANIMATOR_SCRIPT_PATH = "res://Scripts/sprite_animator.gd"
ANIMATION_CONFIG_SCRIPT_UID = "uid://c6cm0ymn1q8ji"
SPRITE_ANIMATOR_SCRIPT_UID = "uid://bxe3c7ku10pxn"


def find_godot_project_root(input_dir: str) -> Optional[Path]:
    """Find the nearest Godot project root by walking upward from input_dir/cwd."""
    candidates = [Path(input_dir).resolve(), Path.cwd().resolve()]
    for candidate in candidates:
        current = candidate if candidate.is_dir() else candidate.parent
        for parent in (current, *current.parents):
            if (parent / "project.godot").is_file():
                return parent
    return None


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Prompt for yes/no in interactive terminals."""
    if not sys.stdin.isatty():
        print(f"{prompt} [{'default: yes' if default else 'default: no'}]")
        return default
    suffix = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{suffix}]: ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in {"y", "yes", "是", "需要"}


def read_uid(uid_path: Path, fallback: str) -> str:
    """Read a Godot .uid file, falling back to the bundled UID."""
    if uid_path.is_file():
        value = uid_path.read_text(encoding="utf-8").strip()
        if value.startswith("uid://"):
            return value
    return fallback


def ensure_support_scripts(project_root: Path, overwrite_existing: Optional[bool] = None) -> None:
    """Copy bundled Godot support scripts into Scripts/ when needed."""
    scripts_dir = project_root / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    for script_name, uid_name, _uid in SCRIPT_TARGETS:
        source_script = ASSET_SCRIPTS_DIR / script_name
        source_uid = ASSET_SCRIPTS_DIR / uid_name
        target_script = scripts_dir / script_name
        target_uid = scripts_dir / uid_name

        if not source_script.is_file():
            print(f"Warning: Missing bundled asset: {source_script}")
            continue

        should_copy = True
        if target_script.exists():
            if overwrite_existing is None:
                should_copy = ask_yes_no(f"{target_script} already exists. Overwrite it?", default=False)
            else:
                should_copy = overwrite_existing

        if should_copy:
            shutil.copy2(source_script, target_script)
            if source_uid.is_file():
                shutil.copy2(source_uid, target_uid)
            print(f"Installed support script: {target_script}")
        else:
            print(f"Keeping existing support script: {target_script}")


def configure_script_uids(project_root: Path) -> None:
    """Use the actual script UIDs present in the target Godot project."""
    global ANIMATION_CONFIG_SCRIPT_UID, SPRITE_ANIMATOR_SCRIPT_UID

    scripts_dir = project_root / "Scripts"
    ANIMATION_CONFIG_SCRIPT_UID = read_uid(
        scripts_dir / "animation_config.gd.uid",
        ANIMATION_CONFIG_SCRIPT_UID,
    )
    SPRITE_ANIMATOR_SCRIPT_UID = read_uid(
        scripts_dir / "sprite_animator.gd.uid",
        SPRITE_ANIMATOR_SCRIPT_UID,
    )


def get_res_path(input_dir: str) -> str:
    """Convert input path to Godot res:// path

    Handles both relative and absolute paths.
    If absolute path is within project, extracts relative part.
    """
    input_path = Path(input_dir).resolve()
    cwd = Path.cwd().resolve()

    # If input path starts with cwd, get relative path
    try:
        rel_path = input_path.relative_to(cwd)
        return str(rel_path).replace('\\', '/')
    except ValueError:
        # Not relative to cwd, use as-is but normalized
        return str(input_path).replace('\\', '/')


def to_snake_case(name: str) -> str:
    """Convert CamelCase or PascalCase to snake_case"""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def generate_uid() -> str:
    """Generate a Godot-style UID"""
    import random
    import string
    chars = string.ascii_lowercase + string.digits
    return 'uid://' + ''.join(random.choices(chars, k=13))


def read_frame_data(json_path: str) -> Optional[Dict]:
    """Read and parse _frame_data.json file"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Warning: Failed to read {json_path}: {e}")
        return None


def natural_key(path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def local_file(directory, name):
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe asset path: {name}")
    return path


def discover_animations(input_dir: str, fps: float = 10.0) -> List[Dict]:
    """Read one action directory or immediate action subdirectories."""
    root = Path(input_dir).resolve()
    def has_frames(directory):
        return (directory / '_frame_data.json').exists() or any(directory.glob('*.png'))
    directories = [root] if has_frames(root) else [p for p in sorted(root.iterdir()) if p.is_dir() and has_frames(p)]
    animations = []
    names = set()
    for directory in directories:
        manifest = directory / '_frame_data.json'
        frames = []
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding='utf-8'))
            name = data.get('animation_name') or data.get('action') or directory.name
            for item in sorted(data['frames'], key=lambda item: item['frame_index']):
                local_file(directory, item['output_name'])
                frames.append({'index': len(frames), 'filename': item['output_name'], 'offset': item.get('offset', {'x': 0, 'y': 0})})
        else:
            name = directory.name
            for file in sorted(directory.glob('*.png'), key=natural_key):
                local_file(directory, file.name)
                frames.append({'index': len(frames), 'filename': file.name, 'offset': {'x': 0, 'y': 0}})
        if not frames:
            raise ValueError(f"No frames in {directory}")
        if not name or any(char in name for char in '/\\\n\r') or name in ('.', '..'):
            raise ValueError(f'Unsafe animation name: {name}')
        if name in names:
            raise ValueError(f"Duplicate animation name: {name}")
        names.add(name)
        audio_path = directory / '_audio_timeline.json'
        audio = json.loads(audio_path.read_text(encoding='utf-8')) if audio_path.exists() else {}
        if audio and audio.get('version') != 1:
            raise ValueError(f"Unsupported audio timeline version: {audio_path}")
        animation_fps = float(audio.get('animation_fps') or fps)
        if not math.isfinite(animation_fps) or animation_fps <= 0:
            raise ValueError(f"Invalid animation FPS: {directory}")
        clips = audio.get('clips', [])
        for clip in clips:
            index = clip['placement_frame']
            if type(index) is not int or not 0 <= index < len(frames):
                raise ValueError(f"Audio trigger outside exported frames: {clip}")
            local_file(directory, clip['file'])
        animations.append({'name': name, 'directory': directory.relative_to(root).as_posix(), 'frames': frames,
                           'fps': animation_fps, 'audio_clips': clips, 'loop': name.lower() in ('idle', 'walk', 'run')})
    return animations


def gd_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def generate_tres(animation: Dict, prefix: str, output_dir: str) -> str:
    """
    Generate .tres config file for an animation
    Returns the generated filename
    """
    anim_name = animation['name']
    frames = animation['frames']

    # Generate snake_case filename
    filename = f"{prefix}_{to_snake_case(anim_name)}_config.tres"
    filepath = os.path.join(output_dir, filename)

    # Generate UID
    resource_uid = generate_uid()
    script_uid = ANIMATION_CONFIG_SCRIPT_UID

    # Build frame_offsets dictionary
    frame_offsets_lines = []
    for frame in frames:
        idx = frame['index']
        offset = frame['offset']
        x = offset.get('x', 0.0)
        y = offset.get('y', 0.0)
        # Use integer if no decimal part
        x_str = str(int(x)) if x == int(x) else str(x)
        y_str = str(int(y)) if y == int(y) else str(y)
        frame_offsets_lines.append(f"{idx}: Vector2({x_str}, {y_str})")

    audio_resources = []
    audio_events = []
    for index, clip in enumerate(animation.get('audio_clips', []), start=2):
        path = f"res://{animation['res_directory']}/{clip['file']}"
        audio_resources.append(f'[ext_resource type="AudioStream" path={gd_string(path)} id="{index}_audio"]')
        audio_events.append(f'{{"frame": {clip["placement_frame"]}, "stream": ExtResource("{index}_audio")}}')

    # Write config with paths; Godot assigns authoritative resource UIDs.
    content = f"""[gd_resource type="Resource" script_class="AnimationConfig" load_steps={2 + len(audio_resources)} format=3]

[ext_resource type="Script" path="{ANIMATION_CONFIG_SCRIPT_PATH}" id="1_7vnq7"]
{chr(10).join(audio_resources)}

[resource]
script = ExtResource("1_7vnq7")
animation_name = {gd_string(anim_name)}
frame_offsets = {{
{chr(10).join('  ' + line + ',' for line in frame_offsets_lines)}
}}
audio_events = [{", ".join(audio_events)}]
"""

    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Generated: {filepath}")
    return filename


def generate_tscn(animations: List[Dict], prefix: str, input_dir: str, output_dir: str):
    """Generate .tscn scene file with SpriteFrames and animation configs"""
    input_path = Path(input_dir)
    scene_name = prefix
    filepath = os.path.join(output_dir, f"{scene_name}.tscn")

    # Get the relative path from project root for res://
    res_path = get_res_path(input_dir)

    # Generate UIDs
    scene_uid = generate_uid()
    animator_script_uid = SPRITE_ANIMATOR_SCRIPT_UID
    config_script_uid = ANIMATION_CONFIG_SCRIPT_UID
    spriteframes_uid = generate_uid()

    # Collect all texture resources
    ext_resources = []
    texture_ids = {}
    current_id = 1

    for anim in animations:
        anim_name = anim['name']
        subdir = anim['directory']

        for frame in anim['frames']:
            texture_path = f"res://{res_path}/{subdir}/{frame['filename']}"
            if texture_path not in texture_ids:
                texture_uid = generate_uid()
                texture_id = f"{current_id}_{to_snake_case(anim_name)}{frame['index']:03d}"
                texture_ids[texture_path] = texture_id
                ext_resources.append(
                    f'[ext_resource type="Texture2D" path={gd_string(texture_path)} id="{texture_id}"]'
                )
                current_id += 1

    # Add script and config resources
    ext_resources.append(
        f'[ext_resource type="Script" path="{SPRITE_ANIMATOR_SCRIPT_PATH}" id="{current_id}_animator"]'
    )
    animator_id = current_id
    current_id += 1

    ext_resources.append(
        f'[ext_resource type="Script" path="{ANIMATION_CONFIG_SCRIPT_PATH}" id="{current_id}_7vnq7"]'
    )
    config_script_id = current_id
    current_id += 1

    # Add AnimationConfig resources
    config_ids = {}
    for anim in animations:
        config_uid = generate_uid()
        anim_name = anim['name']
        config_id = f"{current_id}_{to_snake_case(anim_name)}cfg"
        config_ids[anim_name] = config_id
        config_path = f"res://Resources/Animations/{prefix}/{prefix}_{to_snake_case(anim_name)}_config.tres"
        ext_resources.append(
            f'[ext_resource type="Resource" path={gd_string(config_path)} id="{config_id}"]'
        )
        current_id += 1

    # Build SpriteFrames animations
    anim_entries = []
    for anim in animations:
        anim_name = anim['name']
        subdir = anim['directory']

        # Determine if animation should loop (idle, walk, run typically loop)
        loop = anim['loop']

        # Build frames array properly
        frame_textures = []
        for frame in anim['frames']:
            tex_path = f"res://{res_path}/{subdir}/{frame['filename']}"
            frame_textures.append(f'{{"duration": 1.0, "texture": ExtResource("{texture_ids[tex_path]}")}}')
        frames_str = ', '.join(frame_textures)

        anim_entries.append(f'''{{
"frames": [{frames_str}],
"loop": {str(loop).lower()},
"name": &{gd_string(anim_name)},
"speed": {anim["fps"]}
}}''')

    # Build animation_configs array reference
    config_refs = ', '.join([f'ExtResource("{config_ids[anim["name"]]}")' for anim in animations])

    # Write .tscn file
    content = f'''[gd_scene load_steps={current_id + 1} format=3]

{chr(10).join(ext_resources)}

[sub_resource type="SpriteFrames" id="SpriteFrames_{to_snake_case(scene_name)}"]
animations = [{','.join(anim_entries)}]

[node name="{scene_name}" type="AnimatedSprite2D"]
sprite_frames = SubResource("SpriteFrames_{to_snake_case(scene_name)}")
animation = &{gd_string(animations[0]["name"])}
autoplay = {gd_string(animations[0]["name"])}
position = Vector2(320, 360)
script = ExtResource("{animator_id}_animator")
animation_configs = Array[ExtResource("{config_script_id}_7vnq7")]([{config_refs}])
'''

    os.makedirs(output_dir, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Generated: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Export GAM frames and frame-triggered audio to Godot 4")
    parser.add_argument('input_dir', type=Path)
    parser.add_argument('prefix', nargs='?')
    parser.add_argument('--project', type=Path, help='Target Godot project root')
    parser.add_argument('--fps', type=float, default=10.0, help='Fallback FPS when no audio manifest exists')
    parser.add_argument('--loop', action='append', default=[], help='Additional looping animation name (repeatable)')
    parser.add_argument('--yes', action='store_true', help='Overwrite generated outputs and support scripts')
    parser.add_argument('--skip-scripts', action='store_true')
    args = parser.parse_args()
    source = args.input_dir.resolve()
    if not source.is_dir():
        parser.error('Input must be an existing directory')
    project = args.project.resolve() if args.project else find_godot_project_root(str(source))
    if project is None or not (project / 'project.godot').is_file():
        parser.error('Provide --project pointing to a Godot 4 project')
    prefix = args.prefix or to_snake_case(source.name)
    if not prefix or any(char in prefix for char in '/\\"') or prefix in ('.', '..'):
        parser.error('Prefix must be a single safe filename component')
    animations = discover_animations(str(source), args.fps)
    if not animations:
        parser.error('No PNG animations found')
    filenames = [f"{prefix}_{to_snake_case(anim['name'])}_config.tres" for anim in animations]
    if len(set(filenames)) != len(filenames):
        parser.error('Animation names collide after filename normalization')
    destination = source if source.is_relative_to(project) else project / 'ArtAssets' / prefix
    outputs = [project / 'Resources/Animations' / prefix / name for name in filenames]
    outputs.append(project / 'Scenes/Animator' / f'{prefix}.tscn')
    if not args.yes and (any(path.exists() for path in outputs) or (destination != source and destination.exists())):
        parser.error('Output exists; inspect it before explicitly using --yes')
    for script_name, _, _ in SCRIPT_TARGETS:
        existing = project / 'Scripts' / script_name
        bundled = ASSET_SCRIPTS_DIR / script_name
        if existing.exists() and existing.read_bytes() != bundled.read_bytes() and not args.yes:
            if not args.skip_scripts or (script_name == 'animation_config.gd' and 'audio_events' not in existing.read_text()) or (script_name == 'sprite_animator.gd' and '_trigger_audio' not in existing.read_text()):
                parser.error(f'Support script differs: {existing}; review before --yes or provide compatible scripts with --skip-scripts')
    if destination != source:
        for anim in animations:
            action_dir = destination / anim['directory']
            action_dir.mkdir(parents=True, exist_ok=True)
            for name in [f['filename'] for f in anim['frames']] + [c['file'] for c in anim['audio_clips']]:
                shutil.copy2(source / anim['directory'] / name, action_dir / name)
            for name in ('_frame_data.json', '_audio_timeline.json'):
                metadata = source / anim['directory'] / name
                if metadata.exists():
                    shutil.copy2(metadata, action_dir / name)
    if not args.skip_scripts:
        ensure_support_scripts(project, True if args.yes else None)
    os.chdir(project)
    for anim in animations:
        anim['res_directory'] = (destination / anim['directory']).relative_to(project).as_posix()
        if anim['name'] in args.loop:
            anim['loop'] = True
        generate_tres(anim, prefix, str(project / 'Resources/Animations' / prefix))
    generate_tscn(animations, prefix, str(destination), str(project / 'Scenes/Animator'))
    print(f"Exported {len(animations)} animations and {sum(len(a['audio_clips']) for a in animations)} audio events")


if __name__ == '__main__':
    main()
