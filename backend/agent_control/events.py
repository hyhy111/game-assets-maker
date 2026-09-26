"""JavaScript event builders for local Agent UI control."""

import json


def build_open_step_js(project_id: str, step: int) -> str:
    detail = {
        "projectId": project_id,
        "step": step,
    }
    detail_json = json.dumps(detail, ensure_ascii=False)
    return f"window.dispatchEvent(new CustomEvent('agent-open-step', {{ detail: {detail_json} }}));"


def build_open_seedance_js(local_task_id: str) -> str:
    detail_json = json.dumps({"localTaskId": local_task_id}, ensure_ascii=False)
    return f"window.dispatchEvent(new CustomEvent('agent-open-seedance', {{ detail: {detail_json} }}));"
