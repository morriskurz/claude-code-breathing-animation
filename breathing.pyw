"""
Breathe — 4·7·8 breathing companion for Claude Code.

Starts automatically when Claude begins thinking (via hooks),
resets when Claude finishes. Orange pulse on notification (awaiting input).

Usage:
    python breathing.pyw                 Run normally (GUI window)
    python breathing.pyw --launch        Start detached & exit immediately
                                         (safe to call from hooks — idempotent,
                                          skips if already running)
"""

import tkinter as tk
import math
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os, sys
import subprocess
import socket

# ── Self-launcher (--launch mode) ──────────────────────────────
def _is_running(port=18478):
    """Check if the breathing server is already listening."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.3)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False

if "--launch" in sys.argv:
    if _is_running():
        sys.exit(0)                       # already running, nothing to do

    # Re-launch *this script* fully detached (no --launch flag)
    script = os.path.abspath(__file__)
    python = sys.executable

    if sys.platform == "win32":
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP → fully orphaned
        DETACHED = 0x00000008 | 0x00000200
        subprocess.Popen(
            [python, script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=DETACHED,
            close_fds=True,
        )
    else:
        # Unix: double-fork via nohup
        subprocess.Popen(
            ["nohup", python, script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    sys.exit(0)                           # hook returns instantly


# ── Breathing pattern ──────────────────────────────────────────
INHALE = 4.0
HOLD   = 7.0
EXHALE = 8.0

# ── Server ─────────────────────────────────────────────────────
PORT = 18478

# ── Default size ───────────────────────────────────────────────
DEF_W, DEF_H = 380, 440
MIN_R_RATIO  = 0.12   # min radius as fraction of min(w,h)
MAX_R_RATIO  = 0.30   # max radius as fraction of min(w,h)
FPS = 144

# ── Palette ────────────────────────────────────────────────────
BG = "#080808"

ACTIVE_CORE = "#5b9ea8"
ACTIVE_GLOW = ["#0c2028", "#163840", "#265a64", "#3d7a84"]

IDLE_CORE   = "#1e3a40"
IDLE_GLOW   = ["#0a1418", "#0e1e24", "#142a32", "#1a3038"]

COL_PHASE   = "#5a8888"
COL_TIMER   = "#4a7070"

GLOW_OFFSETS = [30, 21, 13, 6]

# ── Orange notification pulse ──────────────────────────────────
NOTIFY_DURATION = 2.0


class BreathingApp:
    """Minimalistic 4-7-8 breathing window with HTTP control."""

    # ── Setup ──────────────────────────────────────────────────
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Breathe")
        self.root.configure(bg=BG)
        self.root.minsize(200, 260)
        self.root.attributes("-topmost", False)
        self._center()
        self._dark_titlebar()

        self.c = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.c.pack(fill="both", expand=True)

        # canvas dimensions (updated on resize)
        self.cw = DEF_W
        self.ch = DEF_H
        self.cx = DEF_W // 2
        self.cy = DEF_H // 2 - 20
        self.min_r = 44.0
        self.max_r = 115.0

        # glow layers + core circle
        self.glow = [self.c.create_oval(0, 0, 0, 0, outline="") for _ in range(4)]
        self.core = self.c.create_oval(0, 0, 0, 0, outline="")

        # text elements (phase + countdown only)
        self.t_num   = self.c.create_text(0, 0, text="",
                                          font=("Segoe UI Light", 32), fill=COL_TIMER)
        self.t_phase = self.c.create_text(0, 0, text="",
                                          font=("Segoe UI Light", 13), fill=COL_PHASE)

        # notification pulse bars (above and below circle)
        self.notify_bar_top = self.c.create_rectangle(0, 0, 0, 0, outline="", fill=BG)
        self.notify_bar_bot = self.c.create_rectangle(0, 0, 0, 0, outline="", fill=BG)

        # state
        self.active    = False
        self.phase     = "idle"
        self.t0        = 0.0
        self.radius    = self.min_r
        self.fade_from = None

        # notification state
        self.notify_t0 = 0.0
        self.notifying = False

        # draw idle state
        self._circle(self.min_r, active=False)

        # handle resize
        self.c.bind("<Configure>", self._on_resize)

        # keyboard
        self.root.bind("<space>",  lambda _: self._toggle())
        self.root.bind("<Escape>", lambda _: self._quit())

        # http server
        threading.Thread(target=self._serve, daemon=True).start()

        # animation loop
        self._tick()

        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.mainloop()

    def _center(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{DEF_W}x{sh}+{sw - DEF_W}+0")

    def _dark_titlebar(self):
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    # ── Resize handling ────────────────────────────────────────
    def _on_resize(self, event):
        self.cw = event.width
        self.ch = event.height
        self.cx = self.cw // 2
        self.cy = self.ch // 2 - 20
        dim = min(self.cw, self.ch)
        self.min_r = max(30, dim * MIN_R_RATIO)
        self.max_r = max(60, dim * MAX_R_RATIO)

    # ── Drawing ────────────────────────────────────────────────
    def _circle(self, r, active=True):
        self.radius = r
        cx, cy = self.cx, self.cy
        glows = ACTIVE_GLOW if active else IDLE_GLOW
        fill  = ACTIVE_CORE if active else IDLE_CORE
        for i, gid in enumerate(self.glow):
            gr = r + GLOW_OFFSETS[i]
            self.c.coords(gid, cx - gr, cy - gr, cx + gr, cy + gr)
            self.c.itemconfig(gid, fill=glows[i])
        self.c.coords(self.core, cx - r, cy - r, cx + r, cy + r)
        self.c.itemconfig(self.core, fill=fill)

    def _label(self, phase_text, countdown):
        self.c.coords(self.t_num, self.cx, self.cy)
        self.c.coords(self.t_phase, self.cx, self.cy + self.max_r + 42)
        self.c.itemconfig(self.t_phase, text=phase_text)
        self.c.itemconfig(self.t_num,   text=str(int(countdown)))

    # ── Orange notification pulse ──────────────────────────────
    @staticmethod
    def _notify_color(t):
        """Return an #rrggbb orange string that rises and fades, t ∈ [0,1]."""
        # bell curve: peak at t≈0.25 then fade
        brightness = math.sin(t * math.pi) ** 2 * (1 - t * 0.4)
        brightness = max(0.0, min(1.0, brightness))
        r = int(0x90 * brightness)
        g = int(0x50 * brightness)
        b = int(0x08 * brightness)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _update_notify_bar(self):
        if not self.notifying:
            self.c.itemconfig(self.notify_bar_top, fill=BG)
            self.c.itemconfig(self.notify_bar_bot, fill=BG)
            return

        elapsed = time.time() - self.notify_t0
        if elapsed >= NOTIFY_DURATION:
            self.notifying = False
            self.c.itemconfig(self.notify_bar_top, fill=BG)
            self.c.itemconfig(self.notify_bar_bot, fill=BG)
            return

        t = elapsed / NOTIFY_DURATION
        col = self._notify_color(t)

        bar_w = int(self.cw * 0.30)
        bar_h = 3
        bx = self.cx - bar_w // 2
        # Position bars relative to circle (above and below with padding)
        padding = self.max_r + 60
        by_top = self.cy - padding
        by_bot = self.cy + padding
        self.c.coords(self.notify_bar_top, bx, by_top, bx + bar_w, by_top + bar_h)
        self.c.coords(self.notify_bar_bot, bx, by_bot, bx + bar_w, by_bot + bar_h)
        self.c.itemconfig(self.notify_bar_top, fill=col)
        self.c.itemconfig(self.notify_bar_bot, fill=col)

    # ── Easing ─────────────────────────────────────────────────
    @staticmethod
    def _ease(t):
        return -(math.cos(math.pi * t) - 1) / 2

    # ── Animation loop ─────────────────────────────────────────
    def _tick(self):
        now = time.time()

        # ---- fade-out transition ---------------------------
        if self.phase == "fade":
            e = now - self.t0
            d = 1.2
            if e >= d:
                self.phase = "idle"
            else:
                t = self._ease(e / d)
                r = self.fade_from + (self.min_r - self.fade_from) * t
                self._circle(r, active=False)

        # ---- active breathing ------------------------------
        elif self.active:
            e = now - self.t0

            if self.phase == "inhale":
                if e >= INHALE:
                    self.phase, self.t0, e = "hold", now, 0
                else:
                    r = self.min_r + (self.max_r - self.min_r) * self._ease(e / INHALE)
                    self._circle(r)
                    self._label("inhale", math.ceil(INHALE - e))

            if self.phase == "hold":
                if e >= HOLD:
                    self.phase, self.t0, e = "exhale", now, 0
                else:
                    r = self.max_r + math.sin(e * 1.5) * 2
                    self._circle(r)
                    self._label("hold", math.ceil(HOLD - e))

            if self.phase == "exhale":
                if e >= EXHALE:
                    self.phase, self.t0 = "inhale", now
                else:
                    r = self.max_r - (self.max_r - self.min_r) * self._ease(e / EXHALE)
                    self._circle(r)
                    self._label("exhale", math.ceil(EXHALE - e))

        # ---- idle pulse ------------------------------------
        else:
            # Gentle 6-second breathing cycle with smooth easing
            cycle = 6.0
            t = (now % cycle) / cycle
            # Smooth ease-in-out sine for butter-smooth animation
            ease = (math.sin((t * 2 - 0.5) * math.pi) + 1) / 2
            r = self.min_r + ease * 3
            self._circle(r, active=False)

        # notification pulse
        self._update_notify_bar()

        self.root.after(1000 // FPS, self._tick)

    # ── Control methods ────────────────────────────────────────
    def start(self):
        if not self.active:
            self.active = True
            self.phase  = "inhale"
            self.t0     = time.time()

    def stop(self):
        if self.active or self.phase not in ("idle", "fade"):
            self.active    = False
            self.fade_from = self.radius
            self.phase     = "fade"
            self.t0        = time.time()
            self.c.itemconfig(self.t_phase, text="")
            self.c.itemconfig(self.t_num,   text="")

    def notify(self):
        self.notify_t0 = time.time()
        self.notifying = True

    def _toggle(self):
        (self.stop if self.active else self.start)()

    def _quit(self):
        self.root.destroy()
        os._exit(0)

    # ── HTTP control server ────────────────────────────────────
    def _serve(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/start":
                    app.root.after(0, app.start)
                elif path == "/stop":
                    app.root.after(0, app.stop)
                elif path == "/notify":
                    app.root.after(0, app.notify)
                elif path == "/toggle":
                    app.root.after(0, app._toggle)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_):
                pass

        try:
            HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
        except OSError as e:
            print(f"Could not start control server on port {PORT}: {e}",
                  file=sys.stderr)


if __name__ == "__main__":
    BreathingApp()
