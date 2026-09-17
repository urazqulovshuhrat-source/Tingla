# -*- coding: utf-8 -*-
"""
Music Player - Android (Kivy) versiyasi
-----------------------------------------
YouTube'dan qidirish va oqim (stream) tarzida ijro etish.

Ishlatilgan kutubxonalar:
    kivy    - interfeys (UI)
    yt-dlp  - qidiruv va audio manba (URL) topish (Python kutubxona sifatida)

Ijro Kivy'ning o'z SoundLoader'i orqali amalga oshiriladi - Android'da bu
tizimning o'z media pleyeridan (android.media.MediaPlayer) foydalanadi va
internetdan to'g'ridan-to'g'ri oqim (stream) qila oladi.
"""

import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup

import yt_dlp


def yt_search(query, limit=15):
    """YouTube'dan qidiradi, natijalar ro'yxatini qaytaradi (title, id)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    results = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            for entry in info.get("entries", []) or []:
                if not entry:
                    continue
                results.append(
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title") or "Noma'lum",
                        "duration": entry.get("duration"),
                    }
                )
    except Exception as e:
        print("Qidiruv xatosi:", e)
    return results


def get_stream_url(video_id):
    """Berilgan video ID uchun to'g'ridan-to'g'ri audio oqim URL'ini topadi."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "skip_download": True,
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")
    except Exception as e:
        print("Oqim URL topishda xato:", e)
        return None


def fmt_duration(seconds):
    if not seconds:
        return "--:--"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class MusicPlayerApp(App):
    def build(self):
        self.sound = None
        self.queue = []
        self.current_index = -1

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        # --- Qidiruv qatori ---
        search_row = BoxLayout(size_hint=(1, None), height=48, spacing=6)
        self.search_input = TextInput(
            hint_text="Qidiruv so'zi...", multiline=False
        )
        search_btn = Button(text="Qidirish", size_hint=(None, 1), width=110)
        search_btn.bind(on_release=self.on_search)
        search_row.add_widget(self.search_input)
        search_row.add_widget(search_btn)
        root.add_widget(search_row)

        # --- Hozir ijro etilayotgan qo'shiq ---
        self.now_playing_label = Label(
            text="Hech narsa ijro etilmayapti",
            size_hint=(1, None),
            height=40,
        )
        root.add_widget(self.now_playing_label)

        # --- Natijalar / navbat ro'yxati ---
        self.results_box = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=4
        )
        self.results_box.bind(minimum_height=self.results_box.setter("height"))
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.results_box)
        root.add_widget(scroll)

        # --- Boshqaruv tugmalari ---
        controls = BoxLayout(size_hint=(1, None), height=52, spacing=6)
        prev_btn = Button(text="⏮ Oldingi")
        playpause_btn = Button(text="⏯ Play/Stop")
        next_btn = Button(text="⏭ Keyingi")
        prev_btn.bind(on_release=self.on_prev)
        playpause_btn.bind(on_release=self.on_playpause)
        next_btn.bind(on_release=self.on_next)
        controls.add_widget(prev_btn)
        controls.add_widget(playpause_btn)
        controls.add_widget(next_btn)
        root.add_widget(controls)

        return root

    # ------------------------------------------------------------------
    # Qidiruv
    # ------------------------------------------------------------------
    def on_search(self, *_):
        query = self.search_input.text.strip()
        if not query:
            return
        self.show_message(f"'{query}' qidirilmoqda...")
        threading.Thread(
            target=self._search_thread, args=(query,), daemon=True
        ).start()

    def _search_thread(self, query):
        results = yt_search(query)
        Clock.schedule_once(lambda dt: self._show_results(results))

    def _show_results(self, results):
        self.results_box.clear_widgets()
        if not results:
            self.results_box.add_widget(Label(text="Hech narsa topilmadi", size_hint_y=None, height=40))
            return
        for item in results:
            label = f"{item['title']}  [{fmt_duration(item.get('duration'))}]"
            btn = Button(text=label, size_hint_y=None, height=48, halign="left")
            btn.bind(on_release=lambda inst, it=item: self.play_item(it))
            self.results_box.add_widget(btn)

    # ------------------------------------------------------------------
    # Ijro
    # ------------------------------------------------------------------
    def play_item(self, item):
        self.queue.append(item)
        self.current_index = len(self.queue) - 1
        self.show_message(f"Yuklanmoqda: {item['title']}")
        threading.Thread(
            target=self._load_and_play_thread, args=(item,), daemon=True
        ).start()

    def _load_and_play_thread(self, item):
        url = get_stream_url(item["id"])
        Clock.schedule_once(lambda dt: self._play_url(url, item))

    def _play_url(self, url, item):
        if not url:
            self.show_message(f"Xato: '{item['title']}' ijro etib bo'lmadi")
            return
        if self.sound:
            self.sound.stop()
            self.sound.unload()
        self.sound = SoundLoader.load(url)
        if self.sound:
            self.sound.bind(on_stop=self._on_track_finished)
            self.sound.play()
            self.now_playing_label.text = f"▶ {item['title']}"
        else:
            self.show_message("Ijro etib bo'lmadi (format qo'llab-quvvatlanmaydi)")

    def _on_track_finished(self, *_):
        # Qo'shiq tugagach avtomatik keyingisiga o'tish (agar bo'lsa)
        pass

    def on_playpause(self, *_):
        if not self.sound:
            return
        if self.sound.state == "play":
            self.sound.stop()
            self.now_playing_label.text = "⏸ To'xtatildi"
        else:
            self.sound.play()

    def on_next(self, *_):
        if self.current_index + 1 < len(self.queue):
            self.current_index += 1
            item = self.queue[self.current_index]
            self.show_message(f"Yuklanmoqda: {item['title']}")
            threading.Thread(
                target=self._load_and_play_thread, args=(item,), daemon=True
            ).start()

    def on_prev(self, *_):
        if self.current_index > 0:
            self.current_index -= 1
            item = self.queue[self.current_index]
            self.show_message(f"Yuklanmoqda: {item['title']}")
            threading.Thread(
                target=self._load_and_play_thread, args=(item,), daemon=True
            ).start()

    # ------------------------------------------------------------------
    def show_message(self, text):
        self.now_playing_label.text = text


if __name__ == "__main__":
    MusicPlayerApp().run()
