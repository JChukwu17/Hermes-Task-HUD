# Hermes Task HUD plugin

A floating, always-on-task HUD for Hermes: a small heads-up overlay that reports
what the current session is doing (active tool, progress, last update) so you can
keep an eye on long-running agents without switching windows.

## How it works

The plugin is four cooperating pieces:

| File | Role |
| --- | --- |
| `plugin.yaml` | v2 manifest. Declares `kind: standalone` and registers three lifecycle hooks via `provides_hooks`: `pre_llm_call`, `pre_tool_call`, `on_session_end`. |
| `__init__.py` | Python plugin entry. `register(ctx)` wires the hooks (no side effects at import). The hook handlers observe the session and write a small state file consumed by the widget. |
| `hermes_hud.py` | Lightweight HTTP daemon bound to `127.0.0.1:47614`. Serves the widget HTML and the live state JSON with `Cache-Control: no-store` so the browser never caches stale state. Single-instance guarded. |
| `hermes-task-widget.html` | The floating widget. Fetches `task_state.json`, renders the task name and a progress bar, and animates idle → running → completed → idle. The footer shows the last `updated` time. |
| `desktop/plugin.js` | Hermes UI glue. Adds an "Open Task HUD" palette command that launches `http://127.0.0.1:47614`, and exposes an `openExternal(url)` helper backed by `ctx.os.openExternal`. |

## Usage

1. Install the plugin into your Hermes `plugins/task-hud/` directory (or via
   `hermes plugins install`).
2. Open the palette (`⌘K` on macOS / `Ctrl+P` on Windows-Linux) and run
   **"Open Task HUD"** — the floating widget opens and auto-connects to the
   daemon on `127.0.0.1:47614`.
3. As a session runs, the widget shows the current task name and progress. On
   `on_session_end` it marks the run completed (progress `100%`).

> Hermes plugins have no file watcher. After editing a plugin file, **reload
> plugins** (`⌘K` palette → reload) so the running daemon picks up the change.

## State contract

`__init__.py` writes `task_state.json` consumed by `hermes-task-widget.html`.
The schema (authoritative, not the prose above) is:

```jsonc
{
  "task":    "current task name (or \"Task\" if none)", // pre_llm_call / pre_tool_call
  "step":    "human-readable current action, e.g. \"terminal · call 3\"",
  "progress": 0..100,        // creeps toward ~95 while running; 100 on on_session_end
  "state":   "idle|running|completed",
  "run_id":   <ms epoch>,    // fresh per cycle, monotonic
  "updated":  <ms epoch>     // milliseconds, NOT seconds
}
```

- Timestamps (`run_id`, `updated`) are **milliseconds since epoch**.
- `progress` rises as the run advances and is not pinned to 100 while the
  session is still active.
- `on_session_end` finalises the run with `progress: 100` and `state: completed`.
- A stale/unknown session resets `state` to `idle` — the previous task name is
  preserved (falling back to `"Task"` only when no task has been seen yet).

## Development

- Python entry is import-safe: `register(ctx)` is the only side-effectful call,
  and it is invoked by the platform, not at module import.
- External dependencies (declared under `python_dependencies` in `plugin.yaml`)
  are **validated and surfaced only** — Hermes never auto-installs them. Guard
  their imports in code (`try/except ImportError`) and degrade cleanly.
- Verify the hook handlers with the on-disk harness: confirm progress
  `3 → 14 → 26`, `on_session_end` finalises at `100`, and stale reset preserves
  the last real task name.

## Fixes tracked in this release

- Removed a stale dev string (`"Twitter Search: ElChicoEeeee…"`) that was
  overwriting the real task name on session-resume turns.
- `desktop/plugin.js`: `host.os.openExternal(...)` was a no-op (`host` has no
  `.os`); replaced with `ctx.os.openExternal(...)` passed from `register(ctx)`.
- Footer now renders the state file's `updated` timestamp.
- Stale reset preserves the last known task instead of clobbering to `"Task"`.
