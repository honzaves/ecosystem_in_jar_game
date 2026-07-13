"""ComfyUI image-generation worker and workflow builders."""

import random, time

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from settings import COMFY
from simulation import World, CANVAS_W, CANVAS_H


def _comfy_get(path: str) -> dict:
    r = requests.get(f"{COMFY['url']}{path}", timeout=8)
    r.raise_for_status()
    return r.json()


def _node_choices(node_class: str, param: str) -> list:
    """Return the list of valid values for a ComfyUI node parameter."""
    try:
        info = _comfy_get(f"/object_info/{node_class}")
        return (info.get(node_class, {})
                    .get("input", {})
                    .get("required", {})
                    .get(param, [None])[0]) or []
    except Exception:
        return []


def _pick(choices: list, *keywords) -> str | None:
    """Return first choice whose name contains any keyword (case-insensitive)."""
    for kw in keywords:
        for c in choices:
            if kw.lower() in c.lower():
                return c
    return None


def _build_workflow_merged(prompt_text: str, seed: int, ckpt: str) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt_text, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": COMFY["width"], "height": COMFY["height"], "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": COMFY["steps"],
                         "cfg": COMFY["cfg"], "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "ecosystem_jar", "images": ["6", 0]}},
    }


def _build_workflow_split(prompt_text: str, seed: int,
                           unet: str, clip1: str, clip2: str, vae: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": clip1, "clip_name2": clip2, "type": "flux"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt_text, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"text": "", "clip": ["2", 0]}},
        "6": {"class_type": "EmptyLatentImage",
              "inputs": {"width": COMFY["width"], "height": COMFY["height"], "batch_size": 1}},
        "7": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["6", 0], "seed": seed, "steps": COMFY["steps"],
                         "cfg": COMFY["cfg"], "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "ecosystem_jar", "images": ["8", 0]}},
    }


class ImageGenWorker(QThread):
    done   = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, world: World, trigger: str):
        super().__init__()
        self.world   = world
        self.trigger = trigger

    def run(self):
        if not COMFY.get("enabled", True):
            return
        try:
            prompt = self._build_prompt()
            seed   = random.randint(0, 2**32 - 1)
            wf, desc = self._build_workflow(prompt, seed)
            if wf is None:
                self.failed.emit(desc); return

            r = requests.post(f"{COMFY['url']}/prompt", json={"prompt": wf}, timeout=15)
            if r.status_code != 200:
                try:
                    detail = r.json()
                    err    = detail.get("error", {})
                    msg    = err.get("message", str(detail)) if isinstance(err, dict) else str(err)
                    node_errors = detail.get("node_errors", {})
                    if node_errors:
                        msg += " | " + "; ".join(
                            f"node {nid}: {info.get('errors',[{}])[0].get('message','?')}"
                            for nid, info in node_errors.items())
                except Exception:
                    msg = r.text[:300]
                self.failed.emit(f"ComfyUI HTTP {r.status_code}: {msg}"); return

            prompt_id = r.json()["prompt_id"]
            for _ in range(180):
                time.sleep(0.5)
                hist = requests.get(f"{COMFY['url']}/history/{prompt_id}", timeout=8)
                if hist.status_code == 200 and prompt_id in hist.json():
                    for node_out in hist.json()[prompt_id].get("outputs", {}).values():
                        for img_info in node_out.get("images", []):
                            img_r = requests.get(
                                f"{COMFY['url']}/view",
                                params={"filename": img_info["filename"],
                                        "subfolder": img_info.get("subfolder", ""),
                                        "type":      img_info.get("type", "output")},
                                timeout=15)
                            if img_r.status_code == 200:
                                self.done.emit(img_r.content); return
            self.failed.emit("ComfyUI: timed out waiting for image")
        except Exception as e:
            self.failed.emit(f"ComfyUI error: {e}")

    def _build_workflow(self, prompt: str, seed: int):
        unets = _node_choices("UNETLoader", "unet_name")
        unet  = _pick(unets, "schnell", "flux")
        if unet:
            clips = _node_choices("DualCLIPLoader", "clip_name1")
            clip1 = _pick(clips, "clip_l")
            clip2 = _pick(clips, "t5xxl", "t5")
            vaes  = _node_choices("VAELoader", "vae_name")
            vae   = _pick(vaes, "ae", "flux", "vae")
            if clip1 and clip2 and vae:
                return (_build_workflow_split(prompt, seed, unet, clip1, clip2, vae),
                        f"split: {unet} / {clip1} / {clip2} / {vae}")
            if not clip1 or not clip2:
                return None, f"Split setup: found UNET '{unet}' but missing CLIP files (got {clips})"
            if not vae:
                return None, f"Split setup: found UNET '{unet}' but no VAE (got {vaes})"

        ckpts   = _node_choices("CheckpointLoaderSimple", "ckpt_name")
        EXCLUDE = ("ae.safetensors", "clip_l", "t5", "vae")
        real    = [c for c in ckpts if not any(e in c.lower() for e in EXCLUDE)]
        ckpt    = _pick(real, "schnell", "flux") or _pick(ckpts, "schnell", "flux")
        if ckpt:
            return _build_workflow_merged(prompt, seed, ckpt), f"merged: {ckpt}"

        return None, f"No Flux model found. UNETs={unets}, Checkpoints={ckpts}"

    def _build_prompt(self) -> str:
        w      = self.world
        pop    = w.population_by_species()
        season = w.season.split()[-1].lower()

        species_info = {c.species: {"emoji": c.emoji, "diet": c.diet, "count": 0}
                        for c in w.creatures}
        for c in w.creatures:
            species_info[c.species]["count"] += 1

        descriptions = []
        for name, info in sorted(species_info.items(), key=lambda x: -x[1]["count"]):
            diet  = info["diet"]
            count = info["count"]
            size  = "many" if count > 15 else "a few" if count > 4 else "a handful of"
            if diet == "carnivore":
                descriptions.append(f"{size} {name.lower()} predators hunting")
            elif diet == "herbivore":
                descriptions.append(f"{size} {name.lower()} grazers foraging")
            else:
                descriptions.append(f"{size} {name.lower()} creatures")

        cast = ", ".join(descriptions) if descriptions else "alien creatures"

        if "meteor" in self.trigger:
            action = "fleeing a catastrophic meteor impact, fire and destruction"
        elif "drought" in self.trigger:
            action = "struggling across cracked dry earth, desperate for water"
        elif "flood" in self.trigger:
            action = "swimming through floodwaters, clinging to debris"
        elif "plague" in self.trigger:
            action = "weakened and dying from a mysterious plague"
        elif "cold" in self.trigger:
            action = "huddled together, freezing in a sudden cold snap"
        elif "bloom" in self.trigger:
            action = "feasting joyfully in a sudden explosion of abundant food"
        elif pop and len(pop) > 1:
            has_carn = any(c.diet == "carnivore" for c in w.creatures)
            has_herb = any(c.diet == "herbivore" for c in w.creatures)
            if has_carn and has_herb:
                action = f"in a tense chase through {season} undergrowth, predator pursuing prey"
            else:
                action = f"moving through a {season} landscape"
        else:
            action = f"wandering a {season} wilderness"

        plants = ("lush green vegetation" if w.plant_abundance > 65
                  else "sparse dry scrubland" if w.plant_abundance > 25
                  else "barren scorched earth with almost no plants")

        return (f"wildlife nature photography, {cast}, {action}, "
                f"{plants}, dramatic natural lighting, "
                f"sharp focus, cinematic, photorealistic, no text, no humans")