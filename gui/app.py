"""System-tray GUI for managing the proxy."""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime

import pystray
from PIL import Image, ImageDraw

from proxy.config import (
    CONFIG_PATH, load_config, save_config, get_active_model_config,
    is_autostart_enabled, set_autostart, is_already_running,
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_MUTED,
    ACCENT, GREEN, RED, FONT, FONT_MONO, LOG_QUEUE,
)
from proxy.server import ProxyServer
from proxy.handler import ProxyHandler


class ProxyManagerApp:
    def __init__(self):
        self.proxy = ProxyServer(ProxyHandler)
        self.cfg = load_config()
        self.tray = None
        self.window = None
        self.log_lines = []

        self._build_window()
        self._build_tray()

        # Start Flask REST API for frontend (port 15801)
        from api_server import set_proxy_instance
        set_proxy_instance(self.proxy)
        self._start_api_server()

        port = self.cfg.get("port", 15800)
        try:
            self.proxy.start(port)
            self._update_status(True)
        except Exception:
            self._update_status(False)

        self._poll_logs()
        self.window.protocol("WM_DELETE_WINDOW", self._hide_window)

    def _start_api_server(self):
        try:
            from api_server import app as flask_app
            def _run():
                flask_app.run(host="127.0.0.1", port=15801, debug=False,
                             use_reloader=False)
            t = threading.Thread(target=_run, daemon=True)
            t.start()
        except Exception:
            pass  # API server is optional

    def _build_window(self):
        self.window = tk.Tk()
        self.window.title("AI Proxy Manager")
        self.window.geometry("560x640")
        self.window.resizable(False, True)
        self.window.configure(bg=BG_DARK)
        self.window.minsize(520, 400)

        self._setup_icon()
        self._setup_styles()
        self._build_header()
        self._build_tab_bar()

    def _setup_icon(self):
        try:
            ico_path = os.path.join(os.path.dirname(CONFIG_PATH),
                                    "proxy_icon.ico")
            icon_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            icon_draw = ImageDraw.Draw(icon_img)
            icon_draw.ellipse([6, 6, 58, 58], fill=ACCENT)
            icon_draw.ellipse([18, 18, 46, 46], fill="#ffffff")
            icon_img.save(ico_path, format="ICO", sizes=[(64, 64)])
            self.window.iconbitmap(ico_path)
        except Exception:
            pass

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG_DARK, foreground=FG_PRIMARY,
                        font=(FONT, 10), borderwidth=0,
                        troughcolor=BG_INPUT, fieldbackground=BG_INPUT,
                        insertcolor=FG_PRIMARY)
        style.map(".", foreground=[("disabled", FG_MUTED)])
        style.configure("TFrame", background=BG_DARK)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_DARK, foreground=FG_PRIMARY,
                        font=(FONT, 10))
        style.configure("Card.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 10))
        style.configure("CardSec.TLabel", background=BG_CARD,
                        foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("CardTitle.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 11, "bold"))
        style.configure("TButton", background=ACCENT, foreground="#ffffff",
                        font=(FONT, 10), padding=(10, 5), borderwidth=0)
        style.map("TButton", background=[("active", "#5a9ee6"),
                                         ("pressed", "#3a7bc8")],
                  foreground=[("disabled", FG_MUTED)])
        style.configure("Stop.TButton", background=RED,
                        foreground="#ffffff")
        style.map("Stop.TButton", background=[("active", "#f5a0b5"),
                                              ("pressed", "#e0708a")])
        style.configure("TEntry", fieldbackground=BG_INPUT,
                        foreground=FG_PRIMARY, insertcolor=FG_PRIMARY,
                        borderwidth=1, padding=6)
        style.map("TEntry", fieldbackground=[("focus", "#d8e8f8")])
        style.configure("Active.TLabel", foreground=GREEN,
                        font=(FONT, 10, "bold"))
        style.configure("Inactive.TButton", background=BG_INPUT,
                        foreground=FG_SECONDARY, font=(FONT, 9),
                        padding=(8, 4), borderwidth=0)
        style.map("Inactive.TButton",
                  background=[("active", ACCENT)],
                  foreground=[("active", "#ffffff")])
        style.configure("ModelName.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 12, "bold"))
        style.configure("ModelUrl.TLabel", background=BG_CARD,
                        foreground=ACCENT, font=(FONT, 9))
        style.configure("ModelId.TLabel", background=BG_CARD,
                        foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("Tab.TButton", background=BG_DARK,
                        foreground=FG_SECONDARY, font=(FONT, 10),
                        padding=(12, 6), borderwidth=0)
        style.map("Tab.TButton", background=[("active", BG_CARD)],
                  foreground=[("active", FG_PRIMARY)])
        style.configure("TabSel.TButton", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 10, "bold"),
                        padding=(12, 6), borderwidth=0)
        style.configure("Icon.TButton", background=BG_CARD,
                        foreground=FG_SECONDARY, font=(FONT, 8),
                        padding=(4, 2), borderwidth=0)
        style.map("Icon.TButton",
                  background=[("active", "#e8e8ed")],
                  foreground=[("active", FG_PRIMARY)])
        style.configure("ToggleOn.TButton", background=GREEN,
                        foreground="#ffffff", font=(FONT, 9),
                        padding=(8, 4), borderwidth=0)
        style.configure("ToggleOff.TButton", background=BG_INPUT,
                        foreground=FG_SECONDARY, font=(FONT, 9),
                        padding=(8, 4), borderwidth=0)

    def _build_header(self):
        header = ttk.Frame(self.window, style="Card.TFrame", padding=16)
        header.pack(fill=tk.X, padx=16, pady=(16, 0))

        left = ttk.Frame(header, style="Card.TFrame")
        left.pack(side=tk.LEFT)

        ttk.Label(left, text="AI Proxy Manager",
                  style="CardTitle.TLabel").pack(anchor=tk.W)
        self.status_lbl = ttk.Label(left, text="● 运行中",
                                     style="Active.TLabel")
        self.status_lbl.pack(anchor=tk.W, pady=(4, 0))

        right = ttk.Frame(header, style="Card.TFrame")
        right.pack(side=tk.RIGHT)

        self.toggle_btn = ttk.Button(right, text="停止",
                                     command=self._toggle)
        self.toggle_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        ttk.Checkbutton(right, text="开机启动", variable=self.autostart_var,
                        command=self._toggle_autostart).pack(side=tk.RIGHT, padx=(12, 0))

    def _toggle(self):
        if self.proxy.is_running():
            self.proxy.stop()
            self._update_status(False)
        else:
            try:
                self.proxy.start(self.cfg.get("port", 15800))
                self._update_status(True)
            except Exception as e:
                messagebox.showerror("错误", f"启动失败: {e}")

    def _update_status(self, running):
        if running:
            self.status_lbl.config(text="● 运行中", style="Active.TLabel")
            self.toggle_btn.config(text="停止", style="Stop.TButton")
        else:
            self.status_lbl.config(text="● 已停止", foreground=RED)
            self.toggle_btn.config(text="启动", style="TButton")
    def _build_tab_bar(self):
        tab_frame = ttk.Frame(self.window, style="TFrame")
        tab_frame.pack(fill=tk.X, padx=16, pady=(12, 0))

        self._tab_buttons = []
        self._tab_frames = []

        tabs = [("模型", self._build_models_tab),
                ("日志", self._build_logs_tab),
                ("设置", self._build_settings_tab)]

        for i, (name, builder) in enumerate(tabs):
            btn = ttk.Button(tab_frame, text=name, style="Tab.TButton",
                            command=lambda idx=i: self._switch_tab(idx))
            btn.pack(side=tk.LEFT, padx=(0, 4))
            self._tab_buttons.append(btn)

            frame = ttk.Frame(self.window, style="TFrame")
            frame.place(x=0, y=0, relwidth=1, relheight=1)
            builder(frame)
            self._tab_frames.append(frame)

        self._switch_tab(0)

    def _switch_tab(self, idx):
        for i, btn in enumerate(self._tab_buttons):
            if i == idx:
                btn.config(style="TabSel.TButton")
                self._tab_frames[i].place(x=0, y=150, relwidth=1, relheight=1)
                self._tab_frames[i].lift()
            else:
                btn.config(style="Tab.TButton")
                self._tab_frames[i].place_forget()

    def _build_models_tab(self, parent):
        # Add model button
        btn_frame = ttk.Frame(parent, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=16, pady=(8, 8))
        ttk.Button(btn_frame, text="+ 添加模型", command=self._add_model_dialog).pack(side=tk.LEFT)

        # Scrollable container without visible scrollbar
        self.models_canvas = tk.Canvas(parent, bg=BG_DARK, highlightthickness=0)
        self.models_container = tk.Frame(self.models_canvas, bg=BG_DARK)

        self.models_container.bind(
            "<Configure>",
            lambda e: self.models_canvas.configure(scrollregion=self.models_canvas.bbox("all")))

        self.models_canvas.create_window((0, 0), window=self.models_container, anchor="nw", width=520)
        self.models_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0), pady=(0, 12))

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            self.models_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.models_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._refresh_models_list()

    def _build_model_card(self, parent, model, idx):
        """Build a single model card matching reference image style."""
        enabled = model.get("enabled", False)
        base_url = model.get("base_url", "")
        name = model.get("name", model["id"])

        # Card frame with rounded corners effect (using padding and bg)
        card = tk.Frame(parent, bg="white", bd=0)
        card.pack(fill=tk.X, pady=(0, 10))

        # Inner padding frame
        inner = tk.Frame(card, bg="white", padx=16, pady=14)
        inner.pack(fill=tk.X)

        # Left: avatar + info
        left = tk.Frame(inner, bg="white")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Avatar - colored square with letter
        avatar_frame = tk.Frame(left, bg="white")
        avatar_frame.pack(side=tk.LEFT, padx=(0, 12))

        first_letter = name[0].upper() if name else "?"
        # Generate consistent color from name
        colors = ["#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6", "#1ABC9C", "#E67E22", "#34495E"]
        color_idx = sum(ord(c) for c in model["id"]) % len(colors)
        avatar_color = colors[color_idx]

        avatar = tk.Label(avatar_frame, text=first_letter,
                         bg=avatar_color, fg="white",
                         font=(FONT, 13, "bold"),
                         width=2, height=1)
        avatar.pack()

        # Info
        info = tk.Frame(left, bg="white")
        info.pack(side=tk.LEFT, fill=tk.Y)

        name_lbl = tk.Label(info, text=name,
                           bg="white", fg=FG_PRIMARY,
                           font=(FONT, 12, "bold"))
        name_lbl.pack(anchor=tk.W)

        url_lbl = tk.Label(info, text=base_url,
                          bg="white", fg=ACCENT,
                          font=(FONT, 9))
        url_lbl.pack(anchor=tk.W, pady=(3, 0))

        # Right: action buttons
        right = tk.Frame(inner, bg="white")
        right.pack(side=tk.RIGHT)

        # Enable/Disable toggle button
        if enabled:
            toggle_btn = tk.Label(right, text="启用",
                                 bg=GREEN, fg="white",
                                 font=(FONT, 9),
                                 padx=14, pady=5)
        else:
            toggle_btn = tk.Label(right, text="启用",
                                 bg="#e8e8ed", fg=FG_SECONDARY,
                                 font=(FONT, 9),
                                 padx=14, pady=5)
        toggle_btn.pack(side=tk.LEFT, padx=(0, 8))
        toggle_btn.bind("<Button-1>", lambda e, i=idx: self._toggle_model(i))
        toggle_btn.config(cursor="hand2")

        # Edit button - pencil icon
        edit_btn = tk.Label(right, text="✎",
                           bg="white", fg=FG_SECONDARY,
                           font=(FONT, 12),
                           padx=6, pady=5)
        edit_btn.pack(side=tk.LEFT, padx=(0, 8))
        edit_btn.bind("<Button-1>", lambda e, i=idx: self._edit_model_dialog(i))
        edit_btn.config(cursor="hand2")

        # Delete button - trash icon
        del_btn = tk.Label(right, text="🗑",
                          bg="white", fg="#c0c0c0",
                          font=(FONT, 12),
                          padx=6, pady=5)
        del_btn.pack(side=tk.LEFT)
        del_btn.bind("<Button-1>", lambda e, i=idx: self._delete_model(i))
        del_btn.config(cursor="hand2")

        # Hover effects for icons
        def on_enter(e, widget, color):
            widget.config(bg="#f5f5f5")
        def on_leave(e, widget):
            widget.config(bg="white")

        for btn in [edit_btn, del_btn]:
            btn.bind("<Enter>", lambda e, b=btn: on_enter(e, b, "#f5f5f5"))
            btn.bind("<Leave>", lambda e, b=btn: on_leave(e, b))

    def _refresh_models_list(self):
        for w in self.models_container.winfo_children():
            w.destroy()
        models = self.cfg.get("models", [])
        for i, m in enumerate(models):
            self._build_model_card(self.models_container, m, i)

    def _toggle_model(self, idx):
        models = self.cfg.get("models", [])
        for i, m in enumerate(models):
            m["enabled"] = (i == idx)
        self.cfg["models"] = models
        save_config(self.cfg)
        self._refresh_models_list()

    def _delete_model(self, idx):
        if messagebox.askyesno("确认删除", "确定要删除这个模型吗？"):
            models = self.cfg.get("models", [])
            if 0 <= idx < len(models):
                models.pop(idx)
                if models and not any(m.get("enabled", False) for m in models):
                    models[0]["enabled"] = True
                self.cfg["models"] = models
                save_config(self.cfg)
                self._refresh_models_list()

    def _add_model_dialog(self):
        self._model_dialog(None)

    def _edit_model_dialog(self, idx):
        models = self.cfg.get("models", [])
        if 0 <= idx < len(models):
            self._model_dialog(idx, models[idx])

    def _model_dialog(self, idx, model=None):
        dlg = tk.Toplevel(self.window)
        dlg.title("编辑模型" if model else "添加模型")
        dlg.geometry("400x340")
        dlg.configure(bg=BG_DARK)
        dlg.transient(self.window)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Card container
        card = tk.Frame(dlg, bg="white", bd=0)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        inner = tk.Frame(card, bg="white")
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # Title
        tk.Label(inner, text="编辑模型" if model else "添加模型",
                bg="white", fg=FG_PRIMARY,
                font=(FONT, 14, "bold")).pack(anchor=tk.W, pady=(0, 16))

        # Form fields
        fields = [
            ("模型 ID", "id", model.get("id", "") if model else ""),
            ("显示名称", "name", model.get("name", "") if model else ""),
            ("API 地址", "base_url", model.get("base_url", "https://api.deepseek.com") if model else "https://api.deepseek.com"),
            ("API Key", "api_key", model.get("api_key", "") if model else ""),
        ]

        vars_map = {}
        for label, key, val in fields:
            row = tk.Frame(inner, bg="white")
            row.pack(fill=tk.X, pady=(0, 10))

            tk.Label(row, text=label, bg="white", fg=FG_SECONDARY,
                    font=(FONT, 10)).pack(anchor=tk.W)

            var = tk.StringVar(value=val)
            vars_map[key] = var

            if key == "api_key":
                entry = tk.Entry(row, textvariable=var, width=40,
                               bg="#f8f8f8", fg=FG_PRIMARY,
                               insertbackground=FG_PRIMARY,
                               bd=1, relief="solid", show="*")
            else:
                entry = tk.Entry(row, textvariable=var, width=40,
                               bg="#f8f8f8", fg=FG_PRIMARY,
                               insertbackground=FG_PRIMARY,
                               bd=1, relief="solid")
            entry.pack(fill=tk.X, pady=(4, 0))

        # Show key checkbox
        show_var = tk.BooleanVar(value=False)
        show_cb = tk.Checkbutton(inner, text="显示 API Key", variable=show_var,
                                bg="white", fg=FG_SECONDARY,
                                selectcolor="white",
                                activebackground="white", activeforeground=FG_SECONDARY)

        def toggle_show():
            show = show_var.get()
            for w in inner.winfo_children():
                for c in w.winfo_children():
                    if isinstance(c, tk.Entry) and c.cget("show") in ("*", ""):
                        c.config(show="" if show else "*")
        show_cb.config(command=toggle_show)
        show_cb.pack(anchor=tk.W, pady=(4, 0))

        # Buttons
        btn_row = tk.Frame(inner, bg="white")
        btn_row.pack(fill=tk.X, pady=(20, 0))

        def _save():
            mid = vars_map["id"].get().strip()
            if not mid:
                messagebox.showwarning("提示", "模型 ID 不能为空")
                return

            new_model = {
                "id": mid,
                "name": vars_map["name"].get().strip() or mid,
                "base_url": vars_map["base_url"].get().strip().rstrip("/"),
                "api_key": vars_map["api_key"].get().strip(),
                "enabled": False,
            }

            models = self.cfg.get("models", [])
            if idx is not None and 0 <= idx < len(models):
                new_model["enabled"] = models[idx].get("enabled", False)
                models[idx] = new_model
            else:
                models.append(new_model)
                if len(models) == 1:
                    models[0]["enabled"] = True

            self.cfg["models"] = models
            save_config(self.cfg)
            self._refresh_models_list()
            dlg.destroy()

        tk.Button(btn_row, text="取消", bg="#f0f0f0", fg=FG_SECONDARY,
                 font=(FONT, 10), padx=20, pady=6, bd=0,
                 cursor="hand2", command=dlg.destroy).pack(side=tk.RIGHT)

        tk.Button(btn_row, text="保存", bg=ACCENT, fg="white",
                 font=(FONT, 10), padx=20, pady=6, bd=0,
                 cursor="hand2", command=_save).pack(side=tk.RIGHT, padx=(0, 8))

    def _build_logs_tab(self, parent):
        self.log_text = scrolledtext.ScrolledText(
            parent, state=tk.DISABLED, wrap=tk.WORD,
            bg="white", fg=FG_PRIMARY, font=(FONT_MONO, 9),
            insertbackground=FG_PRIMARY, bd=0,
            padx=12, pady=12)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 8))

        btn_frame = ttk.Frame(parent, style="TFrame")
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        ttk.Button(btn_frame, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT)

    def _build_settings_tab(self, parent):
        card = tk.Frame(parent, bg="white", bd=0)
        card.pack(fill=tk.X, padx=16, pady=(8, 8))

        inner = tk.Frame(card, bg="white", padx=16, pady=16)
        inner.pack(fill=tk.X)

        tk.Label(inner, text="代理设置", bg="white", fg=FG_PRIMARY,
                font=(FONT, 14, "bold")).pack(anchor=tk.W, pady=(0, 16))

        row1 = tk.Frame(inner, bg="white")
        row1.pack(fill=tk.X, pady=(0, 12))
        tk.Label(row1, text="代理端口", bg="white", fg=FG_SECONDARY,
                font=(FONT, 10), width=12).pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value=str(self.cfg.get("port", 15800)))
        tk.Entry(row1, textvariable=self.port_var, width=20,
                bg="#f8f8f8", fg=FG_PRIMARY,
                insertbackground=FG_PRIMARY, bd=1, relief="solid").pack(side=tk.LEFT)

        btn_row = tk.Frame(inner, bg="white")
        btn_row.pack(fill=tk.X, pady=(8, 0))
        tk.Button(btn_row, text="保存设置", bg=ACCENT, fg="white",
                 font=(FONT, 10), padx=16, pady=6, bd=0,
                 cursor="hand2", command=self._save_settings).pack(side=tk.RIGHT)

    def _save_settings(self):
        try:
            port = int(self.port_var.get())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "端口必须是 1-65535 的整数")
            return

        self.cfg["port"] = port
        save_config(self.cfg)
        messagebox.showinfo("已保存", "设置已保存！\n重启代理以应用新端口。")

    def _clear_log(self):
        self.log_lines = []
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_logs(self):
        while not LOG_QUEUE.empty():
            try:
                msg = LOG_QUEUE.get_nowait()
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_lines.append("[{0}] {1}".format(ts, msg))
            except queue.Empty:
                break
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", "\n".join(self.log_lines))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.window.after(1000, self._poll_logs)

    def _build_tray(self):
        menu = (
            pystray.MenuItem("显示", self._show_window),
            pystray.MenuItem("退出", self._quit),
        )
        icon_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        icon_draw = ImageDraw.Draw(icon_img)
        icon_draw.ellipse([6, 6, 58, 58], fill=ACCENT)
        icon_draw.ellipse([18, 18, 46, 46], fill="#ffffff")
        self.tray = pystray.Icon("deepseek_proxy", icon_img,
                                  "AI Proxy Manager", menu)

    def _show_window(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _hide_window(self):
        self.window.withdraw()

    def _quit(self):
        if self.proxy.is_running():
            self.proxy.stop()
        if self.tray:
            self.tray.stop()
        self.window.destroy()

    def _toggle_autostart(self):
        set_autostart(self.autostart_var.get())

    def run(self):
        if self.tray:
            threading.Thread(target=self.tray.run, daemon=True).start()
        self.window.mainloop()
