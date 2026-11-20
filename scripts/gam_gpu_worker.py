"""Standalone JSON-lines CUDA worker, bundled without any ONNX Runtime."""

import ctypes
import importlib.abc
import json
import os
import sys
from pathlib import Path


class NoTorch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "torchvision", "torchaudio"}:
            raise ImportError("PyTorch is not part of the GPU runtime")


def loaded_modules():
    from ctypes import wintypes as w

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    psapi.EnumProcessModules.argtypes = [w.HANDLE, ctypes.POINTER(w.HMODULE), w.DWORD, ctypes.POINTER(w.DWORD)]
    psapi.GetModuleFileNameExW.argtypes = [w.HANDLE, w.HMODULE, w.LPWSTR, w.DWORD]
    process = kernel.GetCurrentProcess()
    array = (w.HMODULE * 4096)()
    needed = w.DWORD()
    if not psapi.EnumProcessModules(process, array, ctypes.sizeof(array), ctypes.byref(needed)):
        raise OSError("Cannot inspect worker module origins")
    paths = []
    for handle in array[: needed.value // ctypes.sizeof(w.HMODULE)]:
        buffer = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process, handle, buffer, len(buffer)):
            paths.append(buffer.value)
    return paths


def main():
    site = Path(sys.argv[1]).resolve()
    sys.meta_path.insert(0, NoTorch())
    sys.path.insert(0, str(site))
    ctypes.windll.kernel32.SetDefaultDllDirectories(0x1000)
    directories = [site / "nvidia/cu13/bin/x86_64", site / "nvidia/cudnn/bin", site / "onnxruntime/capi"]
    handles = [os.add_dll_directory(str(directory)) for directory in directories]
    import numpy as np
    import onnxruntime as ort
    from PIL import Image, ImageChops

    if not Path(ort.__file__).resolve().is_relative_to(site):
        raise ImportError("ONNX Runtime loaded outside verified component directory")
    ort.preload_dlls(cuda=True, cudnn=False, msvc=False, directory=str(directories[0]))
    ort.preload_dlls(cuda=False, cudnn=True, msvc=False, directory=str(directories[1]))
    session = None
    current_model = None
    cuda_nodes = None
    for line in sys.stdin:
        stage = "protocol"
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("op") not in {"infer", "probe"}:
                raise ValueError("Invalid GPU request")
            model = request["model_path"]
            if current_model != model:
                stage = "initialization"
                session = None
                current_model = None
                cuda_nodes = None
                options = ort.SessionOptions()
                options.enable_profiling = True
                options.profile_file_prefix = str(site / "cuda-proof")
                options.intra_op_num_threads = 8
                session = ort.InferenceSession(
                    model,
                    sess_options=options,
                    providers=[("CUDAExecutionProvider", {"use_tf32": 0}), "CPUExecutionProvider"],
                )
                current_model = model
            if request["op"] == "infer":
                with Image.open(request["input"]) as source:
                    image = source.convert("RGBA")
                rgb = image.convert("RGB").resize((1024, 1024), Image.Resampling.BILINEAR)
                array = np.asarray(rgb, dtype=np.float32) / 255
                array = (array - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
                    [0.229, 0.224, 0.225], np.float32
                )
                tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None])
            else:
                tensor = np.zeros((1, 3, 1024, 1024), dtype=np.float32)
            stage = "inference"
            logits = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
            if not np.isfinite(logits).all():
                raise ValueError("Non-finite model output")
            alpha = np.exp(-np.logaddexp(0, -logits))
            if request["op"] == "infer":
                mask = Image.fromarray((alpha * 255).astype(np.uint8)).resize(image.size, Image.Resampling.LANCZOS)
                image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
                image.save(request["output"])
            if cuda_nodes is None:
                profile = session.end_profiling()
                events = json.loads(Path(profile).read_text())
                cuda_nodes = sum(event.get("args", {}).get("provider") == "CUDAExecutionProvider" for event in events)
                if not cuda_nodes:
                    raise RuntimeError("No nodes executed on CUDA; check NVIDIA driver and device")
            if request["op"] == "probe":
                modules = loaded_modules()
                if any("/torch/" in module.replace("\\", "/").lower() for module in modules):
                    raise ImportError("Undeclared PyTorch DLL loaded")
                result = {
                    "cuda_nodes": cuda_nodes,
                    "profile": profile,
                    "modules": modules,
                    "ort_module": ort.__file__,
                    "python": sys.executable,
                    "frozen": bool(getattr(sys, "frozen", False)),
                }
                session = None
                current_model = None
            else:
                result = {
                    "output": request["output"],
                    "finite_alpha": True,
                    "cuda_nodes": cuda_nodes,
                    "profile": profile,
                }
            print(json.dumps(result), flush=True)
        except Exception as error:
            message = str(error)
            lowered = message.lower()
            if any(
                token in lowered
                for token in (
                    "out of memory",
                    "failed to allocate",
                    "cudaerrormemoryallocation",
                    "cudnn_status_alloc_failed",
                    "bfcarena::allocaterawinternal",
                )
            ):
                code = "GPU_OUT_OF_MEMORY"
            elif any(token in lowered for token in ("cuda failure", "driver", "no cuda", "no nodes")):
                code = "GPU_DEVICE_INCOMPATIBLE"
            elif stage == "protocol":
                code = "GPU_PROTOCOL_FAILED"
            elif stage == "initialization":
                code = "GPU_MODEL_INITIALIZATION_FAILED"
            else:
                code = "GPU_INFERENCE_FAILED"
            session = None
            current_model = None
            cuda_nodes = None
            print(json.dumps({"error": {"code": code, "message": message}}), flush=True)
    del handles


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error": {"code": "GPU_NATIVE_LOAD_FAILED", "message": str(error)}}), flush=True)
