"""Local, free GUI grounding with Holo1.5; no API keys needed (kb/29).

Complements llm_agent.decide() with on-device visual grounding and VQA.
"""

import json
import re
import tempfile
import time
from contextlib import contextmanager
from os import PathLike

from PIL import Image
from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config


# Lazy singleton load
_REPO = "mlx-community/holo1.5-7b-mlx"
_backend = None
_last_raw = ""


def _get_backend():
    global _backend
    if _backend is None:
        model, processor = load(_REPO)
        _backend = model, processor, load_config(_REPO)
    return _backend


# Model invocation
def _ask(image, question, max_tokens):
    global _last_raw
    model, processor, config = _get_backend()
    prompt = apply_chat_template(processor, config, question, num_images=1)
    result = generate(
        model,
        processor,
        prompt,
        image=[str(image) if isinstance(image, PathLike) else image],
        max_tokens=max_tokens,
        verbose=False,
    )
    _last_raw = result.text
    return _last_raw


@contextmanager
def _model_image(image):
    with Image.open(image) as source:
        source_size = source.size
        scale = min(1, 960 / max(source_size))
        model_size = tuple(round(dimension * scale) for dimension in source_size)
        with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
            source.resize(model_size, Image.Resampling.LANCZOS).save(temporary.name)
            yield temporary.name, source_size, model_size


# Coordinate parsing
def _json_point(value):
    if isinstance(value, dict):
        lowered = {str(key).lower(): item for key, item in value.items()}
        if "x" in lowered and "y" in lowered:
            return float(lowered["x"]), float(lowered["y"])
        for item in value.values():
            point = _json_point(item)
            if point:
                return point
    if isinstance(value, list):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            return float(value[0]), float(value[1])
        for item in value:
            point = _json_point(item)
            if point:
                return point
    return None


def _extract_point(text):
    number = r"[-+]?\d+(?:\.\d+)?"
    patterns = (
        rf"<point[^>]*>\s*({number})\s*[, ]\s*({number})\s*</point>",
        rf"[\"']?x[\"']?\s*[:=]\s*[\"']?({number})[\"']?\s*[,; ]+\s*[\"']?y[\"']?\s*[:=]\s*[\"']?({number})",
        rf"[\[(]\s*({number})\s*,\s*({number})\s*[\])]",
    )
    for candidate in (text.strip(), *re.findall(r"[\[{].*?[\]}]", text, re.DOTALL)):
        try:
            point = _json_point(json.loads(candidate))
        except (json.JSONDecodeError, TypeError, ValueError):
            point = None
        if point:
            return point
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(2))
    match = re.fullmatch(rf"\s*({number})\s+({number})\s*", text)
    return (float(match.group(1)), float(match.group(2))) if match else None


def _device_point(point, source_size, model_size, raw):
    x, y = point
    width, height = model_size
    if 0 <= x <= 1 and 0 <= y <= 1:
        x, y = x * width, y * height
    elif any(marker in raw.lower() for marker in ("normalized", "0-1000", "0 to 1000")) and 0 <= x <= 1000 and 0 <= y <= 1000:
        x, y = x * width / 1000, y * height / 1000
    return round(x * source_size[0] / width), round(y * source_size[1] / height)


# Public API
def ground(image, instruction, max_tokens=256):
    with _model_image(image) as (model_image, source_size, model_size):
        raw = _ask(
            model_image,
            f"Locate {instruction}. Return only the center click point as (x, y) in "
            f"pixel coordinates for this {model_size[0]}x{model_size[1]} image. Do not use normalized coordinates.",
            max_tokens,
        )
    point = _extract_point(raw)
    return _device_point(point, source_size, model_size, raw) if point else None


def describe(image, question, max_tokens=256):
    with _model_image(image) as (model_image, _, _):
        return _ask(model_image, question, max_tokens)


# End-to-end self-test
if __name__ == "__main__":
    test_image = "/private/tmp/claude-501/-Users-sward-work-scratch/c2e71639-9f51-4ec5-b5ef-685684771afc/scratchpad/holo_test.png"
    load_started = time.perf_counter()
    ok = True
    try:
        _get_backend()
        print(f"MODEL LOAD SECONDS: {time.perf_counter() - load_started:.2f}", flush=True)
        started = time.perf_counter()
        answer = describe(test_image, "What screen or dialog is shown? Answer in one short sentence.")
        print(f"DESCRIBE RAW: {answer}", flush=True)
        print("DESCRIBE PARSED: None", flush=True)
        print(f"DESCRIBE SECONDS: {time.perf_counter() - started:.2f}", flush=True)
        describe_ok = bool(answer.strip()) and any(
            word in answer.lower() for word in ("disconnect", "login", "quit", "restart")
        )
        points = []
        for label, instruction in (("QUIT", "the Quit button"), ("RESTART", "the Restart button")):
            started = time.perf_counter()
            point = ground(test_image, instruction)
            points.append(point)
            print(f"{label} RAW: {_last_raw}", flush=True)
            print(f"{label} PARSED: {point}", flush=True)
            print(f"{label} SECONDS: {time.perf_counter() - started:.2f}", flush=True)
        ok = describe_ok and any(
            point is not None
            and 0 <= point[0] <= 1080
            and 0 <= point[1] <= 1920
            and 250 <= point[0] <= 850
            and 650 <= point[1] <= 1250
            for point in points
        )
    except Exception as error:
        print(f"SELF-TEST ERROR: {type(error).__name__}: {error}", flush=True)
        ok = False
    print(f"SELF-TEST: {'PASS' if ok else 'FAIL'}", flush=True)
    raise SystemExit(0 if ok else 1)
