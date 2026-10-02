"""task-hud: writes Hermes task state for the floating HUD and starts it on demand."""
import json, math, os, shutil, subprocess, threading, time
from pathlib import Path

# Profile-safe Hermes home (get_hermes_home understands $HERMES_HOME / profiles)
try:
    from hermes_constants import get_hermes_home
    _HERMES_HOME = Path(get_hermes_home())
except Exception:
    _HERMES_HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))

HUD_DIR = Path(os.environ.get("HERMES_HUD_DIR") or (_HERMES_HOME / "hud"))
STATE = HUD_DIR / "task_state.json"
PLUGIN_DIR = Path(__file__).resolve().parent  # ships hermes_hud.py + widget HTML
HUD_PYTHON = os.environ.get("HERMES_HUD_PYTHON", "pythonw")  # needs pywebview installed

_lock = threading.Lock()
_run = {"id": 0, "task": "Task", "tools": 0}
_launched = False
_SESSION_START = int(time.time() * 1000)


def _ensure_fresh_state():
    """If the session was resumed (pre_llm_call didn't fire), reset stale counters."""
    global _run
    now = int(time.time() * 1000)
    # If run_id is older than 5 minutes, the pre_llm_call hook never fired
    # for this session (e.g. after context compaction resume). Reset counters.
    if _run["id"] > 0 and now - _run["id"] > 300_000:
        # Stale run (e.g. compaction-resume where pre_llm_call didn't fire): reset the
        # tool counter + run id for a fresh turn, but PRESERVE the last known task name
        # so the HUD keeps showing what the user is working on instead of a bare "Task".
        _run.update(id=now, tools=0, task=_run.get("task") or "Task")


def _write(**fields):
    data = {"run_id": _run["id"], "task": _run["task"], "updated": int(time.time() * 1000), **fields}
    with _lock:
        try:
            HUD_DIR.mkdir(parents=True, exist_ok=True)
            tmp = STATE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            for _ in range(5):  # Windows: the HUD may be reading the file
                try:
                    os.replace(tmp, STATE)
                    break
                except PermissionError:
                    time.sleep(0.05)
        except Exception:
            pass  # a HUD problem must never break the agent


def _ensure_hud():
    """Start the HUD once per Hermes process; the HUD ignores duplicates."""
    global _launched
    if _launched:
        return
    _launched = True
    # The launcher and widget HTML ship in the plugin directory; copy the
    # widget into HUD_DIR so the HUD's HTTP server can serve it, and point
    # the HUD at HUD_DIR for task_state.json.
    script = PLUGIN_DIR / "hermes_hud.py"
    if not script.exists():
        return
    try:
        HUD_DIR.mkdir(parents=True, exist_ok=True)
        widget = PLUGIN_DIR / "hermes-task-widget.html"
        if widget.exists():
            shutil.copy2(str(widget), str(HUD_DIR / "hermes-task-widget.html"))
    except Exception:
        pass
    flags = 0x00000008 | 0x08000000 if os.name == "nt" else 0  # DETACHED | NO_WINDOW
    try:
        subprocess.Popen([HUD_PYTHON, str(script), "--dir", str(HUD_DIR)],
                         cwd=str(HUD_DIR),
                         creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _on_turn_start(user_message="", **kw):
    lines = (user_message or "").strip().splitlines()
    _run.update(id=int(time.time() * 1000), tools=0, task=(lines[0][:80] if lines else "Task"))
    _ensure_hud()
    _write(status="running", step="Thinking…", progress=3)


def _on_tool(**kw):
    _ensure_fresh_state()
    _run["tools"] += 1
    n = _run["tools"]
    name = kw.get("tool_name") or kw.get("name") or "tool"
    # Hermes doesn't know how long a task will take, so this bar is only an
    # activity gauge that creeps toward ~95% as tool calls accumulate.
    _write(status="running", step=f"{name} · call {n}", progress=round(95 * (1 - 0.85 ** n)))


def _on_turn_end(**kw):
    _write(status="completed", step="Finished", progress=100)


def register(ctx):
    ctx.register_hook("pre_llm_call", _on_turn_start)
    ctx.register_hook("pre_tool_call", _on_tool)
    ctx.register_hook("on_session_end", _on_turn_end)
