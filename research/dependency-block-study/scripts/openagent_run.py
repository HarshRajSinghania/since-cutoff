"""Workstream B: run a benchmark study with an open-weight model in mini-swe-agent instead of Claude Code.

Run with the isolated venv sc_openagent\\venv (mini-swe-agent 2.4.6); the benchmark harness
(stdlib only) is imported from ~/projects/since-cutoff-benchmark for tasks, notes/conditions, env locks, venvs and
grading, so tasks, CLAUDE.md text, venvs and hidden-test grading are byte-identical to the Claude Code studies.
Only the agent differs: mini-swe-agent's default (bash-only) agent, the model behind a local OpenAI-compatible
llama-server, and the condition's CLAUDE.md text both written into the project and prepended to the task prompt
(Claude Code loads CLAUDE.md into context by itself; mini-swe-agent does not).

usage:
  python openagent_run.py --config <bench toml> --study-id <id> --api-base http://127.0.0.1:8080/v1 \
      --model-name openai/<alias> [--max-sessions N] [--step-limit 40] [--textbased] [--only <run_id,...>] [--dry-run]
The plan is written beforehand with `python -m bench --config <toml> plan ...` (same format as the Claude studies).
Records: <results>/<study>/runs/<attempt_id>/record.json (schema since-cutoff-bench/openagent-run@1),
trajectory.json, final.diff, CLAUDE.md, prompt.txt, grade.log.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BENCH = Path.home() / "projects" / "since-cutoff-benchmark"
sys.path.insert(0, str(BENCH))

from bench import conditions, envs, grade, runner, transcript, util  # noqa: E402
from bench.config import expand, load as load_config  # noqa: E402

# keep mini-swe-agent away from any user-level config/.env (API keys) and its telemetry-free defaults explicit
os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(Path(r"sc_openagent\mswea-config"))
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import yaml  # noqa: E402  (mini-swe-agent dependency)
from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402

SCHEMA = "since-cutoff-bench/openagent-run@1"
DEAD_PROXY = "http://127.0.0.1:9"
VALID_EXITS = {"Submitted", "LimitsExceeded", "TimeExceeded", "RepeatedFormatError", "ContextExceeded"}


def agent_env(cfg, venv: Path, home: Path, tmp: Path) -> dict[str, str]:
    """Environment of every bash command the agent runs: built from scratch, no user variables or secrets."""
    git_bash = expand(cfg.claude["git_bash"])
    git_root = git_bash.parent.parent  # C:/Program Files/Git
    env = util.system_env()
    env["PATH"] = os.pathsep.join([str(util.venv_bin(venv)), str(git_root / "usr" / "bin"), str(git_root / "mingw64" / "bin"),
                                   *util.system_path_dirs()])
    env.update({
        "VIRTUAL_ENV": str(venv), "HOME": str(home), "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "TEMP": str(tmp), "TMP": str(tmp), "HF_HOME": str(tmp / "hf"), "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "HTTP_PROXY": DEAD_PROXY, "HTTPS_PROXY": DEAD_PROXY, "http_proxy": DEAD_PROXY, "https_proxy": DEAD_PROXY,
        "PYTEST_ADDOPTS": "--allow-hosts=127.0.0.1,::1", "PYTHONIOENCODING": "utf-8", "PAGER": "cat",
    })
    return env


class BashEnvironment(LocalEnvironment):
    """mini-swe-agent's local environment, but every command runs in Git Bash with a fixed, scrubbed environment.

    Also records the first command after which a target file changed (for stale_in_first_edit)."""

    def __init__(self, *, bash: str, clean_env: dict[str, str], project: Path, targets: list[str], **kwargs):
        super().__init__(**kwargs)
        self._bash, self._env, self._project, self._targets = bash, clean_env, project, targets
        self._initial = {t: self._read(t) for t in targets}
        self.first_edit: dict | None = None
        self.n_commands = 0

    def _read(self, rel: str) -> bytes | None:
        p = self._project / rel
        return p.read_bytes() if p.exists() else None

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict:
        command = action.get("command", "")
        self.n_commands += 1
        try:
            proc = subprocess.run([self._bash, "-c", command], cwd=str(self._project), env=self._env,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout or self.config.timeout)
            output = {"output": proc.stdout + proc.stderr, "returncode": proc.returncode, "exception_info": ""}
        except subprocess.TimeoutExpired as e:
            out = e.output.decode("utf-8", "replace") if isinstance(e.output, bytes) else (e.output or "")
            output = {"output": out, "returncode": -1, "exception_info": f"command timed out after {e.timeout}s"}
            util.kill_processes_under(self._project)
        if self.first_edit is None:
            now = {t: self._read(t) for t in self._targets}
            changed = [t for t in self._targets if now[t] != self._initial[t]]
            if changed:
                before = {t: self._initial[t] or b"" for t in changed}
                after = {t: now[t] or b"" for t in changed}
                diff = runner.unified_diff(before, after)
                self.first_edit = {"command_index": self.n_commands, "files": changed,
                                   "stale": transcript.stale_matches(transcript.added_lines(diff), self._patterns)}
        self._check_finished(output)
        return output

    _patterns: list[str] = []


def usage_of(messages: list[dict]) -> dict[str, int]:
    tot = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    for m in messages:
        resp = (m.get("extra") or {}).get("response")
        if isinstance(resp, dict) and resp.get("usage"):
            u = resp["usage"]
            tot["input_tokens"] += int(u.get("prompt_tokens") or 0)
            tot["output_tokens"] += int(u.get("completion_tokens") or 0)
            tot["calls"] += 1
    tot["total_tokens"] = tot["input_tokens"] + tot["output_tokens"]
    return tot


def run_one(cfg, st, entry: dict, args, mini_cfg: dict) -> dict:
    task = st.tasks[entry["task"]]
    cond = conditions.get(entry["condition"])
    attempt_id = entry["run_id"]
    project = st.runs_root / attempt_id
    art = st.dir / "runs" / attempt_id
    util.rmtree(project)
    attempt = 1
    if (art / "record.json").exists():  # section 10: an infrastructure-invalid session is re-run (max 3 attempts)
        prev = json.loads((art / "record.json").read_text(encoding="utf-8"))
        attempt = int(prev.get("attempt", 1)) + 1
        (art.parent.parent / "runs_invalid").mkdir(exist_ok=True)
        art.rename(art.parent.parent / "runs_invalid" / f"{attempt_id}.attempt{attempt - 1}")
    art.mkdir(parents=True, exist_ok=True)
    if task.sha256() != entry["task_sha256"]:
        raise RuntimeError(f"{task.key} changed after the plan was written")
    util.copy_clean(task.repo, project)
    text = conditions.claude_md(cfg, task, cond, st.manifest)
    (project / "CLAUDE.md").write_text(text, encoding="utf-8")
    (art / "CLAUDE.md").write_text(text, encoding="utf-8")
    prompt = ("Project instructions (CLAUDE.md in the repository root):\n\n" + text.strip() + "\n\n---\n\nTask:\n"
              + task.prompt.strip())
    (art / "prompt.txt").write_text(prompt, encoding="utf-8")
    initial = util.snapshot(project)
    home = cfg.p("home") / st.study_id / attempt_id
    tmp = cfg.p("tmp") / st.study_id / attempt_id
    for d in (home, tmp):
        util.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    venv = project / ".venv"
    record = {"schema": SCHEMA, "study_id": st.study_id, "run_id": entry["run_id"], "attempt": attempt,
              "attempt_id": attempt_id, "task": task.key, "task_id": task.id, "task_sha256": entry["task_sha256"],
              "library": task.library, "stratum": task.stratum, "kind": task.kind, "condition": cond.name,
              "rep": entry["rep"], "block_id": entry["block_id"], "order_index": entry["order_index"],
              "pilot": entry.get("pilot", False),
              "condition_config": conditions.condition_config(cfg, task, cond, text, st.staged, st.manifest),
              "agent": {"scaffold": "mini-swe-agent", "model_name": args.model_name, "api_base": args.api_base,
                        "step_limit": args.step_limit, "textbased": args.textbased,
                        "wall_limit_s": int(args.wall_limit or min(cfg.claude["wall_timeout_s"], task.timeout_s)),
                        "temperature": args.temperature, "command_timeout_s": args.command_timeout},
              "harness": {"code_sha256": runner.harness_sha256(), "adapter_sha256": util.sha256_file(Path(__file__))}}
    if args.dry_run:
        record.update({"dry_run": True, "valid": None})
        util.write_json(art / "dry_run.json", record)
        return record
    lock = envs.load_lock(cfg, envs.spec_for(cfg, task, task.pinned).env_id)
    envs.build_venv(cfg, lock, venv)
    envs.isolate_python(venv, tmp / "hf")
    freeze_before = envs.pip_list(venv)

    env = BashEnvironment(bash=str(expand(cfg.claude["git_bash"])), clean_env=agent_env(cfg, venv, home, tmp),
                          project=project, targets=list(task.target_files), timeout=args.command_timeout)
    env._patterns = list(task.stale_patterns)
    if args.textbased:
        from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel as Model
    else:
        from minisweagent.models.litellm_model import LitellmModel as Model
    model = Model(model_name=args.model_name, cost_tracking="ignore_errors",
                  model_kwargs={"api_base": args.api_base, "api_key": "sk-local-no-key", "temperature": args.temperature,
                                "timeout": 600})
    agent_cfg = dict(mini_cfg["agent"])
    agent_cfg.update({"step_limit": args.step_limit, "cost_limit": 0.0,
                      "wall_time_limit_seconds": int(args.wall_limit or min(cfg.claude["wall_timeout_s"], task.timeout_s)),
                      "output_path": art / "trajectory.json"})
    agent = DefaultAgent(model, env, **agent_cfg)
    t0 = time.time()
    error = None
    context_note = None
    try:
        result = agent.run(prompt)
    except Exception as exc:  # infrastructure failure (server down, ...) or context overflow
        msg = f"{type(exc).__name__}: {exc}"
        low = msg.lower()
        if "contextwindowexceeded" in low or ("context" in low and ("exceed" in low or "too long" in low)):
            # section 10: the conversation outgrew the slot's context = the agent ran out of room (valid failure,
            # like a turn limit), not an infrastructure failure
            result = {"exit_status": "ContextExceeded"}
            error = None
            context_note = msg[:500]
        else:
            result = {"exit_status": type(exc).__name__}
            error = msg[:2000]
    wall = time.time() - t0
    orphans = util.kill_processes_under(project)
    final = util.snapshot(project)
    diff = runner.unified_diff(initial, final)
    (art / "final.diff").write_text(diff, encoding="utf-8")
    exit_status = result.get("exit_status")
    valid = exit_status in VALID_EXITS and error is None
    usage = usage_of(agent.messages)
    record.update({
        "wall_s": round(wall, 1), "exit": {"status": exit_status, "error": error, "context_note": context_note, "orphans_killed": orphans},
        "process": {"turns": agent.n_calls, "commands": env.n_commands, **usage,
                    "first_edit": env.first_edit,
                    "stale_in_first_edit": bool(env.first_edit and env.first_edit["stale"]),
                    "stale_in_final": bool(transcript.stale_matches(transcript.added_lines(diff), task.stale_patterns)),
                    "files_changed": sorted(n for n in set(initial) | set(final) if initial.get(n) != final.get(n))},
        "venv": envs.venv_diff(freeze_before, envs.pip_list(venv)) if venv.exists() else {"modified": None},
        "valid": valid, "invalid_reason": None if valid else (error or exit_status), "grade": None,
    })
    if valid:
        grade_root = st.runs_root / "_grade" / attempt_id
        g = grade.grade_project(cfg, task, project, grade_root)
        log = Path(g.pop("log"))
        if log.exists():
            (art / "grade.log").write_bytes(log.read_bytes())
        util.kill_processes_under(grade_root)
        util.try_rmtree(grade_root)
        record["grade"] = g
    util.try_rmtree(venv)
    util.try_rmtree(tmp)
    util.write_json(art / "record.json", record)
    status = ("PASS" if (record["grade"] or {}).get("passed") else "fail") if valid else f"INVALID ({record['invalid_reason']})"
    print(f"  <- {attempt_id}: {status} in {wall:.0f}s, turns {agent.n_calls}, tokens {usage['total_tokens']}", flush=True)
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--study-id", required=True)
    ap.add_argument("--api-base", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--step-limit", type=int, default=40)
    ap.add_argument("--command-timeout", type=int, default=180)
    ap.add_argument("--wall-limit", type=int, default=0, help="agent wall-time limit in s (default: config/task, 900)")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--textbased", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--reps", default="", help="comma-separated reps to run (section 10: rep-major order)")
    ap.add_argument("--shard", default="", help="i/n: run only every n-th pending session starting at i (parallel slots)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    st = runner.open_study(cfg, args.study_id)
    import minisweagent
    yaml_name = "mini_textbased.yaml" if args.textbased else "default.yaml"
    mini_cfg = yaml.safe_load((Path(minisweagent.__file__).parent / "config" / yaml_name).read_text(encoding="utf-8"))
    plan = runner.load_plan(cfg, args.study_id)
    only = {x for x in args.only.split(",") if x}
    done = set()
    for p in (st.dir / "runs").glob("*/record.json") if (st.dir / "runs").exists() else []:
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("valid") or int(r.get("attempt", 1)) >= 3:
            done.add(p.parent.name)
    reps = {int(x) for x in args.reps.split(",") if x}
    todo = [e for e in plan if e["run_id"] not in done and (not only or e["run_id"] in only)
            and (not reps or int(e["rep"]) in reps)]
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        todo = todo[i::n]
    if args.max_sessions:
        todo = todo[: args.max_sessions]
    print(f"{args.study_id}: {len(todo)} sessions to run ({len(done)} already recorded)", flush=True)
    for e in todo:
        print(f"  -> {e['run_id']} ({e['task']} {e['condition']} rep {e['rep']})", flush=True)
        run_one(cfg, st, e, args, mini_cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
