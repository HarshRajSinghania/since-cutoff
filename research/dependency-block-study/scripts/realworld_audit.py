"""Hand audit of the changed-API matches in the real-world exposure scan (primary set, current cutoff 2026-06-30).

The scan reported 53 distinct changed APIs used in 10 of the 47 repositories (sum of `used.apis`; 128 changes in
`used.changes`). Each match was checked by reading the matched files in the shallow clone and the two releases'
sources in the tool's download cache (2026-10-22). Verdicts were assigned by hand and are recorded below.

verdict
  TP            the project's code references this API (call, constructor, import or attribute), and the reported
                change exists in the pinned release
  FP-resolution the project's code does not reference this API (the match resolved a different object)
  FP-diff       the code references the API, but the reported change is not a real break at the pinned version
                (for example, parameters moved into **kwargs and still accepted)
affected (only meaningful for TP)
  yes           the code uses the old form, so it breaks or warns at the pinned version
  handled       the code already branches on the library version
  no            the code uses the API, but not the part that changed (or already uses the new form)

usage: python -I realworld_audit.py  -> ../analysis/realworld_audit.csv, ../analysis/realworld_audit_summary.json
"""
import csv
import json
from math import sqrt
import os
from pathlib import Path

# Folder with repos.json and scans/ (set REALWORLD_DIR; default ./realworld).
RW = Path(os.environ.get("REALWORLD_DIR", "realworld"))
ANALYSIS = Path(__file__).resolve().parent.parent / "analysis"

