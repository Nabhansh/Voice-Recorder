"""
Advanced Voice Recorder – Modern UI Edition (Repaired)

Features:
- 🎚 Live audio level bar
- 🎤 Microphone selector dropdown
- Stable Windows mic handling
- Text-only splash (safe for double-click)
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import time
import queue
import threading
from collections import deque
from datetime import timedelta
        
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import numpy as np
import sounddevice as sd
import soundfile as sf
import lameenc

# ---------------- SPLASH ----------------
def show_splash():
    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.configure(bg="#121212")

    w, h = 400, 200
    x = (splash.winfo_screenwidth() - w) // 2
    y = (splash.winfo_screenheight() - h) // 2
    splash.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(
        splash,
        text="🎙 Advanced Voice Recorder",
        fg="white",
        bg="#121212",
        font=("Segoe UI", 16, "bold")
    ).pack(expand=True)

    splash.after(2000, splash.destroy)
    splash.mainloop()


# ---------------- CONFIG ----------------
SAMPLE_RATE = 48000
CHANNELS = 1
CHUNK_SIZE = 1024
WAVE_SECONDS = 3
MAX_SAMPLES = SAMPLE_RATE * WAVE_SECONDS


# ---------------- MIC LIST ----------------
def list_mics():
    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


# ---------------- AUDIO ----------------
class Recorder:
    def __init__(self):
        self.stream = None
        self.q = queue.Queue()
        self.frames = []
        self.recording = False
        self.paused = False
        self.lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        with self.lock:
            if not self.recording or self.paused:
                return
        self.q.put(indata.copy())

    def start(self, device_index):
        with self.lock:
            self.frames.clear()
            self.recording = True
            self.paused = False

        self.stream = sd.InputStream(
            device=device_index,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=CHUNK_SIZE,
            callback=self._callback,
        )
        self.stream.start()

    def stop(self):
        with self.lock:
            self.recording = False
            self.paused = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        while not self.q.empty():
            self.frames.append(self.q.get())

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def collect(self):
        while not self.q.empty():
            self.frames.append(self.q.get())

    def audio(self):
        if not self.frames:
            return np.empty((0, CHANNELS), dtype=np.float32)
        return np.concatenate(self.frames, axis=0)

    def save_wav(self, path):
        data = self.audio()
        if data.size == 0:
            raise RuntimeError("No audio recorded")
        sf.write(path, data, SAMPLE_RATE, subtype="PCM_16")

    def save_mp3(self, path):
        data = self.audio()
        if data.size == 0:
            raise RuntimeError("No audio recorded")

        pcm = (data * 32767).astype(np.int16).tobytes()
        enc = lameenc.Encoder()
        enc.set_bit_rate(128)
        enc.set_in_sample_rate(SAMPLE_RATE)
        enc.set_channels(CHANNELS)
        enc.set_quality(2)

        mp3 = enc.encode(pcm) + enc.flush()
        with open(path, "wb") as f:
            f.write(mp3)


# ---------------- UI ----------------
class VoiceRecorderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Advanced Voice Recorder")
        self.geometry("920x520")
        self.configure(bg="#0f0f0f")
        self.resizable(False, False)

        self.rec = Recorder()
        self.wave = deque(maxlen=MAX_SAMPLES)
        self.start_time = None
        self.level = 0.0

        self.mics = list_mics()
        if not self.mics:
            messagebox.showerror("Error", "No microphone detected.")
            self.destroy()
            return

        self._build_layout()
        self._build_waveform()

        self.after(50, self.update_ui)

    # ---------- LAYOUT ----------
    def _build_layout(self):
        self.controls = tk.Frame(self, bg="#181818")
        self.controls.place(x=20, y=20, width=200, height=480)

        tk.Label(
            self.controls, text="🎙 Recorder",
            fg="white", bg="#181818",
            font=("Segoe UI", 14, "bold")
        ).pack(pady=(12, 10))

        tk.Label(
            self.controls, text="Microphone",
            fg="#bdbdbd", bg="#181818",
            font=("Segoe UI", 9)
        ).pack()

        self.mic_var = tk.StringVar(value=self.mics[0][1])
        ttk.Combobox(
            self.controls,
            values=[m[1] for m in self.mics],
            textvariable=self.mic_var,
            state="readonly",
            width=22
        ).pack(pady=(0, 12))

        self.btn_start = self._btn("▶ Start", self.start, "#1db954")
        self.btn_pause = self._btn("⏸ Pause", self.pause, "#fbbc05", disabled=True)
        self.btn_resume = self._btn("⏵ Resume", self.resume, "#4285f4", disabled=True)
        self.btn_stop = self._btn("⏹ Stop", self.stop, "#ea4335", disabled=True)

        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop):
            b.pack(pady=6)

        self.btn_wav = self._btn("💾 Save WAV", self.save_wav, "#673ab7")
        self.btn_mp3 = self._btn("🎵 Save MP3", self.save_mp3, "#ff6d00")
        self.btn_wav.pack(pady=6)
        self.btn_mp3.pack(pady=6)

        self.status = tk.Label(
            self.controls, text="● Idle",
            fg="#9e9e9e", bg="#181818"
        )
        self.status.pack(pady=6)

        self.timer = tk.Label(
            self.controls, text="00:00:00",
            fg="#cfcfcf", bg="#181818"
        )
        self.timer.pack()

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor="#2b2b2b",
            background="#00e676"
        )

        self.level_bar = ttk.Progressbar(
            self.controls, length=160, maximum=1.0,
            style="Green.Horizontal.TProgressbar"
        )
        self.level_bar.pack(pady=8)

    def _btn(self, text, cmd, color, disabled=False):
        return tk.Button(
            self.controls, text=text, command=cmd,
            bg=color, fg="white", bd=0,
            state="disabled" if disabled else "normal"
        )

    # ---------- WAVEFORM ----------
    def _build_waveform(self):
        card = tk.Frame(self, bg="#161616")
        card.place(x=240, y=20, width=660, height=480)

        self.fig = Figure(figsize=(6.2, 3.8), dpi=100, facecolor="#161616")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#161616")
        self.ax.set_ylim(-1, 1)
        self.ax.axis("off")

        self.line, = self.ax.plot([], [], color="#00e676")
        self.canvas = FigureCanvasTkAgg(self.fig, master=card)
        self.canvas.get_tk_widget().pack(expand=True, fill="both")

    # ---------- CONTROLS ----------
    def start(self):
        mic_index = next(i for i, n in self.mics if n == self.mic_var.get())
        self.rec.start(mic_index)
        self.start_time = time.time()
        self.status.config(text="● Recording", fg="#1db954")
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")

    def pause(self):
        self.rec.pause()
        self.status.config(text="● Paused", fg="#fbbc05")
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="normal")

    def resume(self):
        self.rec.resume()
        self.status.config(text="● Recording", fg="#1db954")
        self.btn_pause.config(state="normal")
        self.btn_resume.config(state="disabled")

    def stop(self):
        self.rec.stop()
        self.start_time = None
        self.status.config(text="● Stopped", fg="#ea4335")
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="disabled")
        self.btn_stop.config(state="disabled")

    def save_wav(self):
        path = filedialog.asksaveasfilename(defaultextension=".wav")
        if path:
            self.rec.save_wav(path)
            messagebox.showinfo("Saved", "WAV file saved")

    def save_mp3(self):
        path = filedialog.asksaveasfilename(defaultextension=".mp3")
        if path:
            self.rec.save_mp3(path)
            messagebox.showinfo("Saved", "MP3 file saved")

    # ---------- UPDATE ----------
    def update_ui(self):
        self.rec.collect()

        if self.rec.frames:
            data = self.rec.frames[-1].flatten()
            self.wave.extend(data.tolist())
            rms = np.sqrt(np.mean(data ** 2))
            self.level = self.level * 0.8 + rms * 0.2
            self.level_bar["value"] = self.level

            y = np.array(self.wave)
            self.line.set_data(range(len(y)), y)
            self.ax.set_xlim(0, len(y))
            self.canvas.draw_idle()

        if self.rec.recording and self.start_time:
            self.timer.config(
                text=str(timedelta(seconds=int(time.time() - self.start_time)))
            )

        self.after(50, self.update_ui)


# ---------------- RUN ----------------
if __name__ == "__main__":
    show_splash()
    VoiceRecorderApp().mainloop()
