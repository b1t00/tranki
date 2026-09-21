import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class SettingsWindow:
    MAX_RECENT_DECKS = 50

    def __init__(self, app):
        self.app = app
        self.window = None

    def show(self):
        if self.window and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()
            return

        self.window = tk.Toplevel(self.app.root)
        self.window.title("Settings")
        self.window.geometry("560x720")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.deck_name_var = tk.StringVar(value=self.app.deck_name)
        self.selected_deck_path_var = tk.StringVar(value="")
        self.ai_api_key_var = tk.StringVar(value=self.app.ai_api_key)
        self._build_widgets()

    def close(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None

    def _build_widgets(self):
        window = self.window
        tk.Label(window, text="Deck Name:").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        deck_name_entry = ttk.Entry(
            window, textvariable=self.deck_name_var, width=30
        )
        deck_name_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        browse_btn = ttk.Button(
            window, text="📁 Browse", command=self.browse_decks, width=10
        )
        browse_btn.grid(row=0, column=2, padx=5, pady=10)

        tk.Label(window, text="Recently used:").grid(
            row=1, column=0, padx=10, pady=(0, 5), sticky="nw"
        )
        recent_container = ttk.Frame(window)
        recent_container.grid(
            row=2, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="nsew"
        )

        columns = ("name", "path")
        self.recent_tree = ttk.Treeview(
            recent_container, columns=columns, show="headings", height=9
        )
        self.recent_tree.heading("name", text="Name")
        self.recent_tree.heading("path", text="Path")
        self.recent_tree.column("name", width=180, minwidth=120, stretch=False)
        self.recent_tree.column("path", width=320, minwidth=180, stretch=True)

        scrollbar = ttk.Scrollbar(
            recent_container, orient="vertical", command=self.recent_tree.yview
        )
        self.recent_tree.configure(yscrollcommand=scrollbar.set)
        self.recent_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        recent_container.grid_rowconfigure(0, weight=1)
        recent_container.grid_columnconfigure(0, weight=1)

        for entry in self.app.recent_decks:
            self.recent_tree.insert(
                "", "end", values=(entry.get("name", ""), entry.get("path", ""))
            )
        self.recent_tree.bind("<<TreeviewSelect>>", self.select_recent_deck)
        self.recent_tree.bind("<Double-1>", self.select_recent_deck)

        tk.Label(window, text="AI API-Key:").grid(
            row=3, column=0, padx=10, pady=(10, 5), sticky="w"
        )
        ai_api_key_entry = ttk.Entry(
            window, textvariable=self.ai_api_key_var, width=30, show="*"
        )
        ai_api_key_entry.grid(row=3, column=1, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        tk.Label(window, text="AI context:").grid(
            row=4, column=0, padx=10, pady=5, sticky="nw"
        )
        context_container = ttk.Frame(window)
        context_container.grid(
            row=4, column=1, columnspan=2, padx=10, pady=5, sticky="nsew"
        )
        self.ai_context_text = tk.Text(context_container, height=8, width=30, wrap="word")
        self.ai_context_text.insert("1.0", self.app.ai_context)
        context_scrollbar = ttk.Scrollbar(
            context_container, orient="vertical", command=self.ai_context_text.yview
        )
        self.ai_context_text.configure(yscrollcommand=context_scrollbar.set)
        self.ai_context_text.grid(row=0, column=0, sticky="nsew")
        context_scrollbar.grid(row=0, column=1, sticky="ns")
        context_container.grid_rowconfigure(0, weight=1)
        context_container.grid_columnconfigure(0, weight=1)

        tk.Label(window, text="Window:").grid(
            row=5, column=0, padx=10, pady=(10, 0), sticky="w"
        )
        size_row = ttk.Frame(window)
        size_row.grid(row=5, column=1, columnspan=2, padx=10, pady=(10, 0), sticky="w")
        self.window_width_var = tk.StringVar(value=str(self.app.window_width))
        self.window_height_var = tk.StringVar(value=str(self.app.window_height))
        self.window_x_var = tk.StringVar(value=str(self.app.window_x))
        self.window_y_var = tk.StringVar(value=str(self.app.window_y))
        for label_text, var in (
            ("Width:", self.window_width_var),
            ("Height:", self.window_height_var),
        ):
            ttk.Label(size_row, text=label_text).pack(side="left", padx=(0, 4))
            ttk.Entry(size_row, textvariable=var, width=6).pack(side="left", padx=(0, 10))

        position_row = ttk.Frame(window)
        position_row.grid(row=6, column=1, columnspan=2, padx=10, pady=(5, 0), sticky="w")
        for label_text, var in (
            ("Position X:", self.window_x_var),
            ("Position Y:", self.window_y_var),
        ):
            ttk.Label(position_row, text=label_text).pack(side="left", padx=(0, 4))
            ttk.Entry(position_row, textvariable=var, width=6).pack(side="left", padx=(0, 10))

        button_row = ttk.Frame(window)
        button_row.grid(row=7, column=0, columnspan=3, pady=20, sticky="s")
        save_btn = ttk.Button(button_row, text="Save", command=self.save)
        save_btn.pack(side="left", padx=5)
        cancel_btn = ttk.Button(button_row, text="Cancel", command=self.close)
        cancel_btn.pack(side="left", padx=5)

        window.grid_rowconfigure(2, weight=1)
        window.grid_rowconfigure(4, weight=1)
        window.grid_columnconfigure(1, weight=1)

    def browse_decks(self):
        initial_dir = (
            self.app.last_deck_directory
            if os.path.exists(self.app.last_deck_directory)
            else os.path.expanduser("~/syncth/anki")
        )
        file_path = filedialog.askopenfilename(
            title="Choose existing deck",
            initialdir=initial_dir,
            filetypes=[("Anki Deck", "*.apkg"), ("Alle Dateien", "*.*")],
        )
        if file_path:
            self.app.last_deck_directory = os.path.dirname(file_path)
            deck_name = os.path.splitext(os.path.basename(file_path))[0]
            self.deck_name_var.set(deck_name)
            self.selected_deck_path_var.set(file_path)

    def select_recent_deck(self, _event=None):
        selection = self.recent_tree.selection()
        if not selection:
            return
        values = self.recent_tree.item(selection[0], "values")
        if len(values) >= 2:
            self.deck_name_var.set(values[0])
            self.selected_deck_path_var.set(values[1])

    def save(self):
        new_deck_name = self.deck_name_var.get().strip()
        if not new_deck_name:
            messagebox.showwarning("Warning", "Deck name must not be empty.")
            return

        recent_path = self.selected_deck_path_var.get().strip()
        if not recent_path or os.path.splitext(os.path.basename(recent_path))[0] != new_deck_name:
            recent_path = os.path.join(
                self.app.last_deck_directory, f"{new_deck_name}.apkg"
            )

        self.app.recent_decks = [
            entry for entry in self.app.recent_decks
            if entry.get("name") != new_deck_name
        ]
        self.app.recent_decks.insert(
            0, {"name": new_deck_name, "path": recent_path}
        )
        self.app.recent_decks = self.app.recent_decks[: self.MAX_RECENT_DECKS]

        if new_deck_name != self.app.deck_name:
            self._switch_deck(new_deck_name)

        self.app.ai_api_key = self.ai_api_key_var.get().strip()
        self.app.ai_context = self.ai_context_text.get("1.0", tk.END).strip()
        try:
            self.app.ai_service.configure(self.app.ai_api_key)
            self.app.ai_service.set_context(self.app.ai_context)
        except Exception as e:
            messagebox.showwarning("AI configuration", f"Could not validate AI key: {e}")

        try:
            new_width = int(self.window_width_var.get().strip())
            new_height = int(self.window_height_var.get().strip())
            new_x = int(self.window_x_var.get().strip())
            new_y = int(self.window_y_var.get().strip())
        except ValueError:
            messagebox.showwarning("Warning", "Window values must be integers.")
            return
        self.app.window_width = new_width
        self.app.window_height = new_height
        self.app.window_x = new_x
        self.app.window_y = new_y
        self.app.root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")

        self._save_config()
        self.close()

    def _save_config(self):
        self.app.config["deck"] = {
            "name": self.app.deck_name,
            "last_directory": self.app.last_deck_directory,
            "recent": self.app._serialize_recent_decks(self.app.recent_decks),
        }
        self.app.config["ai"] = {
            "api_key": self.app.ai_api_key,
            "context": self.app.ai_context,
        }
        self.app.config["window"] = {
            "width": str(self.app.window_width),
            "height": str(self.app.window_height),
            "x": str(self.app.window_x),
            "y": str(self.app.window_y),
        }
        with open(self.app.config_path, "w") as config_file:
            self.app.config.write(config_file)

    def _switch_deck(self, deck_name):
        self.app.deck_name = deck_name
        self.app.anki_service.switch_deck(deck_name)
        self.app._update_window_title()
        self.app.set_status(f"New deck created: {deck_name}")
        print(
            f"Deck: {deck_name}, Deck-ID: {self.app.anki_service.deck_id}, "
            f"Model-ID: {self.app.anki_service.MODEL_ID}"
        )