# (verdict, affected, reason) in the order of the scan's used_apis lists, repositories in star order
V = [
    ("TP", "handled", "test server builds websockets.sync ServerConnection; code appends the now-required server argument when websockets >= 17"),
    ("TP", "no", "resolved to the asyncio Connection.send; the code calls the sync twin, which has the identical keyword-only change; message passed positionally"),
    ("TP", "yes", "tests/integration/_support/mcp.py passes httpx.AsyncClient as http_client to mcp's streamable_http_client; mcp 2.3 takes httpx2 objects"),
    ("TP", "yes", "imports FastMCP from mcp.server.fastmcp; in mcp 2.x that module raises ModuleNotFoundError (renamed MCPServer)"),
    ("TP", "yes", "same import of the removed mcp.server.fastmcp module"),
    ("TP", "yes", "calls ClientSession.subscribe_resource, deprecated in mcp 2.3 (warning at runtime)"),
    ("TP", "yes", "calls ClientSession.unsubscribe_resource, deprecated in mcp 2.3 (warning at runtime)"),
    ("TP", "no", "constructs lowlevel Server; the deprecated overload's handlers (logging, roots, progress) are not passed"),
    ("TP", "no", "calls list_prompts; already uses params=PaginatedRequestParams instead of the removed cursor"),
    ("TP", "no", "calls list_resource_templates without the removed cursor argument"),
    ("TP", "no", "calls list_resources without the removed cursor argument"),
    ("TP", "no", "calls list_tools; pagination already via params=PaginatedRequestParams"),
    ("TP", "no", "constructs OAuthClientProvider without the removed timeout argument"),
    ("TP", "no", "constructs ClientSession with streams only; experimental_task_handlers not passed"),
    ("TP", "no", "constructs ServerSession with the new (channel, connection, request_meta) signature"),
    ("TP", "no", "constructs ClientSession(read_stream, write_stream, read_timeout_seconds=...); removed argument not passed"),
    ("TP", "no", "calls islo.types.AutoResumePolicy(value), valid for the 0.3.20 StrEnum (the 0.3.8 alias was not callable); tool's old-form label is wrong"),
    ("FP-diff", "", "pydantic-ai 2.56 RequestUsage takes the fields through **kwargs (init=False dataclass); the keywords are still accepted"),
    ("FP-diff", "", "pydantic-ai 2.56 RunUsage takes the fields through **kwargs; the keywords are still accepted"),
    ("FP-diff", "", "RunContext still accepts capability_loaded through a patched __init__ (deprecated, not removed)"),
    ("TP", "no", "example DAG calls beta.messages.tool_runner without temperature/top_k/top_p/compaction_control"),
    ("TP", "no", "calls pgvector.psycopg.register_vector(conn) positionally; the parameter became positional-only"),
    ("TP", "no", "calls pgvector.psycopg2.register_vector(conn) positionally; no keyword arguments"),
    ("FP-diff", "", "django-stubs 6.1.1 moved Model.objects to a metaclass __getattr__; still typed, and stubs have no runtime effect"),
    ("TP", "no", "the repository publishes openviking-sdk; calls use the 0.1.15 options= form (telemetry/created_at not passed)"),
    ("TP", "no", "add_resource calls pass no removed keyword; options moved to an options dict"),
    ("TP", "no", "add_skill called without telemetry"),
    ("TP", "no", "batch_add_messages called without telemetry"),
    ("TP", "no", "commit_session called without telemetry"),
    ("TP", "no", "create_session called without memory_policy/telemetry"),
    ("TP", "no", "find called with options= (new form)"),
    ("TP", "no", "search called with options= (new form)"),
    ("TP", "no", "set_tags called without telemetry"),
    ("TP", "no", "write called without telemetry; a test binds the new positional signature"),
    ("TP", "no", "Session.add_message called without created_at"),
    ("TP", "no", "SyncHTTPClient.add_message called without created_at/telemetry"),
    ("TP", "no", "SyncHTTPClient.add_resource calls pass no removed keyword"),
    ("TP", "no", "SyncHTTPClient.add_skill called without telemetry"),
    ("TP", "no", "SyncHTTPClient.batch_add_messages called without telemetry"),
    ("TP", "no", "SyncHTTPClient.commit_session called without telemetry"),
    ("TP", "no", "SyncHTTPClient.create_session called without memory_policy/telemetry"),
    ("TP", "no", "SyncHTTPClient.find called with options= (new form)"),
    ("TP", "no", "SyncHTTPClient.search called with options=; a score_threshold= hit is the example's own Recipe.search"),
    ("TP", "no", "SyncHTTPClient.set_tags called without telemetry"),
    ("TP", "no", "SyncHTTPClient.write called without telemetry"),
    ("TP", "no", "SyncSession.add_message referenced in a signature test that binds the new form"),
    ("TP", "no", "Client.start_workflow called without callbacks/links/request_id (documented as non-public options)"),
    ("TP", "no", "constructs BuildBackendException(exception, description=...); exc_info not passed"),
    ("TP", "no", "adapter wraps AsyncAnthropic().messages.create (async twin with the same removal); no sampling keywords passed"),
    ("TP", "no", "tools call beta.messages.create with output_config, not the removed output_format"),
    ("FP-resolution", "", "code uses top-level anyio.CancelScope; only the anyio.abc alias is deprecated in 4.15"),
    ("FP-resolution", "", "code uses top-level anyio.Event; only the anyio.abc alias is deprecated"),
    ("FP-resolution", "", "code uses top-level anyio.Lock; only the anyio.abc alias is deprecated"),
]


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def main():
    meta = json.loads((RW / "repos.json").read_text(encoding="utf-8"))
    rows = []
    for r in meta["repos"]:
        slug = r["full_name"].replace("/", "__")
        try:
            a = json.loads((RW / "scans" / f"{slug}.opus-5-5.json").read_text(encoding="utf-8"))
            b = json.loads((RW / "scans" / f"{slug}.cutoff-2025-07-31.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        if not (a.get("_ok") and b.get("_ok")):
            continue
        for u in a.get("used_apis") or []:
            rows.append({"repository": r["full_name"], "package": u["package"], "cutoff_version": u["cutoff_version"],
                         "locked": u["locked"], "api": u["api"],
                         "changes": "; ".join(f"{c['kind']}{':' + c['parameter'] if c.get('parameter') else ''}"
                                              for c in u["changes"]),
                         "tool_form": u["form"], "files": len(u["used_in"])})
    assert len(rows) == len(V) == 53, (len(rows), len(V))
    for row, (verdict, affected, reason) in zip(rows, V):
        row.update({"verdict": verdict, "affected": affected, "reason": reason})
    with open(ANALYSIS / "realworld_audit.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    tp = sum(r["verdict"] == "TP" for r in rows)
    old = [r for r in rows if r["tool_form"] == "old_form"]
    summary = {
        "matched_changed_apis": n,
        "used_changes_total": sum(len(r["changes"].split("; ")) for r in rows),
        "tp": tp, "fp_resolution": sum(r["verdict"] == "FP-resolution" for r in rows),
        "fp_diff": sum(r["verdict"] == "FP-diff" for r in rows),
        "precision": round(tp / n, 4), "precision_wilson95": wilson(tp, n),
        "tp_affected_yes": sum(r["affected"] == "yes" for r in rows),
        "tp_affected_handled": sum(r["affected"] == "handled" for r in rows),
        "tp_affected_no": sum(r["affected"] == "no" for r in rows),
        "tool_old_form_labels": len(old), "old_form_labels_correct": sum(r["affected"] == "yes" for r in old),
        "repos_with_match": len({r["repository"] for r in rows}),
        "repos_with_tp": len({r["repository"] for r in rows if r["verdict"] == "TP"}),
        "repos_total": 47,
    }
    summary["repos_with_tp_wilson95"] = wilson(summary["repos_with_tp"], 47)
    (ANALYSIS / "realworld_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
