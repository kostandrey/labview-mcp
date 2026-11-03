"""Tkinter UI - tab layout mirrors the original Continuous2D moco.vi
front panel: Mode tab with pages Init / Params / Moving, Message status
line, Current Position (Xnow/Ynow), error? indicator and the XY path
"Pattern preview" canvas.

All device I/O is marshalled through TshController.submit(); callbacks
are re-dispatched onto the tkinter thread via root.after.
"""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk, messagebox

from .config import Settings
from .controller import TshController
from .patterns import ContourParams, UiPattern, convert_motion_params

PATTERN_ITEMS = ["Random", "Oval", "Raster", "Only X", "Only Y", "CrM-1axis"]
UI_TO_ENUM = {name: UiPattern(i) for i, name in enumerate(PATTERN_ITEMS)}
POLL_MS = 200


class MocoApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ctl = TshController(settings)
        self.root = tk.Tk()
        self.root.title("Continuous motion - Translating Sample Holder")
        self.root.geometry("860x560")
        self._ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self._trace: list[tuple[float, float]] = []
        self._paused = False
        self._pattern_args = None  # last TshStartArgs, for Pause/Resume
        self._build()
        self.root.after(POLL_MS, self._poll_ui_queue)
        self.root.after(POLL_MS, self._poll_status)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_init_tab()
        self._build_params_tab()
        self._build_moving_tab()

        status = ttk.Frame(main)
        status.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(status, text="Current Position").pack(side="left")
        self.lbl_xnow = ttk.Label(status, text="X 0.0 mm", width=14)
        self.lbl_xnow.pack(side="left", padx=(8, 2))
        self.lbl_ynow = ttk.Label(status, text="Y 0.0 mm", width=14)
        self.lbl_ynow.pack(side="left", padx=2)
        self.lbl_error = ttk.Label(status, text="", foreground="red")
        self.lbl_error.pack(side="left", padx=12)
        self.lbl_message = ttk.Label(status, text="Initializing",
                                     font=("", 11, "bold"))
        self.lbl_message.pack(side="left", padx=12)

    def _build_init_tab(self) -> None:
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Init")
        self.lbl_wait = ttk.Label(page, text="Please wait",
                                  font=("", 20))
        self.lbl_wait.pack(pady=(30, 10))

        row = ttk.Frame(page)
        row.pack(fill="x", padx=12)
        ttk.Label(row, text="COM port").pack(side="left")
        self.cmb_com = ttk.Combobox(row, width=16, state="readonly")
        self.cmb_com.pack(side="left", padx=4)
        if self.settings.arduino.com:
            self.cmb_com.set(self.settings.arduino.com)
        ttk.Button(row, text="Discover", command=self._discover).pack(
            side="left", padx=4)
        self.btn_connect = ttk.Button(row, text="Connect",
                                      command=self._connect)
        self.btn_connect.pack(side="left", padx=4)
        self.btn_disconnect = ttk.Button(page, text="Disconnect",
                                         command=self._disconnect,
                                         state="disabled")
        self.btn_disconnect.pack(pady=4)

        self.lbl_devinfo = ttk.Label(page, text="", justify="left")
        self.lbl_devinfo.pack(pady=8)
        self.var_home_startup = tk.BooleanVar(
            value=self.settings.homing_on_startup)
        ttk.Checkbutton(page, text="Homing on startup",
                        variable=self.var_home_startup).pack(anchor="w",
                                                             padx=12)

    def _build_params_tab(self) -> None:
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Params")
        left = ttk.LabelFrame(page, text="Contour Limits, mm")
        left.pack(side="left", fill="y", padx=8, pady=8)

        self.ent = {}
        grid = [
            ("Shift", "shift", 0), ("Width", "width", 1),
            ("Lift", "lift", 2), ("Height", "height", 3),
            ("R step", "r_step", 4), ("Oval, %", "oval", 5),
        ]
        for label, key, r in grid:
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="e",
                                             padx=4, pady=3)
            ent = ttk.Entry(left, width=10)
            ent.grid(row=r, column=1, padx=4, pady=3)
            self.ent[key] = ent
        ttk.Label(left, text="Pattern").grid(row=6, column=0, sticky="e",
                                             padx=4, pady=3)
        self.cmb_pattern = ttk.Combobox(left, values=PATTERN_ITEMS,
                                        state="readonly", width=12)
        self.cmb_pattern.current(int(
            self.settings.defaults_contour.pattern))
        self.cmb_pattern.grid(row=6, column=1, padx=4, pady=3)

        right = ttk.LabelFrame(page, text="Motion")
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ttk.Label(right, text="Speed, mm/s").grid(row=0, column=0,
                                                  sticky="e", padx=4,
                                                  pady=3)
        self.ent_speed = ttk.Entry(right, width=10)
        self.ent_speed.insert(0, str(self.settings.defaults_speed))
        self.ent_speed.grid(row=0, column=1, padx=4, pady=3)
        ttk.Label(right, text="Start point").grid(row=1, column=0,
                                                  sticky="e", padx=4)
        self.lbl_start = ttk.Label(right, text="(set by GO!/Go Initial)")
        self.lbl_start.grid(row=1, column=1, sticky="w", padx=4)
        self.btn_go_initial = ttk.Button(
            right, text="Go Initial!\n(move to start point)",
            command=self._go_initial)
        self.btn_go_initial.grid(row=2, column=0, padx=4, pady=6)
        self.btn_start = ttk.Button(right, text="GO!", command=self._start)
        self.btn_start.grid(row=2, column=1, padx=4, pady=6)
        self.btn_stop = ttk.Button(right, text="Stop", command=self._stop)
        self.btn_stop.grid(row=3, column=0, padx=4, pady=6)

        self.canvas_preview = tk.Canvas(right, width=460, height=300,
                                        bg="white")
        self.canvas_preview.grid(row=4, column=0, columnspan=2,
                                 padx=4, pady=8)
        self._load_defaults_into_entries()
        self.cmb_pattern.bind("<<ComboboxSelected>>",
                              lambda _e: self._draw_preview())

    def _build_moving_tab(self) -> None:
        page = ttk.Frame(self.notebook)
        self.notebook.add(page, text="Moving")
        box = ttk.Frame(page)
        box.pack(pady=10)
        self.btn_pause = ttk.Button(box, text="Pause",
                                    command=self._pause_resume,
                                    state="disabled")
        self.btn_pause.grid(row=0, column=0, padx=6)
        self.btn_changepath = ttk.Button(
            box, text="Change path", command=self._change_path,
            state="disabled")
        self.btn_changepath.grid(row=0, column=1, padx=6)
        self.btn_stop2 = ttk.Button(box, text="Stop", command=self._stop,
                                    state="disabled")
        self.btn_stop2.grid(row=0, column=2, padx=6)

        goto = ttk.LabelFrame(page, text="Go to position, mm")
        goto.pack(pady=6)
        ttk.Label(goto, text="X").grid(row=0, column=0, padx=4)
        self.ent_gx = ttk.Entry(goto, width=8)
        self.ent_gx.grid(row=0, column=1, padx=4)
        ttk.Label(goto, text="Y").grid(row=0, column=2, padx=4)
        self.ent_gy = ttk.Entry(goto, width=8)
        self.ent_gy.grid(row=0, column=3, padx=4)
        ttk.Button(goto, text="Go", command=self._go_to).grid(
            row=0, column=4, padx=6)

        self.canvas_trace = tk.Canvas(page, width=820, height=320,
                                      bg="white")
        self.canvas_trace.pack(padx=8, pady=8, fill="both", expand=True)

    # ------------------------------------------------------------- helpers
    def _to_ui(self, fn, *args):
        self.root.after(0, fn, *args)

    def _submit(self, fn, on_done=None, on_error=None, *args, **kwargs):
        def done(result):
            if on_done:
                self._to_ui(on_done, result)

        def fail(exc):
            self._to_ui(self._show_error, exc)
            if on_error:
                self._to_ui(on_error, exc)

        self.ctl.submit(fn, *args, on_done=done, on_error=fail, **kwargs)

    def _show_error(self, exc: Exception) -> None:
        self.lbl_error.config(text=f"Error: {exc}")
        self.set_message("Error")

    def _clear_error(self) -> None:
        self.lbl_error.config(text="")

    def set_message(self, text: str) -> None:
        self.lbl_message.config(text=text)

    def _entries_of_contour(self) -> ContourParams:
        def get(key, default):
            try:
                return float(self.ent[key].get())
            except (ValueError, tk.TclError):
                return default
        c = ContourParams(
            shift=get("shift", self.settings.defaults_contour.shift),
            width=get("width", self.settings.defaults_contour.width),
            lift=get("lift", self.settings.defaults_contour.lift),
            height=get("height", self.settings.defaults_contour.height),
            r_step=get("r_step", self.settings.defaults_contour.r_step),
            oval=get("oval", self.settings.defaults_contour.oval),
            pattern=UI_TO_ENUM[self.cmb_pattern.get()])
        return c

    def _effective_speed(self) -> float:
        try:
            return float(self.ent_speed.get())
        except ValueError:
            return self.settings.defaults_speed

    def _load_defaults_into_entries(self) -> None:
        c = self.settings.defaults_contour
        vals = {"shift": c.shift, "width": c.width, "lift": c.lift,
                "height": c.height, "r_step": c.r_step, "oval": c.oval}
        for key, val in vals.items():
            self.ent[key].delete(0, "end")
            self.ent[key].insert(0, f"{val:g}")

    # ------------------------------------------------------------ actions
    def _discover(self) -> None:
        self._clear_error()
        self.set_message("Discovering...")

        def work():
            return self.ctl.discover()

        def done(devices):
            names = []
            for d in devices:
                name = str(d.get("com") or d.get("port") or "?")
                online = d.get("online", True)
                names.append(name + ("" if online else " (offline)"))
            self.cmb_com["values"] = names
            self.set_message(f"Found {len(names)} device(s)" if names
                             else "ComPortService not found")

        self._submit(work, on_done=done,
                     on_error=lambda _e: self.set_message(
                         "Discovery failed (service running?)"))

    def _connect(self) -> None:
        self._clear_error()
        com = self.cmb_com.get().replace(" (offline)", "").strip()
        if not com:
            messagebox.showinfo("Connect", "Select a COM port first")
            return
        self.set_message("Connecting...")
        self.btn_connect.config(state="disabled")

        def work():
            self.ctl.connect(com_name=com)
            return self.ctl.read_identity()

        def done(info):
            gx, gy = info["group"][1], info["group"][2]
            self.lbl_wait.config(text="Connected")
            self.lbl_devinfo.config(text=(
                f"Sketch v{info['sketch_ver']}, board {info['board_ver']}\n"
                f"TSH group slot {info['group'][0]}: "
                f"channels X={gx}, Y={gy}"))
            self.set_message("Ready")
            for b in (self.btn_disconnect, self.btn_go_initial,
                      self.btn_start, self.btn_stop):
                b.config(state="normal")
            if self.var_home_startup.get():
                self._home()

        self._submit(work, on_done=done)

    def _disconnect(self) -> None:
        self._submit(self.ctl.disconnect)
        self.set_message("Disconnected")
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")

    def _home(self) -> None:
        self.set_message("Homing")

        def done(_r):
            self.set_message("Finished homing")

        self._submit(self.ctl.home, on_done=done)

    def _go_initial(self) -> None:
        c = self._entries_of_contour()

        def done(_r):
            self.set_message("Moving to start position")

        self._submit(self.ctl.go_initial, c.shift, c.lift, on_done=done)

    def _start(self) -> None:
        self._clear_error()
        contour = self._entries_of_contour()
        args = convert_motion_params(contour, self._effective_speed(),
                                     self.settings.limits.speed)
        self._pattern_args = args
        self.lbl_start.config(
            text=f"({args.x0:g}, {args.y0:g}) - ({args.x1:g}, {args.y1:g})")
        self._draw_preview(args)
        self._trace.clear()

        def done(_r):
            self.set_message("Moving")
            self._paused = False
            self.btn_pause.config(text="Pause", state="normal")
            for b in (self.btn_changepath, self.btn_stop2):
                b.config(state="normal")

        self._submit(self.ctl.start_pattern, args, on_done=done)

    def _pause_resume(self) -> None:
        if not self._paused:
            # firmware has no pause: stop now, resume restarts the
            # pattern from (x0, y0) - same as the original engine
            self._submit(self.ctl.stop)
            self._paused = True
            self.btn_pause.config(text="Resume")
            self.set_message("Paused")
        else:
            self._paused = False
            self.btn_pause.config(text="Pause")
            if self._pattern_args is not None:
                self._submit(self.ctl.start_pattern, self._pattern_args)
            self.set_message("Moving")

    def _change_path(self) -> None:
        self._submit(self.ctl.stop)
        self.set_message("Change path - edit Params, then GO!")
        self.notebook.select(1)

    def _stop(self) -> None:
        self._submit(self.ctl.stop)

        def done(_r):
            self.set_message("Ready")
            self._paused = False
            self.btn_pause.config(text="Pause")

        self._submit(lambda: None, on_done=done)

    def _go_to(self) -> None:
        try:
            x = float(self.ent_gx.get())
            y = float(self.ent_gy.get())
        except ValueError:
            return
        self._submit(self.ctl.go_initial, x, y)

    # ------------------------------------------------------------- polling
    def _poll_ui_queue(self) -> None:
        self.root.after(POLL_MS, self._poll_ui_queue)

    def _poll_status(self) -> None:
        if self.ctl.connected:
            def work():
                return self.ctl.status()

            def done(st):
                self.lbl_xnow.config(text=f"X {st.x:.1f} mm")
                self.lbl_ynow.config(text=f"Y {st.y:.1f} mm")
                self._trace.append((st.x, st.y))
                if len(self._trace) > 2000:
                    self._trace = self._trace[-1000:]
                self._draw_trace()

            self._submit(work, on_done=done,
                         on_error=lambda _e: None)
        self.root.after(POLL_MS, self._poll_status)

    # ------------------------------------------------------------- drawing
    def _world_to_canvas(self, canvas, x, y, w0=-15, w1=15, h0=-15, h1=15):
        W, H = canvas.winfo_width(), canvas.winfo_height()
        px = int((x - w0) / (w1 - w0) * (W - 40)) + 20
        py = H - 20 - int((y - h0) / (h1 - h0) * (H - 40))
        return px, py

    def _draw_preview(self, args=None) -> None:
        cv = self.canvas_preview
        cv.delete("all")
        c = self._entries_of_contour()
        if args is None:
            from .patterns import convert_motion_params as _cmp
            args = _cmp(c, self._effective_speed(),
                        self.settings.limits.speed)
        x0, x1, y0, y1 = args.x0, args.x1, args.y0, args.y1
        p1 = self._world_to_canvas(cv, x0, y0)
        p2 = self._world_to_canvas(cv, x1, y1)
        cv.create_rectangle(min(p1[0], p2[0]), min(p1[1], p2[1]),
                            max(p1[0], p2[0]), max(p1[1], p2[1]),
                            outline="#36c")
        if args.mode == 1:  # raster: draw the line pitch
            step = max(args.step_y, 1e-6)
            yy = y0
            while yy <= y1:
                a = self._world_to_canvas(cv, x0, yy)
                b = self._world_to_canvas(cv, x1, yy)
                cv.create_line(a[0], a[1], b[0], b[1], fill="#9bc")
                yy += step
        cv.create_oval(*self._world_to_canvas(cv, x0, y0), 4, 4,
                       fill="red", outline="")

    def _draw_trace(self) -> None:
        cv = self.canvas_trace
        if not self._trace:
            return
        xs = [p[0] for p in self._trace]
        ys = [p[1] for p in self._trace]
        w0, w1 = min(xs) - 1, max(xs) + 1
        h0, h1 = min(ys) - 1, max(ys) + 1
        if len(self._trace) == 1 or (w1 - w0) < 1e-9 and (h1 - h0) < 1e-9:
            return
        pts = [self._world_to_canvas(cv, x, y, w0, w1, h0, h1)
               for x, y in self._trace[::3]]
        if len(pts) >= 2:
            cv.delete("all")
            cv.create_line(*[c for p in pts for c in p],
                           fill="#36c", smooth=False)
            last = pts[-1]
            cv.create_oval(last[0] - 3, last[1] - 3, last[0] + 3,
                           last[1] + 3, fill="red", outline="")

    # ----------------------------------------------------------------- run
    def run(self) -> int:
        try:
            self.root.mainloop()
        finally:
            self.ctl.disconnect()
        return 0


def run_app(settings: Settings) -> int:
    return MocoApp(settings).run()
