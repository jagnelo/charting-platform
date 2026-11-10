#!/usr/bin/env python3
"""Run one turn in a named orchestration chat (runtime adapter).

This is the Claude Code equivalent of the Codex App Server `turn/start` that
the coordinator used to drive worker threads. Each chat is a normal Claude Code
session stored under the main checkout's project, so it appears in the VS Code
extension's chat-history dropdown and can be opened there at any time.

Usage (run from anywhere):
  agent-turn.py list
  agent-turn.py run <chat> "<prompt>"            # blocks, prints the reply
  agent-turn.py run <chat> --prompt-file F
  agent-turn.py run <chat> --allow 'Bash(docker compose:*)' "<prompt>"
  agent-turn.py run <chat> --interrupt "<prompt>"  # stop a running turn first
  agent-turn.py last <chat>                      # print the last saved reply

<chat> is a roster key (tc, strategy, etf, provider, root), a slug or a chat name.
--allow pre-approves a tool pattern for that one turn. This is how the
coordinator grants a permission a worker reported under DENIED.
Each reply is saved as JSON in turns/<slug>/ next to the roster.
The roster path comes from $AGENT_ROSTER (default ./roster.json). Example:
  {"runtime": "claude-code", "cwd": "/path/to/main/checkout",
   "chats": {"tc": {"name": "feat/x", "slug": "feat-x", "session_id": "<uuid>",
             "model": "claude-haiku-5-5", "effort": "low", "permission_mode": "auto"}}}
Chats are created with `run <chat> --create "<seed prompt>"`.
CLAUDE_CODE_ENTRYPOINT=claude-vscode is set so the chats are listed in the VS Code
extension's history (it hides chats recorded as headless SDK runs).

The roster (roster.json) names the runtime. Only "claude-code" is implemented
here; another runtime needs its own adapter with the same commands.
"""
import argparse, datetime, fcntl, glob, json, os, signal, subprocess, sys, time

ROSTER_PATH = os.path.abspath(os.environ.get("AGENT_ROSTER", "roster.json"))
HERE = os.path.dirname(ROSTER_PATH)  # turns/ and locks/ live next to the roster
ROSTER = json.load(open(ROSTER_PATH))


def find_chat(key):
    for k, c in ROSTER["chats"].items():
        if key in (k, c["slug"], c["name"], c["session_id"]):
            return k, c
    sys.exit(f"unknown chat {key!r}; known: {', '.join(ROSTER['chats'])}")


def claude_bin():
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    found = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude")),
        key=os.path.getmtime)
    if not found:
        sys.exit("Claude Code binary not found; set CLAUDE_BIN")
    return found[-1]


def build_cmd(c, prompt, allow, create=False):
    cmd = [claude_bin(), "-p", "--model", c["model"], "--effort", c["effort"],
           "--permission-mode", c.get("permission_mode", "auto"),
           "--output-format", "json"]
    cmd += ["--session-id", c["session_id"], "-n", c["name"]] if create else ["--resume", c["session_id"]]
    for a in allow or []:
        cmd += ["--allowedTools", a]
    return cmd + [prompt]


def run_turn(c, prompt, allow=None, create=False, interrupt=False, timeout=None):
    if ROSTER.get("runtime") != "claude-code":
        sys.exit("only the claude-code adapter is implemented")
    os.makedirs(os.path.join(HERE, "locks"), exist_ok=True)
    lock_path = os.path.join(HERE, "locks", c["slug"] + ".lock")
    lock = open(lock_path, "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.seek(0)
        pid = (lock.read().strip() or "0")
        if not interrupt:
            print(f"BUSY: {c['name']} is already running a turn (pid {pid}). "
                  "Wait for it, or pass --interrupt to stop it and send this instead.")
            return 3
        try:
            os.kill(int(pid), signal.SIGINT)
        except (ProcessLookupError, ValueError):
            pass
        fcntl.flock(lock, fcntl.LOCK_EX)
    env = dict(os.environ, CLAUDE_CODE_ENTRYPOINT="claude-vscode")
    started = time.time()
    proc = subprocess.Popen(build_cmd(c, prompt, allow, create), cwd=ROSTER["cwd"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lock.seek(0); lock.truncate(); lock.write(str(proc.pid)); lock.flush()
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate()
    lock.seek(0); lock.truncate(); lock.flush()
    fcntl.flock(lock, fcntl.LOCK_UN)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = {"is_error": True, "result": (out or "")[-4000:], "stderr": (err or "")[-4000:]}
    data["_prompt"] = prompt
    data["_allow"] = allow or []
    data["_elapsed_s"] = round(time.time() - started)
    d = os.path.join(HERE, "turns", c["slug"])
    os.makedirs(d, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(os.path.join(d, stamp + ".json"), "w") as f:
        json.dump(data, f, indent=1)
    show(c, data)
    return 1 if data.get("is_error") else 0


def show(c, data):
    print(f"== {c['name']} | error={data.get('is_error')} | {data.get('_elapsed_s')}s | "
          f"cost=${data.get('total_cost_usd', 0) or 0:.2f}")
    print(data.get("result") or data.get("stderr") or "(no reply text)")
    for d in data.get("permission_denials") or []:
        print("PERMISSION-DENIED:", json.dumps(d)[:600])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("chat"); r.add_argument("prompt", nargs="?")
    r.add_argument("--prompt-file"); r.add_argument("--allow", action="append")
    r.add_argument("--interrupt", action="store_true"); r.add_argument("--timeout", type=int)
    r.add_argument("--create", action="store_true", help=argparse.SUPPRESS)
    l = sub.add_parser("last"); l.add_argument("chat")
    a = p.parse_args()
    if a.cmd == "list":
        for k, c in ROSTER["chats"].items():
            print(f"{k:9} {c['name']:38} {c['model']}/{c['effort']:6} {c['session_id']}  {c.get('worktree','')}")
        return 0
    k, c = find_chat(a.chat)
    if a.cmd == "last":
        files = sorted(glob.glob(os.path.join(HERE, "turns", c["slug"], "*.json")))
        if not files:
            print("no saved turns"); return 0
        show(c, json.load(open(files[-1]))); return 0
    prompt = open(a.prompt_file).read() if a.prompt_file else a.prompt
    if not prompt:
        sys.exit("give a prompt or --prompt-file")
    return run_turn(c, prompt, a.allow, a.create, a.interrupt, a.timeout)


if __name__ == "__main__":
    sys.exit(main())
