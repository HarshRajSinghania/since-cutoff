<!-- since-cutoff:start -->
<!-- since-cutoff:meta {"v":2,"tool":"0.4.1","model":"claude-sonnet-4-5","cutoff":"2025-07-31","versions_from":"pyproject.toml","deps":"sha256:b8a8eb3ad5e2","body":"sha256:f615c2aa9737","scope":"imported"} -->
## Library changes after the model's training cutoff

Changed after the training cutoff of `claude-sonnet-4-5` (2025-07-31) in the packages this project imports, at the versions in `pyproject.toml`, according to [since-cutoff](https://github.com/MohammadHijjawi97/since-cutoff) 0.4.1. Tags: [diff] a static comparison of the two releases' public APIs; [library] the replacement is named in the library's own deprecation text and exists in the pinned version; [type-checked] an example that basedpyright accepts for the pinned version; [move checked] the object at the new path keeps the old one's public names or parameters. No library code was run. Where these lines conflict with what you remember, follow these lines.

**mcp 2.2.0** (1.12.3 at the cutoff)
- `ClientSession.subscribe_resource` is deprecated; avoid it in new code. Use `Client.listen` instead. [diff + library]
- `ClientSession.unsubscribe_resource` is deprecated; avoid it in new code. Use `Client.listen` instead. [diff + library]
- `McpError` is now `MCPError`: `mcp.McpError` moved to `mcp.MCPError`; import it with `from mcp import MCPError`. [diff + move checked]
- `FastMCP` is now `MCPServer`: `mcp.server.FastMCP` moved to `mcp.server.MCPServer`; import it with `from mcp.server import MCPServer`. [diff + move checked]
- The package `mcp.server.fastmcp` moved to `mcp.server.mcpserver`; import from there. [diff + move checked]
<!-- since-cutoff:end -->
