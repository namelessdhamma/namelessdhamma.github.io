#!/usr/bin/env python3
"""ND Kaggle LTX 2B first/last worker via direct LTX pipeline + MMGP.

FREE_ONLY candidate for Kaggle T4. Designed to avoid the 86 GiB LTX-13B
dataset mount and use the compact mounted LTX 2B 0.9.6 diffusers BF16 stack.
"""
from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

WORK = Path("/kaggle/working")
ROOT = WORK / "Wan2GP"
CK = ROOT / "ckpts"
T5 = CK / "T5_xxl_1.1"
TMP = Path("/tmp/nd-ltx2b-f2l")
FPS = 28  # 57-frame 2s lattice: 57/28 = 2.036s; avoids 65-frame T4 performance cliff
WANGP_COMMIT = "2345ae148f82740f66e82c41292dbbdd592e713d"
LTX_CONFIG_COMMIT = "4b2d053057623ddd4d0a1d3e9cd28890e9ef487f"
MODEL_NAME = "diffusion_pytorch_model.bf16.safetensors"
MODEL_REPO = "multimodalart/ltxv-2b-0.9.6-distilled"
MODEL_REL = "transformer/diffusion_pytorch_model.bf16.safetensors"
TEXT_ENCODER = "T5_xxl_1.1_enc_quanto_bf16_int8.safetensors"
DEFAULT_NEGATIVE = "worst quality, blurry, jittery, distorted, sudden cut, duplicate subject, text, watermark"


def run(cmd: list[str], timeout: int) -> str:
    env = {**os.environ, "PIP_NO_CACHE_DIR": "1", "HF_HOME": str(WORK / "hf-cache")}
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        env=env,
    )
    if p.returncode != 0:
        print("ND_LTX2B_CMD_FAIL " + repr(cmd) + "\n" + p.stdout[-12000:], flush=True)
        raise RuntimeError("command failed: " + repr(cmd))
    return p.stdout


