import tkinter as tk
from tkinter import ttk, messagebox
import os
import pytesseract
import configparser
import json
import sys
import threading

from ocr_service import OCRService
from speech_service import SpeechService
from translation_service import TranslationService
from anki_service import AnkiService
from ai_service import AIService, DEFAULT_AI_CONTEXT
from transcription_service import TranscriptionService
from settings_ui import SettingsWindow

APP_NAME = "translate-and-anki"
APP_VERSION = "v4.1.1"


def configure_macos_process_name():
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSProcessInfo
        NSProcessInfo.processInfo().setProcessName_(APP_NAME)
    except Exception:
        pass

# Set the Tesseract path explicitly for the .app bundle.
if os.path.exists('/opt/homebrew/bin/tesseract'):
    pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'
elif os.path.exists('/usr/local/bin/tesseract'):
    pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'


class Tooltip:
    def __init__(self, widget, text, delay=600):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.after_id = None
        self.window = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')

    def _schedule(self, _event=None):
        self._hide()
        self.after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        self.after_id = None
        if self.window or not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.attributes('-topmost', True)
        label = tk.Label(
            self.window,
            text=self.text,
            bg='#ffffe0',
            fg='#222',
            relief='solid',
            borderwidth=1,
            padx=5,
            pady=2,
        )
        label.pack()
        self.window.update_idletasks()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window.geometry(f'+{x - self.window.winfo_width() // 2}+{y}')

    def _hide(self, _event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.window:
            self.window.destroy()
            self.window = None


class TranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.createcommand("tkAboutDialog", self.show_about_dialog)
        self.root.createcommand("::tk::mac::ShowPreferences", self.show_preferences)
        try:
            self.root.tk.call("tk", "appname", APP_NAME)
        except tk.TclError:
            pass

        self.translation_service = TranslationService()
        self.speech_service = SpeechService()
        self.ocr_service = OCRService(
            tesseract_path=pytesseract.pytesseract.tesseract_cmd
        )
        self.transcription_service = TranscriptionService()
        # Load the model in the background, including its first download, instead of on the first mic click.
        self.transcription_service.preload_async(
            on_error=lambda e: self.root.after(
                0, lambda: self.set_status(f"Could not load speech model: {e}")
            )
        )

        # Only allow German and English
        self.languages = ["German", "English"]
        self.lang_codes = {"German": "de", "English": "en"}
        self._pending_recording = None  # Last mic recording if it still matches the current text.

        self.src_lang_var = tk.StringVar(value="German")
        self.dest_lang_var = tk.StringVar(value="English")
        self.auto_detect = tk.BooleanVar(value=True)
        self._r_release_after_id = None

        # Make all columns flexible.
        for i in range(6):
            self.root.grid_columnconfigure(i, weight=1)

        self._build_buttons()

        # Load the config file from the app directory.
        app_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(app_dir, 'config')
        os.makedirs(config_dir, exist_ok=True)
        self.config_path = os.path.join(config_dir, 'config.ini')
        self.config = configparser.ConfigParser()

        # Load the config or create defaults.
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
            self.deck_name = self.config.get('deck', 'name', fallback='translate-and-anki-03-debug')
            self.last_deck_directory = self.config.get('deck', 'last_directory', fallback=os.path.expanduser('~/syncth/anki'))
            last_decks_str = self.config.get('deck', 'recent', fallback='')
            self.recent_decks = self._parse_recent_decks(last_decks_str)
        else:
            self.deck_name = "translate-and-anki-03-debug"
            self.last_deck_directory = os.path.expanduser('~/syncth/anki')
            self.recent_decks = [{
                'name': self.deck_name,
                'path': os.path.join(self.last_deck_directory, f"{self.deck_name}.apkg")
            }]
            self.config['deck'] = {
                'name': self.deck_name,
                'last_directory': self.last_deck_directory,
                'recent': self._serialize_recent_decks(self.recent_decks)
            }
            with open(self.config_path, 'w') as f:
                self.config.write(f)

        if not self.recent_decks:
            self.recent_decks = [{
                'name': self.deck_name,
                'path': os.path.join(self.last_deck_directory, f"{self.deck_name}.apkg")
            }]

        self.ai_api_key = self.config.get('ai', 'api_key', fallback='')
        self.ai_context = self.config.get('ai', 'context', fallback='').strip() or DEFAULT_AI_CONTEXT
        self.ai_service = AIService(self.ai_api_key, self.ai_context)

        self.window_width = self.config.getint('window', 'width', fallback=393)
        self.window_height = self.config.getint('window', 'height', fallback=241)
        self.window_x = self.config.getint('window', 'x', fallback=200)
        self.window_y = self.config.getint('window', 'y', fallback=200)

        self.anki_service = AnkiService(self.deck_name)
        self._update_window_title()

        # Always show input fields and buttons.
        self.text_input = tk.Text(self.root, height=5, width=40, undo=True, autoseparators=True, maxundo=-1)
        self.text_input.bind('<Command-z>', lambda e: self.text_input.edit_undo() or 'break')
        self.text_input.bind('<Command-Shift-Z>', lambda e: self.text_input.edit_redo() or 'break')
        self.text_input.grid(row=1, column=0, columnspan=6, padx=3, pady=1, sticky="ew")
        self.text_input.bind("<Return>", self.on_enter)
        self._configure_text_widget_shortcuts(self.text_input)

        self.auto_check = ttk.Checkbutton(self.root, text="auto", variable=self.auto_detect)
        self.auto_check.grid(row=2, column=0, padx=3, pady=1, sticky="ew")
        Tooltip(self.auto_check, "Detect language automatically")

        self.text_output = tk.Text(self.root, height=5, width=40)
        self.text_output.grid(row=3, column=0, columnspan=6, padx=3, pady=5, sticky="ew")
        self._configure_text_widget_shortcuts(self.text_output)

        # Terminal-style status output at the bottom.
        self.status_output = tk.Text(self.root, height=1, width=40, state="disabled", bg="#222", fg="#eee")
        self.status_output.grid(row=4, column=0, columnspan=6, padx=3, pady=(0,5), sticky="ew")

        self._load_existing_notes()

        # Create the menu bar.
        self._create_menu()

        # Keyboard shortcuts.
        self.root.bind('<Command-s>', lambda e: self.save_current_as_apkg() or 'break')
        self.root.bind('<Command-t>', lambda e: self.translate() or 'break')
        self.root.bind('<Command-Shift-T>', lambda e: self.start_ocr_capture() or 'break')

        # Push to talk with the R key, unless a text or input field is focused.
        self.root.bind('<KeyPress-r>', self._on_r_keypress)
        self.root.bind('<KeyRelease-r>', self._on_r_keyrelease)

    def _build_buttons(self):

        # Arrange all buttons in grid order, from top left to bottom right.

        self.speak_output_btn = ttk.Button(self.root, text="🔊", command=self.speak_input_auto)
        self.speak_output_btn.grid(row=0, column=0, padx=1, pady=1, sticky="ew")
        Tooltip(self.speak_output_btn, "Read input text aloud")

        self.src_combo = ttk.Combobox(self.root, values=self.languages, textvariable=self.src_lang_var, state="readonly", width=8)
        self.src_combo.grid(row=0, column=1, padx=1, pady=1, sticky="ew")
        Tooltip(self.src_combo, "Choose source language")

        self.swap_btn = ttk.Button(self.root, text="⟲", width=2, command=self.swap_languages)
        self.swap_btn.grid(row=0, column=2, padx=1, pady=1, sticky="ew")
        Tooltip(self.swap_btn, "Swap languages and texts")

        self.dest_combo = ttk.Combobox(self.root, values=self.languages, textvariable=self.dest_lang_var, state="readonly", width=8)
        self.dest_combo.grid(row=0, column=3, padx=1, pady=1, sticky="ew")
        Tooltip(self.dest_combo, "Choose target language")

        self.speak_input_btn = ttk.Button(self.root, text="🔊", command=self.speak_output_auto)
        self.speak_input_btn.grid(row=0, column=4, padx=1, pady=1, sticky="ew")
        Tooltip(self.speak_input_btn, "Read output text aloud")

        self.settings_btn = ttk.Button(self.root, text="⚙️", command=self.open_settings)
        self.settings_btn.grid(row=0, column=5, padx=1, pady=1, sticky="ew")
        Tooltip(self.settings_btn, "Settings")

        # Bottom row.

        self.translate_btn = ttk.Button(self.root, text="translate", width=7, command=self.translate)
        self.translate_btn.grid(row=2, column=1, padx=1, pady=1, sticky="ew")
        Tooltip(self.translate_btn, "Translate")

        self.ocr_btn = ttk.Button(self.root, text="📷", command=self.start_ocr_capture)
        self.ocr_btn.grid(row=2, column=2, padx=1, pady=1, sticky="ew")
        Tooltip(self.ocr_btn, "OCR Screenshot")

            # Push to talk: recording continues while the button is held down.
        self.mic_btn = ttk.Button(self.root, text="🎤")
        self.mic_btn.grid(row=2, column=3, padx=1, pady=1, sticky="ew")
        Tooltip(self.mic_btn, "Record speech")
        self.mic_btn.bind("<ButtonPress-1>", lambda e: self._begin_mic_recording())
        self.mic_btn.bind("<ButtonRelease-1>", lambda e: self._end_mic_recording())

        self.ai_btn = ttk.Button(self.root, text="✨✨", command=self.on_ai_button)
        self.ai_btn.grid(row=2, column=4, padx=1, pady=1, sticky="ew")
        Tooltip(self.ai_btn, "AI")

        self.save_apkg_btn = ttk.Button(self.root, text="⭐", command=self.save_current_as_apkg)
        self.save_apkg_btn.grid(row=2, column=5, padx=1, pady=1, sticky="ew")
        Tooltip(self.save_apkg_btn, "Save card")

    def _create_menu(self):
        """Create the macOS menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu.
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Card", command=self.save_current_as_apkg, accelerator="Cmd+S")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.on_close, accelerator="Cmd+Q")
        
        # Edit menu.
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Translate", command=self.translate, accelerator="Cmd+T")
        edit_menu.add_command(label="Swap Languages", command=self.swap_languages, accelerator="Cmd+R")
        
        # Tools menu.
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="ScreenshotOCR", command=self.start_ocr_capture, accelerator="Cmd+Shift+T")
        tools_menu.add_separator()
        tools_menu.add_command(label="Speak Input", command=self.speak_input_auto, accelerator="Cmd+I")
        tools_menu.add_command(label="Speak Output", command=self.speak_output_auto, accelerator="Cmd+O")
        
        # Cmd+Q and other shortcuts.
        self.root.bind('<Command-q>', lambda e: self.on_close() or 'break')
        self.root.bind('<Command-r>', lambda e: self.swap_languages() or 'break')
        self.root.bind('<Command-i>', lambda e: self.speak_input_auto() or 'break')
        self.root.bind('<Command-o>', lambda e: self.speak_output_auto() or 'break')

    def show_about_dialog(self):
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME}\nVersion {APP_VERSION}"
        )

    def show_preferences(self):
        self.open_settings()

    def _configure_text_widget_shortcuts(self, widget):
        widget.bind('<Shift-Return>', self._insert_newline)
        widget.bind('<Shift-KP_Enter>', self._insert_newline)
        widget.bind('<Command-Left>', self._move_to_line_start)
        widget.bind('<Command-Right>', self._move_to_line_end)
        widget.bind('<Command-Up>', self._move_to_text_start)
        widget.bind('<Command-Down>', self._move_to_text_end)
        widget.bind('<Command-Shift-Left>', self._select_to_line_start)
        widget.bind('<Command-Shift-Right>', self._select_to_line_end)
        widget.bind('<Command-Shift-Up>', self._select_to_text_start)
        widget.bind('<Command-Shift-Down>', self._select_to_text_end)

    def _insert_newline(self, event):
        event.widget.insert('insert', '\n')
        return 'break'

    def _move_to_line_start(self, event):
        event.widget.mark_set('insert', 'insert linestart')
        event.widget.see('insert')
        return 'break'

    def _move_to_line_end(self, event):
        event.widget.mark_set('insert', 'insert lineend')
        event.widget.see('insert')
        return 'break'

    def _move_to_text_start(self, event):
        event.widget.mark_set('insert', '1.0')
        event.widget.see('insert')
        return 'break'

    def _move_to_text_end(self, event):
        event.widget.mark_set('insert', 'end-1c')
        event.widget.see('insert')
        return 'break'

    def _select_from_insert_to(self, widget, index):
        start_index = widget.index('insert')
        target_index = widget.index(index)
        widget.tag_remove('sel', '1.0', 'end')
        widget.mark_set('insert', target_index)
        if widget.compare(start_index, '<=', target_index):
            widget.tag_add('sel', start_index, target_index)
        else:
            widget.tag_add('sel', target_index, start_index)
        widget.see('insert')

    def _select_to_line_start(self, event):
        self._select_from_insert_to(event.widget, 'insert linestart')
        return 'break'

    def _select_to_line_end(self, event):
        self._select_from_insert_to(event.widget, 'insert lineend')
        return 'break'

    def _select_to_text_start(self, event):
        self._select_from_insert_to(event.widget, '1.0')
        return 'break'

    def _select_to_text_end(self, event):
        self._select_from_insert_to(event.widget, 'end-1c')
        return 'break'

    def speak_english_auto(self):
        # Prefer the output field, then the input field.
        output_text = self.text_output.get("1.0", tk.END).strip()
        input_text = self.text_input.get("1.0", tk.END).strip()
        if self.dest_lang_var.get() == "English" and output_text:
            self.speech_service.speak(output_text, "English")
            self.set_status("Englischer Text im Ausgabefeld vorgelesen.")
        elif self.src_lang_var.get() == "English" and input_text:
            self.speech_service.speak(input_text, "English")
            self.set_status("Englischer Text im Eingabefeld vorgelesen.")
        else:
            self.set_status("Kein englischer Text zum Vorlesen gefunden.")

    def speak_german_auto(self):
        output_text = self.text_output.get("1.0", tk.END).strip()
        input_text = self.text_input.get("1.0", tk.END).strip()
        if self.dest_lang_var.get() == "German" and output_text:
            self.speech_service.speak(output_text, "German")
            self.set_status("Deutscher Text im Ausgabefeld vorgelesen.")
        elif self.src_lang_var.get() == "German" and input_text:
            self.speech_service.speak(input_text, "German")
            self.set_status("Deutscher Text im Eingabefeld vorgelesen.")
        else:
            self.set_status("Kein deutscher Text zum Vorlesen gefunden.")

    def _update_window_title(self):
        """Update the window title with the current deck name."""
        self.root.title(self.deck_name)

    def _parse_recent_decks(self, recent_value):
        """Read recent entries from the config in JSON or legacy format."""
        recent = []
        if not recent_value:
            return recent

        # New format: JSON list of objects {name, path}.
        try:
            data = json.loads(recent_value)
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    name = str(entry.get('name', '')).strip()
                    path = str(entry.get('path', '')).strip()
                    if name:
                        if not path:
                            path = os.path.join(self.last_deck_directory, f"{name}.apkg")
                        recent.append({'name': name, 'path': path})
                return recent
        except Exception:
            pass

        # Legacy format: "name;name;..." or "name|path;...".
        for token in recent_value.split(';'):
            token = token.strip()
            if not token:
                continue
            if '|' in token:
                name, path = token.split('|', 1)
                name = name.strip()
                path = path.strip()
            else:
                name = token
                path = os.path.join(self.last_deck_directory, f"{name}.apkg")
            if name:
                recent.append({'name': name, 'path': path})
        return recent

    def _serialize_recent_decks(self, recent_decks):
        """Write recent entries to the config as a JSON string."""
        return json.dumps(recent_decks, ensure_ascii=True)

    def open_settings(self):
        if not hasattr(self, "settings_ui"):
            self.settings_ui = SettingsWindow(self)
        self.settings_ui.show()

    def _focus_is_text_entry(self):
        widget = self.root.focus_get()
        return isinstance(widget, (tk.Text, tk.Entry, ttk.Entry, ttk.Combobox))

    def _on_r_keypress(self, event):
        if self._focus_is_text_entry():
            return
        # OS key repeat sends press/release pairs while held; discard the pending stop.
        if getattr(self, "_r_release_after_id", None):
            self.root.after_cancel(self._r_release_after_id)
            self._r_release_after_id = None
        self._begin_mic_recording()

    def _on_r_keyrelease(self, event):
        if self._focus_is_text_entry():
            return
        self._r_release_after_id = self.root.after(60, self._end_mic_recording)

    def _begin_mic_recording(self):
        if self.transcription_service.is_recording:
            return
        try:
            self.transcription_service.start_recording()
        except Exception as e:
            self.set_status(f"Microphone error: {e}")
            return
        self.mic_btn.state(["pressed"])
        self.set_status("🎤 Recording...")

    def _end_mic_recording(self):
        if not self.transcription_service.is_recording:
            return
        self.mic_btn.state(["!pressed"])
        self.set_status("Transkribiere...")
        language = self.lang_codes.get(self.src_lang_var.get())

        def worker():
            try:
                text = self.transcription_service.stop_and_transcribe(language=language)
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Transkription fehlgeschlagen: {e}"))
                return
            self.root.after(0, lambda: self._on_transcription_done(text))

        threading.Thread(target=worker, daemon=True).start()

    def _on_transcription_done(self, text):
        recording = self.transcription_service.take_last_recording()
        if not text:
            self.set_status("No speech detected.")
            return
        self.text_input.delete("1.0", tk.END)
        self.text_input.insert(tk.END, text)
        if recording:
            audio, sample_rate = recording
            self._pending_recording = {
                "text": text,
                "language": self.src_lang_var.get(),
                "audio": audio,
                "sample_rate": sample_rate,
            }
        self.translate()
        self.set_status("Transcription inserted and translated.")

    def on_ai_button(self):
        if not self.ai_service.is_configured:
            self.set_status("Please add an API key in Settings first.")
            return

        source_text = self.text_input.get("1.0", tk.END).strip()
        translated_text = self.text_output.get("1.0", tk.END).strip()
        if not source_text:
            self.set_status("Please enter text first.")
            return

        if not translated_text:
            self.translate()
            translated_text = self.text_output.get("1.0", tk.END).strip()
            if not translated_text:
                return

        try:
            refined_source, refined_translation = self.ai_service.refine_translation(
                source_text, translated_text,
                self.src_lang_var.get(), self.dest_lang_var.get()
            )
            self.text_input.delete("1.0", tk.END)
            self.text_input.insert(tk.END, refined_source)
            self.text_output.delete("1.0", tk.END)
            self.text_output.insert(tk.END, refined_translation)
            self.set_status("AI checked and improved the source text and translation.")
        except Exception as e:
            self.set_status(f"AI check failed: {e}")

    def set_status(self, msg):
        self.status_output.config(state="normal")
        self.status_output.delete("1.0", tk.END)
        self.status_output.insert(tk.END, msg)
        self.status_output.config(state="disabled")

    def _load_existing_notes(self):
        try:
            self.anki_service.load_existing_notes()
        except Exception as e:
            self.set_status(f"Warning: Could not load existing cards: {e}")


    def save_current_as_apkg(self):
            try:
                src_text = self.text_input.get("1.0", tk.END).strip()
                dest_text = self.text_output.get("1.0", tk.END).strip()
                if not src_text or not dest_text:
                    self.set_status("Please enter and translate text first.")
                    return
                if self.src_lang_var.get() == "English":
                    english_text, german_text = src_text, dest_text
                else:
                    english_text, german_text = dest_text, src_text

                recording = self._pending_recording
                self._pending_recording = None
                recording_arg = None
                # Language detection may have changed src_lang_var after recording (auto mode),
                # so use the unchanged text to determine the target field for the recording.
                if recording and recording["text"] == src_text:
                    field_name = "english" if english_text == src_text else "german"
                    recording_arg = (field_name, recording["audio"], recording["sample_rate"])

                result, details = self.anki_service.save_card(
                    english_text, german_text, recording=recording_arg
                )
                if result == "duplicate":
                    self.set_status("Diese Karte ist bereits im Deck.")
                elif result == "audio_error":
                    self.set_status(f"Could not create audio: {details}")
                else:
                    self.set_status(f"Safe:{self.anki_service.collection_path}")
            except Exception as e:
                self.set_status(f"Could not save cards: {e}")

    def on_enter(self, event):
        if event.state & 0x1:  # Shift key held
            event.widget.insert('insert', '\n')
            return 'break'
        self.translate()
        return "break"

    def swap_languages(self):
        src = self.src_lang_var.get()
        dest = self.dest_lang_var.get()
        self.src_lang_var.set(dest)
        self.dest_lang_var.set(src)
        input_text = self.text_input.get("1.0", tk.END).strip()
        output_text = self.text_output.get("1.0", tk.END).strip()
        self.text_input.delete("1.0", tk.END)
        self.text_input.insert(tk.END, output_text)
        self.text_output.delete("1.0", tk.END)
        self.text_output.insert(tk.END, input_text)

    def translate(self):
        text = self.text_input.get("1.0", tk.END).strip()
        if not text:
            self.set_status("Please enter text.")
            return
        try:
            if self.auto_detect.get():
                detected_language, translated_text = self.translation_service.detect_and_translate(text)
                if detected_language == "de":
                    self.src_lang_var.set("German")
                    self.dest_lang_var.set("English")
                else:
                    self.src_lang_var.set("English")
                    self.dest_lang_var.set("German")
            else:
                src = self.lang_codes[self.src_lang_var.get()]
                dest = self.lang_codes[self.dest_lang_var.get()]
                translated_text = self.translation_service.translate(text, src, dest)
            self.text_output.delete("1.0", tk.END)
            self.text_output.insert(tk.END, translated_text)
        except Exception as e:
            if self.translation_service.is_timeout_error(e):
                self.set_status("wait;try again;translation timed out.")
            else:
                messagebox.showerror("Error", f"Translation failed:\n{e}")

    def debug_window_geometry(self):
        geom = self.root.geometry()
        print(f"Current window geometry: {geom}")
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        print(f"Width: {w}, Height: {h}, X: {x}, Y: {y}")

    def on_close(self):
        self.debug_window_geometry()
        self.root.destroy()

    def speak_output_auto(self):
        text = self.text_output.get("1.0", tk.END).strip()
        lang = self.dest_lang_var.get()
        if not text:
            self.set_status("No text in the output field.")
            return
        if lang == "English":
            self.speech_service.speak(text, "English")
            self.set_status("Read English text from the output field aloud.")
        elif lang == "German":
            self.speech_service.speak(text, "German")
            self.set_status("Read German text from the output field aloud.")
        else:
            self.set_status("Unknown language in the output field.")

    def speak_input_auto(self):
        text = self.text_input.get("1.0", tk.END).strip()
        lang = self.src_lang_var.get()
        if not text:
            self.set_status("No text in the input field.")
            return
        if lang == "English":
            self.speech_service.speak(text, "English")
            self.set_status("Read English text from the input field aloud.")
        elif lang == "German":
            self.speech_service.speak(text, "German")
            self.set_status("Read German text from the input field aloud.")
        else:
            self.set_status("Unknown language in the input field.")

    def start_ocr_capture(self):
        """Start screenshot selection for OCR using macOS screencapture"""
        self.set_status("Select an area with the mouse...")
        self.root.withdraw()
        try:
            text = self.ocr_service.capture_text()
            if text:
                self._set_ocr_text(text)
            else:
                self.set_status("Screenshot cancelled.")
        except TimeoutError:
            self.set_status("Screenshot Timeout.")
        except Exception as e:
            self.set_status(f"Error: {e}")
        finally:
            self.root.deiconify()

    def perform_ocr_from_file(self, image_path):
        """Perform OCR on saved screenshot file"""
        try:
            text = self.ocr_service.text_from_file(image_path)
            if text:
                self._set_ocr_text(text)
            else:
                self.set_status("No text detected.")
        except Exception as e:
            self.set_status(f"OCR error: {e}")
            print(f"DEBUG: Exception: {e}")
            messagebox.showerror("OCR error", f"Text recognition failed:\n{e}")

    def _set_ocr_text(self, text):
        self.text_input.delete("1.0", tk.END)
        self.text_input.insert(tk.END, text)
        self.set_status(f"OCR erfolgreich: {len(text)} Zeichen erkannt.")
        self.translate()

if __name__ == "__main__":
    configure_macos_process_name()
    root = tk.Tk()
    app = TranslatorApp(root)
    root.geometry(f"{app.window_width}x{app.window_height}+{app.window_x}+{app.window_y}")
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
