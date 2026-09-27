#!/usr/bin/env python3
"""ND Kaggle LTX 2B first/last worker via Wan2GP + MMGP.

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
FPS = 30
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
    k = max(2, round((raw - 1) / 8))
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
        run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")], 1200)
        env = dict(os.environ)
        env["ND_LTX2B_RUNTIME_READY"] = "1"
        worker_path = WORK / "kaggle_ltx2b_wan2gp_worker.py"
        os.execvpe(sys.executable, [sys.executable, str(worker_path), sys.argv[1]], env)

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
        ltxv_py.write_text(src.replace(needle, replacement, 1), encoding="utf-8")
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

    width = align32(int(request.get("width") or 512))
    height = align32(int(request.get("height") or 288))
    if width * height > 768 * 448:
        scale = math.sqrt((768 * 448) / float(width * height))
        width = align32(max(256, int(width * scale)))
        height = align32(max(256, int(height * scale)))
    frames = frame_count(float(request.get("duration_seconds") or 2.0))
    seed = int(request.get("seed") or 42)
    prompt = str(request.get("prompt") or "").strip() or "Smooth coherent motion from first keyframe to final keyframe, continuous camera, physically plausible movement, no cuts."
    negative = str(request.get("negative_prompt") or DEFAULT_NEGATIVE)

    TMP.mkdir(parents=True, exist_ok=True)
    start_path = TMP / "start.png"
    end_path = TMP / "end.png"

    model, te, cfg = prepare_runtime()

    materialize_image(request, "start", start_path)
    materialize_image(request, "end", end_path)

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for LTX 2B generation")

    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    from mmgp import offload, profile_type
    from shared.attention import attention_config_shared_state
    from shared.utils import files_locator as fl
    fl.set_checkpoints_paths([str(CK)])
    from models.ltx_video.ltxv import LTXV

    print("ND_LTX2B_STAGE=instantiate", flush=True)
    obj = LTXV(
        model_filepath=str(model),
        text_encoder_filepath=str(te),
        model_type="ltxv_2B",
        base_model_type="ltxv_2B",
        model_def={"LTXV_config": str(cfg), "text_encoder_folder": "T5_xxl_1.1"},
        dtype=torch.bfloat16,
        VAE_dtype=torch.bfloat16,
    )
    # Wan2GP's generation_progress decorator expects the UI cancellation flag.
    # Direct headless LTXV construction does not initialize it.
    obj._interrupt = False

    # LTX 2B 0.9.6 distilled is an official base-pipeline config.
    # Wan2GP's LTXV wrapper constructs a multi-scale wrapper unconditionally,
    # so select its inner base pipeline for this model instead of borrowing
    # 0.9.8-only multi-scale parameters.
    multi_pipeline = obj.pipeline
    base_pipeline = multi_pipeline.video_pipeline
    pipe = {
        "transformer": base_pipeline.transformer,
        "vae": base_pipeline.vae,
        "text_encoder": base_pipeline.text_encoder,
    }
    print("ND_LTX2B_STAGE=profile", flush=True)
    offload_obj = offload.profile(
        pipe,
        profile_no=profile_type.VerylowRAM_LowVRAM,
        quantizeTransformer=False,
        pinnedMemory=False,
        budgets={"transformer": 100, "text_encoder": 100, "*": 1000},
    )

    class BasePromptAdapter:
        def __init__(self, base):
            self._base = base

        def __getattr__(self, name):
            return getattr(self._base, name)

        def __call__(self, *args, **kwargs):
            prompt = kwargs.pop("prompt", None)
            negative_prompt = kwargs.pop("negative_prompt", None)
            if kwargs.get("prompt_embeds") is None:
                (
                    prompt_embeds,
                    prompt_attention_mask,
                    negative_prompt_embeds,
                    negative_prompt_attention_mask,
                ) = self._base.encode_prompt(
                    prompt,
                    True,
                    negative_prompt=negative_prompt,
                    device=kwargs.get("device") or "cuda",
                    text_encoder_max_tokens=256,
                )
                kwargs["prompt_embeds"] = prompt_embeds
                kwargs["prompt_attention_mask"] = prompt_attention_mask
                kwargs["negative_prompt_embeds"] = negative_prompt_embeds
                kwargs["negative_prompt_attention_mask"] = negative_prompt_attention_mask
            return self._base(*args, **kwargs)

    obj.pipeline = BasePromptAdapter(base_pipeline)

    from PIL import Image
    start_img = Image.open(start_path).convert("RGB")
    end_img = Image.open(end_path).convert("RGB")
    start_t = pil_to_tensor(start_img, width, height)
    end_t = pil_to_tensor(end_img, width, height)

    print("ND_LTX2B_STAGE=generate", flush=True)
    started = time.time()
    with attention_config_shared_state("sdpa"):
        with torch.inference_mode():
            samples = obj.generate(
                input_prompt=prompt,
                n_prompt=negative,
                image_start=start_t,
                image_end=end_t,
                sampling_steps=7,
                image_cond_noise_scale=0.025,
                seed=seed,
                height=height,
                width=width,
                frame_num=frames,
                frame_rate=FPS,
                fit_into_canvas=True,
                device="cuda",
                VAE_tile_size=256,
            )
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
    imageio.mimsave(str(result_mp4), [np.asarray(f) for f in out_frames], fps=FPS, codec="libx264", quality=7)

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
        "route": "kaggle_ltx2b_wan2gp_f2l",
        "model": f"{MODEL_REPO}:{MODEL_REL}",
        "model_precision": "bf16",
        "wangp_commit": WANGP_COMMIT,
        "profile": "VerylowRAM_LowVRAM",
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
