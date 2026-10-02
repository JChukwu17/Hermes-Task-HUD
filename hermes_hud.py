#!/usr/bin/env python3
"""Hermes HUD launcher (v2).

Watches task_state.json (written by the task-hud Hermes plugin) and shows a
small always-on-top window while a task is running or finished-but-unseen.
The HUD hides itself whenever a Hermes window is in the foreground.

Setup:  pip install pywebview  (optional — without it the server still runs
        so the widget can be opened manually in a browser)
Run:    pythonw hermes_hud.py     (the plugin starts this for you)
Tune:   python hermes_hud.py --debug   # prints the foreground window each second
"""
import argparse, ctypes, functools, http.server, json, os, socket
import socketserver, threading, time
from pathlib import Path

try:
    import webview
except ImportError:
    webview = None  # graceful degradation: serve only, no window

W, H, MARGIN, TASKBAR = 360, 235, 24, 48
LOCK_PORT = 47613  # single-instance guard
HTTP_PORT = 47614  # fixed port so the desktop plugin can link to the widget


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(folder):
    handler = functools.partial(QuietHandler, directory=str(folder))
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", HTTP_PORT), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return HTTP_PORT


def foreground():
    """(title, exe, pid) of the foreground window, or None (Windows only)."""
    if os.name != "nt":
        return None
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return None
    n = u32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, title, n + 1)
    pid = ctypes.c_ulong()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = k32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if h:
        size, path = ctypes.c_ulong(520), ctypes.create_unicode_buffer(520)
        if k32.QueryFullProcessImageNameW(h, 0, path, ctypes.byref(size)):
            exe = os.path.basename(path.value)
        k32.CloseHandle(h)
    return title.value, exe, pid.value


def hermes_focused(match, debug=False):
    info = foreground()
    if debug:
        print("foreground:", info, flush=True)
    if not info or info[2] == os.getpid():  # the HUD itself doesn't count
        return False
    text = f"{info[0]} {info[1]}".lower()
    return any(m in text for m in match)


def watch(window, url, state_path, match, grace, poll, debug):
    visible, idle_since, acked, last = False, None, None, None

    def show(v):
        nonlocal visible
        if v and not visible:
            window.evaluate_js("location.reload()")  # drop any stale state
            window.show()
            visible = True
        elif not v and visible:
            window.hide()
            visible = False

    while True:
        try:
            last = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass  # missing file / mid-write: keep last known state
        focused = hermes_focused(match, debug)
        if last:
            status, rid = last.get("status", "idle"), last.get("run_id")
            if status == "idle":
                idle_since = idle_since or time.time()
                if time.time() - idle_since > grace:
                    show(False)
            else:
                idle_since = None
                if status in ("completed", "error") and focused:
                    acked = rid  # you've seen the result
                seen = status in ("completed", "error") and acked == rid
                show(not (focused or seen))
        time.sleep(poll)


def main():
    try:
        from hermes_constants import get_hermes_home
        default_dir = Path(get_hermes_home()) / "hud"
    except Exception:
        default_dir = Path(os.environ.get("HERMES_HUD_DIR") or (Path.home() / ".hermes" / "hud"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(default_dir))
    ap.add_argument("--match", default=os.environ.get("HERMES_HUD_MATCH", "hermes"),
                    help="comma-separated substrings of the window title / exe name that count as 'in Hermes'")
    ap.add_argument("--grace", type=float, default=5)
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--no-window", action="store_true",
                    help="Run the HTTP server only (no pywebview window)")
    args = ap.parse_args()

    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
        lock.listen(1)
    except OSError:
        return  # another HUD is already running

    folder = Path(args.dir).resolve()
    port = serve(folder)
    url = f"http://127.0.0.1:{port}/hermes-task-widget.html"

    if webview is None or args.no_window:
        print(f"HUD server running (pywebview not available): {url}", flush=True)
        if args.debug:
            match = [m.strip().lower() for m in args.match.split(",") if m.strip()]
            watch(None, url, folder / "task_state.json", match,
                  args.grace, args.poll, True)
        else:
            # Block so the server stays alive; Ctrl-C to stop.
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
        return

    x = y = None
    try:
        s = webview.screens[0]
        x, y = s.width - W - MARGIN, s.height - H - MARGIN - TASKBAR
    except Exception:
        pass
    window = webview.create_window(
        "Task HUD", url, width=W, height=H, x=x, y=y, frameless=True,
        easy_drag=True, on_top=True, resizable=False, hidden=True)
    match = [m.strip().lower() for m in args.match.split(",") if m.strip()]
    webview.start(watch, (window, url, folder / "task_state.json", match,
                          args.grace, args.poll, args.debug))


if __name__ == "__main__":
    main()
