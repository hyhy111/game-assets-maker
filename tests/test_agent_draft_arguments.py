"""Direct draft parameters preserve omitted values and share the existing transport."""

import json

import pytest

from src.cli import agent


@pytest.fixture
def draft_cli(monkeypatch, capsys):
    calls = []
    closes = []

    class FakeService:
        def draft_operation(self, kind, patch, request_id):
            calls.append((kind, patch, request_id))
            return {"ok": True, "operation": "draft.patch", "data": {"ui_sync": "applied"}}

        def close(self):
            closes.append(True)

    monkeypatch.setattr(agent, "AgentWorkflowService", FakeService)

    def invoke(*arguments):
        result = agent.main(["draft", *arguments])
        output = json.loads(capsys.readouterr().out)
        assert closes
        return result, output

    return invoke, calls


def test_prompt_only_patch_does_not_add_defaults(draft_cli):
    invoke, calls = draft_cli
    prompt = '原地行走\n保持角色完整入画，标注 "起手"；$value 和 `符号` 保留。'
    result, output = invoke("patch", "--kind", "video", "--prompt", prompt, "--request-id", "draft-1")
    assert result == 0 and output["data"]["ui_sync"] == "applied"
    assert calls == [("video", {"prompt": prompt}, "draft-1")]


def test_video_patch_combines_only_requested_fields(draft_cli):
    invoke, calls = draft_cli
    result, _ = invoke(
        "patch", "--kind", "video", "--prompt", "原地行走", "--first-frame", "角色 图.png", "--duration", "5"
    )
    assert result == 0
    assert calls == [("video", {"prompt": "原地行走", "first_frame": "角色 图.png", "duration": 5}, None)]


def test_image_parameters_keep_numeric_strings_as_strings(draft_cli):
    invoke, calls = draft_cli
    result, _ = invoke(
        "patch",
        "--kind",
        "image",
        "--prompt",
        "123",
        "--reference-image",
        "参考 图.png",
        "--model",
        "platform-model-id",
        "--resolution",
        "1.5K",
        "--ratio",
        "3:4",
        "--count",
        "2",
    )
    assert result == 0
    assert calls == [
        (
            "image",
            {
                "prompt": "123",
                "reference_image": "参考 图.png",
                "model": "platform-model-id",
                "resolution": "1.5K",
                "ratio": "3:4",
                "count": 2,
            },
            None,
        )
    ]


def test_video_boolean_flags_can_enable_and_disable_without_adding_other_defaults(draft_cli):
    invoke, calls = draft_cli
    invoke("patch", "--kind", "video", "--generate-audio", "--no-return-last-frame")
    invoke("patch", "--kind", "video", "--no-generate-audio", "--return-last-frame")
    assert calls == [
        ("video", {"generate_audio": True, "return_last_frame": False}, None),
        ("video", {"generate_audio": False, "return_last_frame": True}, None),
    ]


@pytest.mark.parametrize(
    "kind,option,patch",
    [
        ("image", "--clear-reference-image", {"reference_image": ""}),
        ("video", "--clear-first-frame", {"first_frame": ""}),
        ("video", "--clear-last-frame", {"last_frame": None}),
        ("image", "--prompt", {"prompt": ""}),
    ],
)
def test_explicit_clearing_preserves_omitted_fields(draft_cli, kind, option, patch):
    invoke, calls = draft_cli
    arguments = ["patch", "--kind", kind, option]
    if option == "--prompt":
        arguments.append("")
    result, _ = invoke(*arguments)
    assert result == 0
    assert calls == [(kind, patch, None)]


def test_utf8_prompt_file_keeps_multiline_content_and_works_with_other_flags(tmp_path, draft_cli):
    invoke, calls = draft_cli
    prompt = '原地行走\n保留 "双引号"、$变量、反引号 ` 和结束换行。\n'
    prompt_file = tmp_path / "提示词.txt"
    prompt_file.write_text(prompt, encoding="utf-8-sig")
    result, _ = invoke("patch", "--kind", "video", "--prompt-file", str(prompt_file), "--duration", "6")
    assert result == 0
    assert calls == [("video", {"prompt": prompt, "duration": 6}, None)]


def test_json_patch_remains_compatible(tmp_path, draft_cli):
    invoke, calls = draft_cli
    patch = {"prompt": "原地行走", "generate_audio": False, "last_frame": None}
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(json.dumps(patch), encoding="utf-8-sig")
    result, _ = invoke("patch", "--kind", "video", "--patch-json", str(patch_file))
    assert result == 0
    assert calls == [("video", patch, None)]


@pytest.mark.parametrize(
    "kind,arguments",
    [
        ("image", []),
        ("image", ["--first-frame", "first.png"]),
        ("image", ["--duration", "5"]),
        ("image", ["--no-generate-audio"]),
        ("video", ["--reference-image", "reference.png"]),
        ("video", ["--count", "2"]),
        ("video", ["--patch-json", "missing.json", "--prompt", "prompt"]),
        ("video", ["--patch-json", "missing.json", "--prompt-file", "missing.txt"]),
    ],
)
def test_invalid_parameter_combinations_do_not_contact_application(draft_cli, kind, arguments):
    invoke, calls = draft_cli
    result, output = invoke("patch", "--kind", kind, *arguments)
    assert result == 1
    assert output["error"]["code"] == "INPUT_INVALID"
    assert calls == []


@pytest.mark.parametrize("content", [None, b"\xff"])
def test_unreadable_prompt_files_do_not_contact_application(tmp_path, draft_cli, content):
    invoke, calls = draft_cli
    prompt_file = tmp_path / "prompt.txt"
    if content is not None:
        prompt_file.write_bytes(content)
    result, output = invoke("patch", "--kind", "video", "--prompt-file", str(prompt_file))
    assert result == 1 and output["error"]["code"] == "INPUT_INVALID"
    assert calls == []


@pytest.mark.parametrize("content", ["[]", "not JSON"])
def test_invalid_json_patches_do_not_contact_application(tmp_path, draft_cli, content):
    invoke, calls = draft_cli
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(content, encoding="utf-8")
    result, output = invoke("patch", "--kind", "image", "--patch-json", str(patch_file))
    assert result == 1 and output["error"]["code"] == "INPUT_INVALID"
    assert calls == []


@pytest.mark.parametrize(
    "arguments",
    [
        ["--prompt", "prompt", "--prompt-file", "prompt.txt"],
        ["--reference-image", "image.png", "--clear-reference-image"],
        ["--first-frame", "image.png", "--clear-first-frame"],
        ["--last-frame", "image.png", "--clear-last-frame"],
        ["--duration", "3"],
        ["--duration", "7"],
        ["--count", "0"],
        ["--count", "5"],
    ],
)
def test_parser_rejects_conflicting_inputs_and_out_of_range_numbers(draft_cli, arguments):
    invoke, calls = draft_cli
    with pytest.raises(SystemExit) as result:
        invoke("patch", "--kind", "video", *arguments)
    assert result.value.code == 2
    assert calls == []


def test_get_draft_still_uses_read_operation(draft_cli):
    invoke, calls = draft_cli
    result, _ = invoke("get", "--kind", "video")
    assert result == 0
    assert calls == [("video", None, None)]
