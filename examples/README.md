# Example inference configs

## server_8card.json

The config actually used in production: 8× Ascend 910B as **one** server, tensor-parallel 4 ×
sequence-parallel 2, BF16, 8-step turbo distillation LoRA, native 768×1344 vertical at 24 fps.
About 130 s per 8-second segment.

**Replace `/REPLACE/` with your model root before using it** — two paths (`adaln_cache_dir` and
the LoRA `path`) point at local weights.

Notes on the values that are not obvious:

- `alpha: 8` on the LoRA — read it from the adapter's own metadata. The widely-copied example
  config for a *different* 4-step adapter uses 128, which produces corrupted output with this one.
- `tensor_p_size` must divide the attention head count (MiniMax-H3 has 56, so 4 and 8 both work).
  Combine with `seq_p_size` to use the remaining cards.
- `use_adaln_cache` needs the cache generated once before first use; the LightX2V start script does
  this on a single card, so first launch is slower.
- `enable_cfg: false` — distilled step schedules ignore classifier-free guidance, and with CFG at 1
  a negative prompt does nothing at all. Put constraints in the positive prompt instead.
- `num_frames` here is only a default; the runner sets it per segment. MiniMax-H3 requires
  `num_frames % 17 == 5` (158, 175, 192 … 362).
