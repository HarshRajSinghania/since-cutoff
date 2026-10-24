"""Manual (AI-judged, Claude Opus 5.5) precision verdicts for the sample items the evidence pre-check did not settle.
Each verdict was made after reading the two releases' code (evidence.lookup output, plus grep where noted)."""
import json, re
from pathlib import Path

S = json.loads(Path(r"recall_eval\out\precision\sample.json").read_text(encoding="utf-8"))
M = {}


def put(rid, acc, brk, why):
    M[rid] = {"accurate": acc, "breaking": brk, "why": why}


# detector reports
for rid, s in S.items():
    if s["kind"] == "deprecated" and not s["tool"].endswith("cap5"):
        put(rid, True, False, "new release adds a deprecation decorator (typing_extensions.deprecated / deprecated) to this callable; still works")
put("041-huggingface-hub-0043", True, True, "HFCacheInfo is a dataclass; 2.0.0 adds a required field incomplete_files, so constructing it the old way fails")
put("041-mcp-0032", True, True, "mcp.server.fastmcp removed (fastmcp.py raises ModuleNotFoundError); Audio lives in mcp.server.mcpserver")
put("041-mcp-0033", True, True, "as above for Context")
put("041-mcp-0099", True, True, "old StreamableHTTPTransport.__init__ took headers/timeout/sse_read_timeout/auth (overloads); 2.2.0 takes url only")
put("041-mcp-0025", True, True, "instance attribute self.stdin_raw set in 1.28.1 FallbackProcess.__init__; absent in 2.2.0 (grep)")
put("041-mcp-0068", True, True, "1.28.1 ServerSession inherited __aexit__ from BaseSession; 2.2.0 ServerSession is a plain class without __aexit__ (grep)")
put("041-streamlit-0073", True, True, "proto stub field debug_last_backmsg_id dropped from ForwardMsg (pyi grep); public module streamlit.proto, internal protocol")
put("c2m0-streamlit-0068", True, True, "same field dropped from BackMsg stub (internal protocol)")
for t in ("041", "c2m0"):
    for n in ("0259", "0270", "0206", "0361", "0246"):
        put(f"{t}-mistralai-{n}", True, True, "name absent from 3.3.0 models/__init__ lazy table and from every module (grep)")
put("c2m0-anthropic-0068", True, True, "BetaAsyncStreamingToolRunner.__init__(compaction_control=) in 0.115.0 lib/tools/_beta_runner.py; gone in 1.8.0 (grep)")
put("c2m0-openai-0003", True, True, "ResponsesClientEventParam: TypedDict class -> TypeAlias Union; instantiation breaks")
put("c2m0-mcp-0061", True, True, "self.request_handlers attribute renamed to _request_handlers in 2.2.0 (grep)")
put("c2m0-polars-0199", True, True, "old signature allowed positional inference_length (with deprecate_nonkeyword_arguments warning); 2.0.0 keyword-only")
put("griffe-anthropic-00136", True, True, "TypedDict class -> TypeAlias Union; instantiation breaks")
for n in ("00008", "00012", "00015", "00013", "00009"):
    put(f"griffe-openai-{n}", True, True, "class -> TypeAlias (verified in both wheels); instantiation/isinstance breaks")
for n in ("00064", "00067", "00051", "00090", "00061", "00093"):
    put(f"griffe-huggingface-hub-{n}", True, True, "hf CLI command function: a new parameter `name` was inserted before it, shifting positions (public module path, CLI implementation)")
put("griffe-mcp-00273", True, True, "Server.__init__(version) became keyword-only")
put("griffe-polars-00146", True, True, "Selector inherits from Expr; Expr.flatten exists in 1.42.1 and not in 2.0.0")
put("griffe-streamlit-00064", True, True, "marshall_video: a parameter inserted before width (internal helper on a non-underscore path)")
put("griffe-streamlit-00093", True, False, "PopoverContainer.__exit__ parameters renamed exc_type->typ etc.; the interpreter calls __exit__ positionally, so nothing breaks")
for n in ("00259", "00270", "00206", "00546", "00361", "00246", "00586", "00375"):
    put(f"griffe-mistralai-{n}", True, True, "name/module absent from 3.3.0 (lazy table and files checked by grep)")
