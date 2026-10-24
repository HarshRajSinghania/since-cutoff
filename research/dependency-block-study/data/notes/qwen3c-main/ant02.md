<!-- since-cutoff:start -->
<!-- since-cutoff:meta {"v":2,"tool":"0.4.1","model":"qwen3-coder-30b-a3b-instruct","cutoff":"2025-04-30","versions_from":"pyproject.toml","deps":"sha256:6f079f2464ef","body":"sha256:8658a9a49e31","scope":"imported"} -->
## Library changes after the model's training cutoff

Changed after the training cutoff of `qwen3-coder-30b-a3b-instruct` (2025-04-30) in the packages this project imports, at the versions in `pyproject.toml`, according to [since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) 0.4.1. Tags: [diff] a static comparison of the two releases' public APIs; [library] the replacement is named in the library's own deprecation text and exists in the pinned version; [type-checked] an example that basedpyright accepts for the pinned version. No library code was run. Where these lines conflict with what you remember, follow these lines.

**anthropic 1.8.0** (0.50.0 at the cutoff)
- `Messages.create()` no longer accepts `temperature`, `top_k` or `top_p` as keyword arguments. If the API still needs them, pass them through its `extra_body` or `extra_query` argument. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.AI_PROMPT` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.HUMAN_PROMPT` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.ProxiesTypes` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.Transport` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
<!-- since-cutoff:end -->
