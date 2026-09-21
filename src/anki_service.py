import hashlib
import os
import sqlite3
import tempfile
import zipfile

import genanki

from audio_service import AudioService


class AnkiService:
    MODEL_ID = 1607392320

    def __init__(self, deck_name, base_directory="~/syncth/anki"):
        self.base_directory = os.path.expanduser(base_directory)
        self.model = genanki.Model(
            self.MODEL_ID,
            "Translation Model",
            fields=[{"name": "English"}, {"name": "German"}],
            templates=[
                {
                    "name": "Card 1",
                    "qfmt": "{{English}}",
                    "afmt": "{{English}}<hr id='answer'>{{German}}",
                }
            ],
        )
        self.switch_deck(deck_name)

    def switch_deck(self, deck_name):
        self.deck_name = deck_name
        self.deck_id = int(hashlib.md5(deck_name.encode()).hexdigest()[:8], 16)
        self.deck_folder = os.path.join(self.base_directory, deck_name)
        os.makedirs(self.deck_folder, exist_ok=True)
        self.media_folder = os.path.join(self.deck_folder, "media")
        self.collection_path = os.path.join(
            self.deck_folder, f"{deck_name}.apkg"
        )
        self.audio_service = AudioService(self.media_folder)
        self.deck = genanki.Deck(self.deck_id, self.deck_name)
        self.notes = []

    def load_existing_notes(self):
        if not os.path.exists(self.collection_path):
            return

        with tempfile.TemporaryDirectory() as temp_directory:
            database_path = os.path.join(temp_directory, "collection.anki2")
            with zipfile.ZipFile(self.collection_path, "r") as package:
                with package.open("collection.anki2") as database_file:
                    with open(database_path, "wb") as output_file:
                        output_file.write(database_file.read())

            with sqlite3.connect(database_path) as connection:
                for (fields_value,) in connection.execute("SELECT flds FROM notes"):
                    fields = fields_value.split("\x1f")
                    if len(fields) >= 2:
                        self.notes.append(
                            genanki.Note(model=self.model, fields=fields[:2])
                        )

    def save_card(self, english_text, german_text, recording=None):
        if self._contains_card(english_text, german_text):
            return "duplicate", None

        english_field = english_text
        german_field = german_text
        audio_error = None
        if english_text:
            try:
                english_field, _ = self.audio_service.create_english_audio(english_text)
            except Exception as error:
                audio_error = str(error)

        if recording:
            field_name, audio, sample_rate = recording
            try:
                sound_tag = self.audio_service.save_recording(audio, sample_rate)
                if field_name == "english":
                    english_field = f"{english_field} {sound_tag}"
                else:
                    german_field = f"{german_field} {sound_tag}"
            except Exception as error:
                audio_error = audio_error or str(error)

        self.notes.append(
            genanki.Note(model=self.model, fields=[english_field, german_field])
        )
        deck = genanki.Deck(self.deck_id, self.deck_name)
        for note in self.notes:
            deck.add_note(note)

        package = genanki.Package(deck)
        media_files = self.audio_service.all_media_files()
        if media_files:
            package.media_files = media_files
        package.write_to_file(self.collection_path)
        return "audio_error" if audio_error else "saved", audio_error

    def _contains_card(self, english_text, german_text):
        for note in self.notes:
            note_english = self._strip_sound(note.fields[0])
            note_german = self._strip_sound(note.fields[1])
            if note_english == english_text and note_german == german_text:
                return True
        return False

    @staticmethod
    def _strip_sound(text):
        return text.split("[sound:")[0].strip()