def align32(v: int) -> int:
    return max(256, (int(v) // 32) * 32)


def frame_count(seconds: float) -> int:
    raw = max(0.6, min(6.0, float(seconds))) * FPS
    k = max(2, math.ceil((raw - 1) / 8))
    return min(121, 8 * k + 1)


def download(url: str, path: Path) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValueError("start/end image must be an http(s) URL")
    req = urllib.request.Request(url, headers={"User-Agent": "nd-kaggle-ltx2b/1.0"})
    with urllib.request.urlopen(req, timeout=120) as src, path.open("wb") as dst:
        total = 0
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 20 * 1024 * 1024:
                raise ValueError("input image exceeds 20 MiB")
            dst.write(chunk)


def materialize_image(request: dict, key: str, path: Path) -> None:
    inline = request.get(f"{key}_image_base64")
    if inline:
        raw = base64.b64decode(str(inline))
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise ValueError(f"{key} inline image is empty or too large")
        path.write_bytes(raw)
        return
    download(str(request.get(f"{key}_image_url") or ""), path)


def find_cached_file(name: str) -> Path | None:
    base = Path("/kaggle/input")
    if not base.exists():
        return None
    candidates = list(base.glob(f"**/{name}"))
    candidates = [p for p in candidates if p.is_file()]
    return candidates[0] if candidates else None


def link_or_copy_cached(name: str, dest: Path) -> bool:
    src = find_cached_file(name)
    if src is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dest.exists():
            dest.unlink()
        os.symlink(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    print(f"ND_LTX2B_CACHE_HIT={name}", flush=True)
    return True


def prepare_runtime() -> tuple[Path, Path, Path]:
    print("ND_LTX2B_STAGE=prepare_runtime", flush=True)
    if not ROOT.exists():
        run(["git", "clone", "--filter=blob:none", "https://github.com/deepbeepmeep/Wan2GP.git", str(ROOT)], 240)
        run(["git", "-C", str(ROOT), "checkout", WANGP_COMMIT], 90)

    # Kaggle/hosted notebook images may preload NumPy. Installing Wan2GP can replace
    # NumPy/SciPy on disk, so restart once into a clean interpreter before importing
    # the scientific stack. This avoids mixed in-memory/on-disk binary state.
    if os.environ.get("ND_LTX2B_RUNTIME_READY") != "1":
        minimal_requirements = [
            "mmgp==3.8.1",
            "diffusers==0.36.0",
            "transformers==4.54.0",
            "tokenizers>=0.20.3",
            "accelerate>=1.1.1",
            "tqdm",
            "imageio",
            "imageio-ffmpeg",
            "einops",
            "rotary-embedding-torch>=0.5.3",
            "sentencepiece",
            "numpy==2.1.2",
            "scipy",
            "opencv-python-headless>=4.12.0.88",
            "av",
            "pyyaml",
            "safetensors",
            "huggingface_hub[hf_xet]",
            "hf_xet>=1.5.2",
        ]
        run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "--disable-pip-version-check", *minimal_requirements], 900)
        env = dict(os.environ)
        env["ND_LTX2B_RUNTIME_READY"] = "1"

        probe_code = (
            "import importlib.metadata as im;"
            "import numpy,scipy,transformers;"
            "print('ND_LTX2B_IMPORT_VERSIONS='+repr({"
            "'numpy':numpy.__version__,'scipy':scipy.__version__,"
            "'transformers':transformers.__version__,"
            "'optimum_quanto':im.version('optimum-quanto'),"
            "'mmgp':im.version('mmgp')}),flush=True);"
            "from mmgp import offload;"
            "print('ND_LTX2B_IMPORT_PROBE=mmgp_offload_ok',flush=True)"
        )
        probe = subprocess.run(
            [sys.executable, "-c", probe_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            timeout=180,
        )
        print(f"ND_LTX2B_IMPORT_PROBE_RC={probe.returncode}", flush=True)
        if probe.stdout:
            print(probe.stdout[-12000:], flush=True)
        if probe.returncode != 0:
            raise RuntimeError("LTX2B import probe failed")

        worker_path = Path(sys.argv[0]).resolve()
        print("ND_LTX2B_STAGE=clean_child_begin", flush=True)
        child_started = time.time()
        child = subprocess.Popen(
            [sys.executable, str(worker_path), sys.argv[1]],
            env=env,
        )
        next_heartbeat = child_started + 20.0
        while True:
            rc = child.poll()
            if rc is not None:
                break
            now = time.time()
            if now >= next_heartbeat:
                print(
                    "ND_LTX2B_PARENT_HEARTBEAT elapsed_s="
                    + str(round(now - child_started, 1)),
                    flush=True,
                )
                next_heartbeat = now + 20.0
            time.sleep(2.0)
        print(f"ND_LTX2B_STAGE=clean_child_rc_{rc}", flush=True)
        raise SystemExit(rc)

    from huggingface_hub import hf_hub_download

    CK.mkdir(parents=True, exist_ok=True)
    T5.mkdir(parents=True, exist_ok=True)

    mounted_models = [p for p in Path("/kaggle/input").glob(f"**/{MODEL_NAME}") if p.is_file()]
    if mounted_models:
        model = mounted_models[0]
        print(f"ND_LTX2B_CACHE_HIT={model}", flush=True)
    else:
        model = Path(hf_hub_download(MODEL_REPO, MODEL_REL, local_dir=str(CK)))

    te = T5 / TEXT_ENCODER
    if not te.exists() and not link_or_copy_cached(TEXT_ENCODER, te):
        te = Path(hf_hub_download("DeepBeepMeep/LTX_Video", f"T5_xxl_1.1/{TEXT_ENCODER}", local_dir=str(CK)))

    aux = [
        "T5_xxl_1.1/added_tokens.json",
        "T5_xxl_1.1/special_tokens_map.json",
        "T5_xxl_1.1/spiece.model",
        "T5_xxl_1.1/tokenizer_config.json",
        "ltxv_0.9.7_VAE.safetensors",
        "ltxv_0.9.7_spatial_upscaler.safetensors",
        "ltxv_scheduler.json",
    ]
    for rel in aux:
        dest = CK / rel
        if dest.exists():
            continue
        if link_or_copy_cached(Path(rel).name, dest):
            continue
        hf_hub_download("DeepBeepMeep/LTX_Video", rel, local_dir=str(CK))

    cfg = WORK / "ltxv-2b-0.9.6-distilled.yaml"
    if not cfg.exists():
        cfg.write_bytes(
            urllib.request.urlopen(
                f"https://raw.githubusercontent.com/Lightricks/LTX-Video/{LTX_CONFIG_COMMIT}/configs/ltxv-2b-0.9.6-distilled.yaml",
                timeout=60,
            ).read()
        )

    mounted_cfg = list(Path("/kaggle/input").glob("**/ltxv-2b-distilled/transformer/config.json"))
    source_cfg = mounted_cfg[0] if mounted_cfg else None
    if source_cfg is None:
        source_cfg = CK / "nd_ltx2b_source_config.json"
        urllib.request.urlretrieve(
            "https://huggingface.co/multimodalart/ltxv-2b-0.9.6-distilled/resolve/main/transformer/config.json?download=true",
            str(source_cfg),
        )
    cfg_obj = json.loads(Path(source_cfg).read_text(encoding="utf-8"))
    cfg_obj.update(
        {
            "_class_name": "Transformer3DModel",
            "_diffusers_version": "0.25.1",
            "_name_or_path": "PixArt-alpha/PixArt-XL-2-256x256",
            "activation_fn": "gelu-approximate",
            "attention_bias": True,
            "attention_head_dim": 64,
            "attention_type": "default",
            "caption_channels": 4096,
            "cross_attention_dim": 2048,
            "double_self_attention": False,
            "dropout": 0.0,
            "in_channels": 128,
            "norm_elementwise_affine": False,
            "norm_eps": 1e-6,
            "norm_num_groups": 32,
            "num_attention_heads": 32,
            "num_embeds_ada_norm": 1000,
            "num_layers": 28,
            "num_vector_embeds": None,
            "only_cross_attention": False,
            "out_channels": 128,
            "project_to_2d_pos": True,
            "upcast_attention": False,
            "use_linear_projection": False,
            "qk_norm": "rms_norm",
            "standardization_norm": "rms_norm",
            "positional_embedding_type": "rope",
            "positional_embedding_theta": 10000.0,
            "positional_embedding_max_pos": [20, 2048, 2048],
            "timestep_scale_multiplier": 1000,
        }
    )
    forced_cfg = CK / "nd_ltx2b_transformer_config.json"
    forced_cfg.write_text(json.dumps(cfg_obj), encoding="utf-8")

    ltxv_py = ROOT / "models" / "ltx_video" / "ltxv.py"
    src = ltxv_py.read_text(encoding="utf-8")

    phase_progress_import = "from shared.utils.phase_progress import generation_progress"
    if phase_progress_import in src:
        src = src.replace(
            phase_progress_import,
            "def generation_progress(method):\n    return method",
            1,
        )

    heavy_utils_import = "from shared.utils.utils import calculate_new_dimensions"
    if heavy_utils_import in src:
        minimal_dims = """def calculate_new_dimensions(canvas_height, canvas_width, image_height, image_width, fit_into_canvas, block_size=16):
    if fit_into_canvas is None or fit_into_canvas == 2:
        return canvas_height, canvas_width
    if fit_into_canvas == 1:
        scale = max(
            min(canvas_height / image_height, canvas_width / image_width),
            min(canvas_width / image_height, canvas_height / image_width),
        )
    else:
        scale = (canvas_height * canvas_width / (image_height * image_width)) ** 0.5
    new_height = round(image_height * scale / block_size) * block_size
    new_width = round(image_width * scale / block_size) * block_size
    return new_height, new_width"""
        src = src.replace(heavy_utils_import, minimal_dims, 1)

    needle = "offload.fast_load_transformers_model(model_filepath, modelClass=Transformer3DModel, writable_tensors=False)"
    replacement = (
        "offload.fast_load_transformers_model("
        "model_filepath, modelClass=Transformer3DModel, writable_tensors=False, "
        "forcedConfigPath=os.environ['ND_LTX_TRANSFORMER_CONFIG_PATH'], "
        "preprocess_sd={**{'proj_in':'patchify_proj','time_embed':'adaln_single'}, "
        "**{f'transformer_blocks.{i}.{a}.{src}':f'transformer_blocks.{i}.{a}.{dst}' "
        "for i in range(28) for a in ['attn1','attn2'] "
        "for src,dst in [('norm_q','q_norm'),('norm_k','k_norm')]}})"
    )
    if needle not in src and "ND_LTX_TRANSFORMER_CONFIG_PATH" not in src:
        raise RuntimeError("Wan2GP LTX loader patch point missing")
    if needle in src:
        src = src.replace(needle, replacement, 1)

    heavy_utils_import = "from shared.utils.utils import calculate_new_dimensions"
    lightweight_calculate_new_dimensions = """def calculate_new_dimensions(canvas_height, canvas_width, image_height, image_width, fit_into_canvas, block_size=16):
    if fit_into_canvas is None or fit_into_canvas == 2:
        return canvas_height, canvas_width
    if fit_into_canvas == 1:
        scale1 = min(canvas_height / image_height, canvas_width / image_width)
        scale2 = min(canvas_width / image_height, canvas_height / image_width)
        scale = max(scale1, scale2)
    else:
        scale = (canvas_height * canvas_width / (image_height * image_width)) ** (1 / 2)
    new_height = round(image_height * scale / block_size) * block_size
    new_width = round(image_width * scale / block_size) * block_size
    return new_height, new_width
"""
    if heavy_utils_import in src:
        src = src.replace(heavy_utils_import, lightweight_calculate_new_dimensions, 1)

    import_markers = [
        ("from shared.utils.phase_progress import generation_progress", "phase_progress"),
        ("from mmgp import offload", "mmgp_offload"),
        ("from diffusers.utils import logging", "diffusers_logging"),
        ("import imageio", "imageio"),
        ("import numpy as np", "numpy"),
        ("import torch", "torch"),
        ("from safetensors import safe_open", "safetensors"),
        ("from huggingface_hub import hf_hub_download", "huggingface_hub"),
        ("from .models.transformers.symmetric_patchifier import SymmetricPatchifier", "patchifier"),
        ("from .models.transformers.transformer3d import Transformer3DModel", "transformer3d"),
        ("from .schedulers.rf import RectifiedFlowScheduler", "scheduler"),
        ("from .utils.skip_layer_strategy import SkipLayerStrategy", "skip_layer"),
        ("from .models.autoencoders.latent_upsampler import LatentUpsampler", "latent_upsampler"),
        ("from .pipelines import crf_compressor", "crf_compressor"),
        ("import cv2", "cv2"),
        ("from shared.utils import files_locator as fl", "files_locator"),
    ]
    for statement, marker in import_markers:
        if statement in src:
            src = src.replace(
                statement,
                statement + "\nprint('ND_LTX2B_LTXV_IMPORT=" + marker + "', flush=True)",
                1,
            )
    ltxv_py.write_text(src, encoding="utf-8")

    # Headless LTX uses shared.utils submodules directly. The package initializer
    # imports unrelated solver modules and can destabilize the constrained Kaggle runtime.
    utils_init = ROOT / "shared" / "utils" / "__init__.py"
    utils_init.write_text("__all__ = []\n", encoding="utf-8")

    pipeline_py = ROOT / "models" / "ltx_video" / "pipelines" / "pipeline_ltx_video.py"
    pipeline_src = pipeline_py.read_text(encoding="utf-8")
    enhancer_import = "from shared.prompt_enhancer.prompt_enhance_utils import generate_cinematic_prompt"
    if enhancer_import in pipeline_src:
        pipeline_src = pipeline_src.replace(
            enhancer_import,
            "def generate_cinematic_prompt(prompt, *args, **kwargs):\n    return prompt",
            1,
        )
        pipeline_py.write_text(pipeline_src, encoding="utf-8")

    # Direct headless candidate: eliminate progress/UI imports from the base pipeline.
    pipeline_src = pipeline_py.read_text(encoding="utf-8")
    progress_import = "from shared.utils.phase_progress import control_video_encoding, text_encoding_prompts, text_encoding_progress"
    if progress_import in pipeline_src:
        pipeline_src = pipeline_src.replace(
            progress_import,
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def control_video_encoding(*args, **kwargs):\n    yield\n"
            "@contextmanager\n"
            "def text_encoding_prompts(*args, **kwargs):\n    yield\n"
            "@contextmanager\n"
            "def text_encoding_progress(*args, **kwargs):\n    yield",
            1,
        )
        pipeline_py.write_text(pipeline_src, encoding="utf-8")

    text_cache_py = ROOT / "shared" / "utils" / "text_encoder_cache.py"
    text_cache_src = text_cache_py.read_text(encoding="utf-8")
    cache_progress_import = "from shared.utils.phase_progress import text_encoding_prompts"
    if cache_progress_import in text_cache_src:
        text_cache_src = text_cache_src.replace(
            cache_progress_import,
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def text_encoding_prompts(*args, **kwargs):\n    yield",
            1,
        )
        text_cache_py.write_text(text_cache_src, encoding="utf-8")

    os.environ["ND_LTX_TRANSFORMER_CONFIG_PATH"] = str(forced_cfg)
    print("ND_LTX2B_STAGE=transformer_config_ready", flush=True)
    return model, te, cfg


def pil_to_tensor(img, width: int, height: int):
    import numpy as np
    import torch
    from PIL import Image
    im = img.convert("RGB").resize((width, height), Image.LANCZOS)
    arr = np.asarray(im, dtype=np.float32)
    t = torch.from_numpy(arr).permute(2, 0, 1).contiguous()
    return t.div(127.5).sub(1.0)


def mae(a, b, size):
    import numpy as np
    aa = np.asarray(a.resize(size), dtype=np.float32)
    bb = np.asarray(b.resize(size), dtype=np.float32)
    return float(np.mean(np.abs(aa - bb)))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: kaggle_ltx2b_wan2gp_worker.py request.json")
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    # Current Kaggle runtime compatibility: the qualified import probe proves
    # MMGP loads in a fresh interpreter before the broader worker import graph.
    # Preload it at the earliest clean-child point and reuse the same modules
    # later instead of importing MMGP after an explicit torch import.
    if os.environ.get("ND_LTX2B_RUNTIME_READY") == "1":
        print("ND_LTX2B_STAGE=mmgp_bootstrap_begin", flush=True)
        from mmgp import offload, profile_type
        print("ND_LTX2B_STAGE=mmgp_bootstrap_done", flush=True)

    width = align32(int(request.get("width") or 512))
    height = align32(int(request.get("height") or 288))
    if width * height > 1024 * 576:
        scale = math.sqrt((1024 * 576) / float(width * height))
        width = align32(max(256, int(width * scale)))
        height = align32(max(256, int(height * scale)))
    frames = frame_count(float(request.get("duration_seconds") or 2.0))
    seed = int(request.get("seed") or 42)
    quality_mode = str(request.get("quality_mode") or "direct").strip().lower()
    if quality_mode not in {"direct", "multiscale"}:
        raise ValueError("quality_mode must be direct or multiscale")
    prompt = str(request.get("prompt") or "").strip() or "Smooth coherent motion from first keyframe to final keyframe, continuous camera, physically plausible movement, no cuts."
    negative = str(request.get("negative_prompt") or DEFAULT_NEGATIVE)

    TMP.mkdir(parents=True, exist_ok=True)
    start_path = TMP / "start.png"
    end_path = TMP / "end.png"
    mid_path = TMP / "mid.png"
    has_mid = bool(request.get("mid_image_url") or request.get("mid_image_base64"))
    mid_frame_number = int(request.get("mid_frame_number") if request.get("mid_frame_number") is not None else frames // 2)
    if has_mid and not (0 < mid_frame_number < frames - 1):
        raise ValueError("mid_frame_number must be between first and last frame")

    model, te, cfg = prepare_runtime()

    print("ND_LTX2B_STAGE=materialize_start_begin", flush=True)
    materialize_image(request, "start", start_path)
    print(f"ND_LTX2B_STAGE=materialize_start_done bytes={start_path.stat().st_size}", flush=True)
    print("ND_LTX2B_STAGE=materialize_end_begin", flush=True)
    materialize_image(request, "end", end_path)
    print(f"ND_LTX2B_STAGE=materialize_end_done bytes={end_path.stat().st_size}", flush=True)
    if has_mid:
        print("ND_LTX2B_STAGE=materialize_mid_begin", flush=True)
        materialize_image(request, "mid", mid_path)
        print(f"ND_LTX2B_STAGE=materialize_mid_done frame={mid_frame_number} bytes={mid_path.stat().st_size}", flush=True)

    print("ND_LTX2B_STAGE=import_torch_begin", flush=True)
    import torch
    print("ND_LTX2B_STAGE=import_torch_done", flush=True)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for LTX 2B generation")

    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    import resource
    def import_stage(name: str) -> None:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(f"ND_LTX2B_IMPORT_STAGE={name} maxrss_kb={rss}", flush=True)

    print("ND_LTX2B_STAGE=direct_import_begin", flush=True)
    import_stage("mmgp_preloaded")
    from shared.utils import files_locator as fl
    import_stage("files_locator_done")
    fl.set_checkpoints_paths([str(CK)])
    import_stage("checkpoint_paths_done")
    from models.ltx_video.models.autoencoders.causal_video_autoencoder import CausalVideoAutoencoder
    import_stage("causal_video_autoencoder_done")
    from models.ltx_video.models.transformers.symmetric_patchifier import SymmetricPatchifier
    import_stage("symmetric_patchifier_done")
    from models.ltx_video.models.transformers.transformer3d import Transformer3DModel
    import_stage("transformer3d_done")
    from models.ltx_video.pipelines.pipeline_ltx_video import ConditioningItem, LTXVideoPipeline, LTXMultiScalePipeline
    from models.ltx_video.models.autoencoders.latent_upsampler import LatentUpsampler
    import_stage("pipeline_ltx_video_done")
    from models.ltx_video.schedulers.rf import RectifiedFlowScheduler
    import_stage("rf_scheduler_done")
    from models.ltx_video.utils.skip_layer_strategy import SkipLayerStrategy
    import_stage("skip_layer_strategy_done")
    from transformers import T5Tokenizer
    import_stage("t5_tokenizer_done")
    from shared.attention import attention_config_shared_state
    import_stage("shared_attention_done")
    print("ND_LTX2B_STAGE=direct_import_done", flush=True)

    print("ND_LTX2B_STAGE=direct_assemble", flush=True)
    vae = offload.fast_load_transformers_model(
        fl.locate_file("ltxv_0.9.7_VAE.safetensors"),
        modelClass=CausalVideoAutoencoder,
        writable_tensors=False,
    ).to(torch.bfloat16)
    vae._model_dtype = torch.bfloat16

    # High-resolution decode on Kaggle T4 must tile the VAE. The diffusion
    # transformer itself can complete 1024x576; untiled VAE decode exceeds
    # 14.56 GiB VRAM. Wan2GP's own automatic policy uses 512px HW tiles and
    # 4-frame Z tiles for GPUs in this memory class.
    if width * height > 768 * 448:
        vae.enable_z_tiling(4)
        vae.enable_hw_tiling()
        vae.set_tiling_params(sample_size=512, overlap_factor=0.25)
        print("ND_LTX2B_VAE_TILING=z4_hw512", flush=True)

    transformer = offload.fast_load_transformers_model(
        str(model),
        modelClass=Transformer3DModel,
        writable_tensors=False,
        forcedConfigPath=os.environ["ND_LTX_TRANSFORMER_CONFIG_PATH"],
        preprocess_sd={
            **{"proj_in": "patchify_proj", "time_embed": "adaln_single"},
            **{
                f"transformer_blocks.{i}.{a}.{src}": f"transformer_blocks.{i}.{a}.{dst}"
                for i in range(28)
                for a in ["attn1", "attn2"]
                for src, dst in [("norm_q", "q_norm"), ("norm_k", "k_norm")]
            },
        },
    )
    transformer._model_dtype = torch.bfloat16

    text_encoder = offload.fast_load_transformers_model(str(te), writable_tensors=False)
    tokenizer = T5Tokenizer.from_pretrained(str(T5))
    scheduler = RectifiedFlowScheduler.from_pretrained(fl.locate_file("ltxv_scheduler.json"))
    patchifier = SymmetricPatchifier(patch_size=1)

    base_pipeline = LTXVideoPipeline(
        tokenizer=tokenizer,
        text_encoder=text_encoder,
        vae=vae,
        transformer=transformer,
        scheduler=scheduler,
        patchifier=patchifier,
        prompt_enhancer_image_caption_model=None,
        prompt_enhancer_image_caption_processor=None,
        prompt_enhancer_llm_model=None,
        prompt_enhancer_llm_tokenizer=None,
        allowed_inference_steps=None,
    )

    latent_upsampler = None
    generation_pipeline = base_pipeline
    if quality_mode == "multiscale":
        print("ND_LTX2B_STAGE=multiscale_assemble", flush=True)
        latent_upsampler = LatentUpsampler.from_pretrained(
            fl.locate_file("ltxv_0.9.7_spatial_upscaler.safetensors")
        ).to("cpu").eval()
        latent_upsampler.to(torch.bfloat16)
        latent_upsampler._model_dtype = torch.bfloat16
        generation_pipeline = LTXMultiScalePipeline(
            base_pipeline, latent_upsampler=latent_upsampler
        )
        print("ND_LTX2B_MULTISCALE=downscale_0.6666666_upscaler_0.9.7", flush=True)

    pipe = {
        "transformer": transformer,
        "vae": vae,
        "text_encoder": text_encoder,
    }
    if latent_upsampler is not None:
        pipe["latent_upsampler"] = latent_upsampler
    print("ND_LTX2B_STAGE=profile", flush=True)
    offload_obj = offload.profile(
        pipe,
        profile_no=profile_type.VerylowRAM_LowVRAM,
        quantizeTransformer=False,
        pinnedMemory=False,
        budgets={"transformer": 100, "text_encoder": 100, "*": 1000},
    )
    print("ND_LTX2B_STAGE=direct_assemble_done", flush=True)

    from PIL import Image
    start_img = Image.open(start_path).convert("RGB")
    end_img = Image.open(end_path).convert("RGB")
    start_t = pil_to_tensor(start_img, width, height)
    end_t = pil_to_tensor(end_img, width, height)

    start_media = start_t.unsqueeze(0).unsqueeze(2)
    end_media = end_t.unsqueeze(0).unsqueeze(2)
    conditioning_items = [ConditioningItem(start_media, 0, 1.0, False)]
    if has_mid:
        mid_img = Image.open(mid_path).convert("RGB")
        mid_t = pil_to_tensor(mid_img, width, height)
        mid_media = mid_t.unsqueeze(0).unsqueeze(2)
        conditioning_items.append(ConditioningItem(mid_media, mid_frame_number, 1.0, False))
        print(f"ND_LTX2B_CONDITIONING=three_anchor_0_{mid_frame_number}_{frames-1}", flush=True)
    conditioning_items.append(ConditioningItem(end_media, frames - 1, 1.0, False))

    import yaml
    pipeline_config = yaml.safe_load(Path(cfg).read_text(encoding="utf-8"))
    stg_mode = str(pipeline_config.get("stg_mode", "attention_values")).lower()
    skip_layer_strategy = {
        "stg_av": SkipLayerStrategy.AttentionValues,
        "attention_values": SkipLayerStrategy.AttentionValues,
        "stg_as": SkipLayerStrategy.AttentionSkip,
        "attention_skip": SkipLayerStrategy.AttentionSkip,
        "stg_r": SkipLayerStrategy.Residual,
        "residual": SkipLayerStrategy.Residual,
        "stg_t": SkipLayerStrategy.TransformerBlock,
        "transformer_block": SkipLayerStrategy.TransformerBlock,
    }[stg_mode]

    class HeadlessLTXState:
        _interrupt = False

    ltxv_state = HeadlessLTXState()

    print("ND_LTX2B_STAGE=generate", flush=True)
    started = time.time()
    import threading
    heartbeat_stop = threading.Event()
    def _generation_heartbeat():
        while not heartbeat_stop.wait(20.0):
            print(
                "ND_LTX2B_GENERATE_HEARTBEAT elapsed_s="
                + str(round(time.time() - started, 1)),
                flush=True,
            )
    threading.Thread(target=_generation_heartbeat, daemon=True).start()
    with attention_config_shared_state("sdpa"):
        with torch.inference_mode():
            (
                prompt_embeds,
                prompt_attention_mask,
                negative_prompt_embeds,
                negative_prompt_attention_mask,
            ) = base_pipeline.encode_prompt(
                prompt,
                True,
                negative_prompt=negative,
                device="cuda",
                text_encoder_max_tokens=256,
            )
            if quality_mode == "direct":
                images = base_pipeline(
                    height=height,
                    width=width,
                    num_frames=frames,
                    frame_rate=FPS,
                    prompt=None,
                    negative_prompt=None,
                    num_inference_steps=int(pipeline_config.get("num_inference_steps", 8)),
                    guidance_scale=float(pipeline_config.get("guidance_scale", 1.0)),
                    stg_scale=float(pipeline_config.get("stg_scale", 0.0)),
                    rescaling_scale=float(pipeline_config.get("rescaling_scale", 1.0)),
                    generator=torch.Generator(device="cuda").manual_seed(seed),
                    prompt_embeds=prompt_embeds,
                    prompt_attention_mask=prompt_attention_mask,
                    negative_prompt_embeds=negative_prompt_embeds,
                    negative_prompt_attention_mask=negative_prompt_attention_mask,
                    output_type="pt",
                    conditioning_items=conditioning_items,
                    decode_timestep=float(pipeline_config.get("decode_timestep", 0.05)),
                    decode_noise_scale=float(pipeline_config.get("decode_noise_scale", 0.025)),
                    stochastic_sampling=bool(pipeline_config.get("stochastic_sampling", True)),
                    image_cond_noise_scale=0.025,
                    skip_layer_strategy=skip_layer_strategy,
                    is_video=True,
                    vae_per_channel_normalize=True,
                    strength=1.0,
                    device="cuda",
                    ltxv_model=ltxv_state,
                )
                samples = images.sub(0.5).mul(2).squeeze(0)
            else:
                # Native LTX multi-scale path. Parameters mirror the official
                # 0.9.7/0.9.8 distilled multi-scale schedule while retaining
                # the qualified 2B 0.9.6 transformer and 0.9.7 spatial upscaler.
                multiscale_first_pass = {
                    "timesteps": [1.0000, 0.9937, 0.9875, 0.9812, 0.9750, 0.9094, 0.7250],
                    "guidance_scale": 1.0,
                    "stg_scale": 0.0,
                    "rescaling_scale": 1.0,
                    "skip_block_list": [42],
                }
                multiscale_second_pass = {
                    "timesteps": [0.9094, 0.7250, 0.4219],
                    "guidance_scale": 1.0,
                    "stg_scale": 0.0,
                    "rescaling_scale": 1.0,
                    "skip_block_list": [42],
                }
                images = generation_pipeline(
                    downscale_factor=0.6666666,
                    first_pass=multiscale_first_pass,
                    second_pass=multiscale_second_pass,
                    height=height,
                    width=width,
                    num_frames=frames,
                    frame_rate=FPS,
                    prompt=prompt,
                    negative_prompt=negative,
                    num_inference_steps1=8,
                    num_inference_steps2=3,
                    guidance_scale=1.0,
                    stg_scale=0.0,
                    rescaling_scale=1.0,
                    generator=torch.Generator(device="cuda").manual_seed(seed),
                    output_type="pt",
                    conditioning_items=conditioning_items,
                    decode_timestep=float(pipeline_config.get("decode_timestep", 0.05)),
                    decode_noise_scale=float(pipeline_config.get("decode_noise_scale", 0.025)),
                    stochastic_sampling=False,
                    image_cond_noise_scale=0.025,
                    skip_layer_strategy=skip_layer_strategy,
                    is_video=True,
                    vae_per_channel_normalize=True,
                    strength=1.0,
                    mixed_precision=False,
                    VAE_tile_size=(4, 512),
                    device="cuda",
                    ltxv_model=ltxv_state,
                )
                samples = images.sub(0.5).mul(2).squeeze(0)
    heartbeat_stop.set()
    generation_seconds = time.time() - started
    if samples is None:
        raise RuntimeError("LTX 2B returned no samples")

    import imageio.v2 as imageio
    import numpy as np
    arr = samples.detach().float().cpu().permute(1, 2, 3, 0).numpy()
    arr = ((arr + 1.0) / 2.0).clip(0, 1)
    arr = (arr * 255).astype(np.uint8)
    out_frames = [Image.fromarray(arr[i]) for i in range(arr.shape[0])]
    result_mp4 = WORK / "result.mp4"
    imageio.mimsave(str(result_mp4), [np.asarray(f) for f in out_frames], fps=FPS, codec="libx264", quality=9)

    endpoint = {
        "first_to_start_mae": mae(out_frames[0], start_img, (width, height)),
        "first_to_end_mae": mae(out_frames[0], end_img, (width, height)),
        "last_to_end_mae": mae(out_frames[-1], end_img, (width, height)),
        "last_to_start_mae": mae(out_frames[-1], start_img, (width, height)),
    }
    endpoint["endpoint_order_pass"] = (
        endpoint["first_to_start_mae"] < endpoint["first_to_end_mae"]
        and endpoint["last_to_end_mae"] < endpoint["last_to_start_mae"]
    )
    receipt = {
        "ok": True,
        "route": "kaggle_ltx2b_direct_f2l",
        "model": f"{MODEL_REPO}:{MODEL_REL}",
        "model_precision": "bf16",
        "wangp_commit": WANGP_COMMIT,
        "profile": "VerylowRAM_LowVRAM_DIRECT",
        "quality_mode": quality_mode,
        "conditioning_frames": [0, mid_frame_number, frames - 1] if has_mid else [0, frames - 1],
        "multiscale_downscale_factor": 0.6666666 if quality_mode == "multiscale" else None,
        "spatial_upscaler": "ltxv_0.9.7_spatial_upscaler.safetensors" if quality_mode == "multiscale" else None,
        "width": width,
        "height": height,
        "frames": len(out_frames),
        "fps": FPS,
        "duration_seconds": len(out_frames) / FPS,
        "generation_seconds": round(generation_seconds, 3),
        "size_bytes": result_mp4.stat().st_size,
        "sha256": hashlib.sha256(result_mp4.read_bytes()).hexdigest(),
        "seed": seed,
        "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        **endpoint,
    }
    (WORK / "result.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("ND_LTX2B_F2L_JSON=" + json.dumps(receipt, separators=(",", ":"), sort_keys=True), flush=True)

    try:
        offload_obj.release()
    except Exception:
        pass


if __name__ == "__main__":
    main()
