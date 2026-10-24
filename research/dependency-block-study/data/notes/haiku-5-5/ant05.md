<!-- since-cutoff:start -->
<!-- since-cutoff:meta {"v":2,"tool":"0.4.1","model":"claude-haiku-5-5","cutoff":"2026-06-30","versions_from":"pyproject.toml","deps":"sha256:6f079f2464ef","body":"sha256:a9f17141d114","scope":"imported"} -->
## Library changes after the model's training cutoff

Changed after the training cutoff of `claude-haiku-5-5` (2026-06-30) in the packages this project imports, at the versions in `pyproject.toml`, according to [since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) 0.4.1. Tags: [diff] a static comparison of the two releases' public APIs; [library] the replacement is named in the library's own deprecation text and exists in the pinned version; [type-checked] an example that basedpyright accepts for the pinned version; [move checked] the object at the new path keeps the old one's public names or parameters. No library code was run. Where these lines conflict with what you remember, follow these lines.

**anthropic 1.8.0** (0.115.0 at the cutoff)
- `anthropic.AI_PROMPT` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.HUMAN_PROMPT` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.ProxiesTypes` was removed; do not use it. since-cutoff found no replacement in anthropic's deprecation text. [diff]
- `anthropic.types.beta.deleted_file` moved to `anthropic.types.deleted_file`: import it with `from anthropic.types import deleted_file`. [diff + move checked]
- `anthropic.types.beta.file_metadata` moved to `anthropic.types.file_metadata`: import it with `from anthropic.types import file_metadata`. [diff + move checked]
<!-- since-cutoff:end -->
