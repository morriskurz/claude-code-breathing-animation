# Breathe — 4·7·8 Breathing for Claude Code

A minimalistic breathing animation that activates the moment you submit a prompt to Claude Code and resets when it finishes.

```
inhale 4s → hold 7s → exhale 8s
```

---

## Quick Start

### 1. Launch the breathing window

```bash
# No console window (recommended)
pythonw breathing.pyw

# With console (for debugging)
python breathing.pyw
```

The window appears centered, always-on-top, with a gentle idle pulse.

### 2. Configure Claude Code hooks

Add the following to **`~/.claude/settings.json`** (create the file if it doesn't exist).

If the file already has content, merge the `hooks` section into the existing JSON.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s http://localhost:18478/start || exit 0"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s http://localhost:18478/stop || exit 0"
          }
        ]
      }
    ]
  }
}
```

### 3. Restart Claude Code

Claude Code snapshots hooks at startup, so restart it after editing settings. If prompted, review and approve the new hooks in the `/hooks` menu.

---

## How It Works

| Event | Hook | Effect |
|---|---|---|
| User submits a prompt | `UserPromptSubmit` | Sends `GET /start` → breathing begins |
| Claude finishes its turn | `Stop` | Sends `GET /stop` → smooth fade to idle |

The app listens on `localhost:18478`. The breathing starts the moment you press Enter, so you can begin relaxing immediately while Claude thinks. Repeated `/start` calls while already breathing are ignored (no restart mid-cycle). The `|| exit 0` ensures the hook never fails even if the breathing app isn't running.

---

## Controls

| Key | Action |
|---|---|
| `Space` | Toggle breathing manually |
| `Escape` | Quit |

---

## HTTP API (for custom integrations)

```
GET http://localhost:18478/start    → begin breathing
GET http://localhost:18478/stop     → fade to idle
GET http://localhost:18478/toggle   → toggle on/off
```

---

## Troubleshooting

**Window doesn't appear** — Make sure Python 3 is installed and `tkinter` is available (`python -c "import tkinter"`).

**Hooks not triggering** — Restart Claude Code after editing settings. Use `/hooks` inside Claude Code to verify hooks are loaded.

**Port conflict** — Change `PORT = 18478` at the top of `breathing.pyw` and update the URLs in `settings.json` to match.

**Title bar is light** — The dark title bar requires Windows 10 20H1 or later. On older versions it falls back to the system theme.

---

## Requirements

- Python 3.7+ (uses only standard library — no pip installs)
- Windows 10/11 (also works on macOS/Linux, dark title bar is Windows-only)
- `curl` available in PATH (ships with Windows 10+)
