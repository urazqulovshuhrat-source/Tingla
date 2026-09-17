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
from kivy.utils import platform
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup

import yt_dlp

IS_ANDROID = platform == "android"

if IS_ANDROID:
    from jnius import autoclass, PythonJavaClass, java_method

    AndroidMediaPlayer = autoclass("android.media.MediaPlayer")
    AudioManager = autoclass("android.media.AudioManager")

    class _OnPreparedListener(PythonJavaClass):
        __javainterfaces__ = ["android/media/MediaPlayer$OnPreparedListener"]
        __javacontext__ = "app"

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method("(Landroid/media/MediaPlayer;)V")
        def onPrepared(self, mp):
            self.callback()

    class _OnErrorListener(PythonJavaClass):
        __javainterfaces__ = ["android/media/MediaPlayer$OnErrorListener"]
        __javacontext__ = "app"

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method("(Landroid/media/MediaPlayer;II)Z")
        def onError(self, mp, what, extra):
            self.callback(what, extra)
            return True

    class _OnCompletionListener(PythonJavaClass):
        __javainterfaces__ = ["android/media/MediaPlayer$OnCompletionListener"]
        __javacontext__ = "app"

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method("(Landroid/media/MediaPlayer;)V")
        def onCompletion(self, mp):
            self.callback()


class StreamPlayer:
    """Android'ning tabiiy MediaPlayer'i orqali internet oqimini ijro etadi.

    Kivy'ning o'z audio tizimidan farqli o'laroq, bu HTTP/HTTPS orqali
    to'g'ridan-to'g'ri oqim (stream) qilishni to'liq qo'llab-quvvatlaydi.
    Barcha callback'lar Android'ning o'z ichki oqimida chaqiriladi, shuning
    uchun ular Kivy widget'larini bevosita o'zgartirmaydi - App shu
    callback'lar ichida Clock.schedule_once orqali UI'ni yangilaydi.
    """

    def __init__(self, on_ready=None, on_error=None, on_finished=None):
        self.on_ready = on_ready
        self.on_error = on_error
        self.on_finished = on_finished
        self._mp = None

    def play(self, url):
        self.release()
        if not IS_ANDROID:
            if self.on_error:
                self.on_error("Faqat Android qurilmasida ishlaydi")
            return

        self._mp = AndroidMediaPlayer()
        try:
            self._mp.setAudioStreamType(AudioManager.STREAM_MUSIC)
            self._mp.setOnPreparedListener(_OnPreparedListener(self._on_prepared))
            self._mp.setOnErrorListener(_OnErrorListener(self._on_error_cb))
            self._mp.setOnCompletionListener(_OnCompletionListener(self._on_completion))
            self._mp.setDataSource(url)
            self._mp.prepareAsync()
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))

    def _on_prepared(self):
        try:
            self._mp.start()
        except Exception:
            pass
        if self.on_ready:
            self.on_ready()

    def _on_error_cb(self, what, extra):
        if self.on_error:
            self.on_error(f"MediaPlayer xatosi: {what}/{extra}")

    def _on_completion(self):
        if self.on_finished:
            self.on_finished()

    def toggle_pause(self):
        if not self._mp:
            return
        try:
            if self._mp.isPlaying():
                self._mp.pause()
            else:
                self._mp.start()
        except Exception:
            pass

    def is_playing(self):
        if not self._mp:
            return False
        try:
            return bool(self._mp.isPlaying())
        except Exception:
            return False

    def release(self):
        if self._mp:
            try:
                self._mp.stop()
            except Exception:
                pass
            try:
                self._mp.release()
            except Exception:
                pass
        self._mp = None


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
        self.player = StreamPlayer(
            on_ready=self._on_player_ready,
            on_error=self._on_player_error,
            on_finished=self._on_track_finished,
        )
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
        self._play_queue_index(self.current_index)

    def _play_queue_index(self, index):
        item = self.queue[index]
        self.show_message(f"Yuklanmoqda: {item['title']}")
        threading.Thread(
            target=self._load_and_play_thread, args=(item,), daemon=True
        ).start()

    def _load_and_play_thread(self, item):
        url = get_stream_url(item["id"])
        if not url:
            Clock.schedule_once(
                lambda dt: self.show_message(f"Xato: '{item['title']}' topilmadi")
            )
            return
        self._current_title = item["title"]
        # MediaPlayer.setDataSource/prepareAsync - alohida iplarda chaqirish xavfsiz
        self.player.play(url)

    def _on_player_ready(self, *_):
        title = getattr(self, "_current_title", "")
        Clock.schedule_once(lambda dt: self.show_message(f"▶ {title}"))

    def _on_player_error(self, message):
        Clock.schedule_once(lambda dt: self.show_message(f"Xato: {message}"))

    def _on_track_finished(self, *_):
        # Qo'shiq tugagach avtomatik keyingisiga o'tish (agar bo'lsa)
        Clock.schedule_once(lambda dt: self.on_next())

    def on_playpause(self, *_):
        self.player.toggle_pause()
        if self.player.is_playing():
            title = getattr(self, "_current_title", "")
            self.show_message(f"▶ {title}")
        else:
            self.show_message("⏸ To'xtatildi")

    def on_next(self, *_):
        if self.current_index + 1 < len(self.queue):
            self.current_index += 1
            self._play_queue_index(self.current_index)

    def on_prev(self, *_):
        if self.current_index > 0:
            self.current_index -= 1
            self._play_queue_index(self.current_index)

    # ------------------------------------------------------------------
    def show_message(self, text):
        self.now_playing_label.text = text


if __name__ == "__main__":
    MusicPlayerApp().run()