# notes lines
for rid, s in S.items():
    if not s["tool"].endswith("cap5"):
        continue
    t = s["text"]
    if "is deprecated" in t or "are deprecated" in t:
        put(rid, True, False, "deprecation verified (decorator in the pinned release); still works")
    else:
        put(rid, True, True, "stated change verified in both wheels (removal/move/default/dependency metadata)")
for rid in ("041cap5-mistralai-04", "c2m0cap5-mistralai-04"):
    M[rid]["why"] += "; NOTE: the 'is now RegisterDeploymentRequestVespaField' replacement is a structural match of two one-field models, not documented; the removal itself is real"
M["041cap5-polars-00"]["why"] += "; NOTE: suggested replacement polars.functions.arctan2 returns radians (old deprecation text says arctan2 then .degrees())"
json.dump(M, open(Path(__file__).parent / "precision_manual.json", "w", encoding="utf-8"), indent=1)
print(len(M))

# ---- AexPy sample (verdicts after reading the evidence for each item) ----
def ax(rid, acc, brk, why):
    if rid in S:
        put(rid, acc, brk, why)


for rid, s in S.items():
    if s["tool"] != "aexpy" or rid in M:
        continue
    k, path = s["kind"], s["path"] or ""
    priv = any(c.startswith("_") and not c.startswith("__") for c in path.split("."))
    if k == "AddOptionalParameter":
        put(rid, True, False, "an optional keyword parameter was added (verified in the new signature); old calls still work")
    elif k == "ChangeParameterType" and "httpx2" in s["text"] and re.search(r"(?<![\w])httpx\.", s["text"]):
        put(rid, True, not priv, "annotation moved from httpx to httpx2 (the documented dependency switch)" + ("; private method" if priv else "; httpx objects are no longer the accepted type"))
    elif k == "RemoveExternalAlias":
        put(rid, True, False, "an incidental import of a third-party/stdlib name was dropped from the module; not API")
ax("aexpy-anthropic-01544", True, False, "AsyncStream's private metaclass _AsyncStreamMeta (isinstance shim) was removed; no public name breaks")
ax("aexpy-openai-01457", True, False, "private method; annotation httpx -> httpx2")
ax("aexpy-openai-01468", True, False, "private method; annotation httpx -> httpx2")
ax("aexpy-openai-01442", True, False, "private method; annotation httpx -> httpx2")
ax("aexpy-huggingface-hub-00763", True, False, "annotation of a module-level CLI app object changed type; nothing a caller does breaks")
ax("aexpy-huggingface-hub-00600", True, True, "hf CLI command function: a parameter inserted earlier shifts positions (as griffe)")
ax("aexpy-huggingface-hub-00628", True, True, "as above")
ax("aexpy-mcp-02597", False, False, "a parametrised pydantic generic (Request[..., Literal['roots/list']]) is an AexPy-internal entity, not an importable name")
ax("aexpy-mcp-02584", False, False, "same generic-specialisation artefact")
ax("aexpy-mcp-02849", True, False, "base class Notification[...] of TaskStatusNotification is now mcp_types' generic; class and fields unchanged")
ax("aexpy-mcp-02032", True, False, "same for GetTaskRequest")
ax("aexpy-mcp-03218", False, False, "return types named mcp.types.ElicitResult and mcp_types._types.ElicitResult are the same object (mcp.types mirrors mcp_types)")
ax("aexpy-mcp-03530", False, False, "mcp.shared.session is gone in 2.2.0 (the whole module); a 'parameter type changed' report misstates it")
ax("aexpy-mcp-03232", True, False, "private function; annotation changed")
ax("aexpy-streamlit-00668", True, True, "DeltaGenerator lost the BokehMixin base: st.bokeh_chart is gone")
json.dump(M, open(Path(__file__).parent / "precision_manual.json", "w", encoding="utf-8"), indent=1)
print("with aexpy", len(M))
for rid in ("aexpy-mistralai-01261", "aexpy-mistralai-01272", "aexpy-mistralai-01208", "aexpy-mistralai-01248"):
    ax(rid, True, True, "name absent from the 3.3.0 models lazy table and from every module (grep)")
json.dump(M, open(Path(__file__).parent / "precision_manual.json", "w", encoding="utf-8"), indent=1)
