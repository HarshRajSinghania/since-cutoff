<!-- since-cutoff:start -->
<!-- since-cutoff:meta {"v":2,"tool":"0.4.1","model":"claude-opus-5-5","cutoff":"2026-06-30","versions_from":"pyproject.toml","deps":"sha256:f72830096d3f","body":"sha256:632927b2b2f7","scope":"imported"} -->
## Library changes after the model's training cutoff

Changed after the training cutoff of `claude-opus-5-5` (2026-06-30) in the packages this project imports, at the versions in `pyproject.toml`, according to [since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) 0.4.1. Tags: [diff] a static comparison of the two releases' public APIs; [library] the replacement is named in the library's own deprecation text and exists in the pinned version; [type-checked] an example that basedpyright accepts for the pinned version. No library code was run. Where these lines conflict with what you remember, follow these lines.

**openai 3.19.2** (2.44.0 at the cutoff)
- `ResponseFunctionCallArgumentsDoneEvent.name` was removed; do not use it. since-cutoff found no replacement in openai's deprecation text. [diff]
- `Videos.create` is deprecated; avoid it in new code. openai 3.19.2 says: "The Sora API is scheduled to permanently shut down on September 24, 2026." [diff]
- `Videos.create_and_poll` is deprecated; avoid it in new code. openai 3.19.2 says: "The Sora API is scheduled to permanently shut down on September 24, 2026." [diff]
- `openai.types.responses.ResponsesClientEvent` changed from class to attribute; check its new signature before use. [diff]
- `openai.types.responses.ResponsesClientEventParam` changed from class to attribute; check its new signature before use. [diff]
<!-- since-cutoff:end -->
