"""
Advanced Voice Recorder GUI (FIXED VERSION)
Features:
- Modern dark-themed Tkinter GUI
- Start / Pause / Resume / Stop
- Save as WAV or MP3 (MP3 requires ffmpeg)
- Waveform visualization (matplotlib embedded)
- Live audio level meter + timer
- Smooth UI + No audio corruption

Dependencies:
pip install sounddevice soundfile numpy matplotlib pydub pillow
ffmpeg required for MP3 export
"""

import os
import queue
import threading
import tempfile
import time
from collections import deque
from datetime import timedelta
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import numpy as np
import sounddevice as sd
import soundfile as sf
from pydub import AudioSegment
from PIL import Image, ImageTk

# ---------- Config ----------
SAMPLE_RATE = 44100
CHANNELS = 1
CHUNK_SIZE = 1024
WAVE_DISPLAY_SECONDS = 3
MAX_WAVE_SAMPLES = SAMPLE_RATE * WAVE_DISPLAY_SECONDS


# ---------- Recorder Class ----------
class Recorder:
    def __init__(self, samplerate=SAMPLE_RATE, channels=CHANNELS, chunk=CHUNK_SIZE):
        self.samplerate = samplerate
        self.channels = channels
        self.chunk = chunk

        self.stream = None
        self.q = queue.Queue()
        self.frames = []
        self.recording = False
        self.paused = False
        self.lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print("Audio status:", status)
        with self.lock:
            if not self.recording or self.paused:
                return
        self.q.put(indata.copy())

    def start(self):
        with self.lock:
            if self.recording:
                return
            self.frames = []
            self.recording = True
            self.paused = False

        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            blocksize=self.chunk,
            callback=self._callback
        )
        self.stream.start()

    def stop(self):
        with self.lock:
            if not self.recording:
                return
            self.recording = False
            self.paused = False

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except:
                pass
            self.stream = None

        # Drain queue without deleting existing frames
        while not self.q.empty():
            try:
                self.frames.append(self.q.get_nowait())
            except:
                break

    def pause(self):
        with self.lock:
            if self.recording:
                self.paused = True

    def resume(self):
        with self.lock:
            if self.recording:
                self.paused = False

    def collect_from_queue(self):
        moved = 0
        while not self.q.empty():
            try:
                self.frames.append(self.q.get_nowait())
                moved += 1
            except:
                break
        return moved

    def get_combined(self):
        if not self.frames:
            return np.empty((0, self.channels), dtype=np.float32)
        return np.concatenate(self.frames, axis=0)

    def save_wav(self, filepath):
        data = self.get_combined()
        if data.size == 0:
            raise RuntimeError("No audio to save")
        sf.write(filepath, data, self.samplerate, subtype='PCM_16')

    def save_mp3(self, filepath):
        data = self.get_combined()
        if data.size == 0:
            raise RuntimeError("No audio to save")

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmpname = tmp.name
        tmp.close()

        sf.write(tmpname, data, self.samplerate, subtype='PCM_16')
        audio = AudioSegment.from_wav(tmpname)
        audio.export(filepath, format="mp3")
        os.unlink(tmpname)


# ---------- GUI Application ----------
class VoiceRecorderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎙️ Advanced Voice Recorder (Fixed)")
        self.geometry("900x520")
        self.configure(bg="#121212")
        self.resizable(False, False)

        self.rec = Recorder()
        self.wave_deque = deque(maxlen=MAX_WAVE_SAMPLES)

        self.last_level = 0.0
        self.start_time = None
        self.elapsed_seconds = 0

        self._build_ui()
        self._build_waveform()

        self.after(50, self._update_ui)

    # UI LAYOUT ---------------------------------------------------------------

    def _build_ui(self):
        header = tk.Frame(self, bg="#1b1b1b", height=70)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title = tk.Label(header, text="🎙️ Advanced Voice Recorder", fg="white",
                         bg="#1b1b1b", font=("Inter", 18, "bold"))
        title.pack(side="left", padx=20)

        # Controls
        controls = tk.Frame(self, bg="#121212")
        controls.place(x=20, y=90, width=260, height=400)

        self.btn_start = tk.Button(
            controls, text="Start Recording", command=self.start_recording,
            font=("Inter", 12, "bold"), width=22,
            bg="#0f9d58", fg="white", bd=0
        )
        self.btn_start.pack(pady=(10, 8))

        self.btn_pause = tk.Button(
            controls, text="Pause", command=self.pause_recording,
            font=("Inter", 12), width=22,
            bg="#f4b400", fg="white", bd=0, state="disabled"
        )
        self.btn_pause.pack(pady=8)

        self.btn_resume = tk.Button(
            controls, text="Resume", command=self.resume_recording,
            font=("Inter", 12), width=22,
            bg="#2196f3", fg="white", bd=0, state="disabled"
        )
        self.btn_resume.pack(pady=8)

        self.btn_stop = tk.Button(
            controls, text="Stop", command=self.stop_recording,
            font=("Inter", 12, "bold"), width=22,
            bg="#db4437", fg="white", bd=0, state="disabled"
        )
        self.btn_stop.pack(pady=8)

        save_frame = tk.Frame(controls, bg="#121212")
        save_frame.pack(pady=10)

        self.btn_save_wav = tk.Button(
            save_frame, text="Save as WAV", command=self.save_wav,
            font=("Inter", 11), width=10, bg="#5e35b1", fg="white", bd=0
        )
        self.btn_save_wav.grid(row=0, column=0, padx=6, pady=6)

        self.btn_save_mp3 = tk.Button(
            save_frame, text="Save as MP3", command=self.save_mp3,
            font=("Inter", 11), width=10, bg="#ff6d00", fg="white", bd=0
        )
        self.btn_save_mp3.grid(row=0, column=1, padx=6, pady=6)

        self.timer_label = tk.Label(controls, text="00:00:00", fg="#cfcfcf",
                                    bg="#121212", font=("Inter", 16))
        self.timer_label.pack(pady=(18, 6))

        self.status_label = tk.Label(controls, text="Idle", fg="#9e9e9e",
                                     bg="#121212", font=("Inter", 10))
        self.status_label.pack(pady=(0, 6))

        # Level Meter
        self.level_var = tk.DoubleVar()
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Green.Horizontal.TProgressbar",
                        troughcolor="#2b2b2b",
                        background="#00c853")

        level_label = tk.Label(controls, text="Audio Level",
                               fg="#bdbdbd", bg="#121212", font=("Inter", 10))
        level_label.pack()

        self.level_meter = ttk.Progressbar(
            controls, orient="horizontal",
            length=220, mode="determinate",
            variable=self.level_var,
            maximum=1.0,
            style="Green.Horizontal.TProgressbar"
        )
        self.level_meter.pack(pady=6)

        # Waveform card
        right_card = tk.Frame(self, bg="#161616")
        right_card.place(x=300, y=90, width=580, height=400)

        self.wave_container = tk.Frame(right_card, bg="#161616")
        self.wave_container.pack(expand=True, fill="both", padx=12, pady=12)

        bottom_info = tk.Frame(right_card, bg="#161616")
        bottom_info.pack(side="bottom", fill="x", padx=12, pady=12)

        self.samples_label = tk.Label(bottom_info, text="Samples: 0",
                                      fg="#bdbdbd", bg="#161616", font=("Inter", 10))
        self.samples_label.pack(side="left")

        self.frame_rate_label = tk.Label(
            bottom_info, text=f"Rate: {SAMPLE_RATE} Hz",
            fg="#bdbdbd", bg="#161616", font=("Inter", 10)
        )
        self.frame_rate_label.pack(side="right")

    # WAVEFORM ---------------------------------------------------------------

    def _build_waveform(self):
        self.fig = Figure(figsize=(5.2, 3.0), dpi=100, facecolor="#161616")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#161616")
        self.ax.set_ylim(-1, 1)
        self.ax.set_xlim(0, MAX_WAVE_SAMPLES)
        self.ax.axis("off")

        self.line, = self.ax.plot([], [], linewidth=1.2, color="#00e676")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.wave_container)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(expand=True, fill="both")

    # CONTROLS ---------------------------------------------------------------

    def start_recording(self):
        self.rec.start()
        self.start_time = time.time()
        self.status_label.config(text="Recording", fg="#00e676")

        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_resume.config(state="disabled")
        self.btn_stop.config(state="normal")

    def pause_recording(self):
        self.rec.pause()
        self.status_label.config(text="Paused", fg="#ffb74d")

        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="normal")

    def resume_recording(self):
        self.rec.resume()
        self.status_label.config(text="Recording", fg="#00e676")

        self.btn_pause.config(state="normal")
        self.btn_resume.config(state="disabled")

    def stop_recording(self):
        self.rec.stop()
        self.status_label.config(text="Stopped", fg="#ff5252")

        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="disabled")
        self.btn_stop.config(state="disabled")

    def save_wav(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".wav", filetypes=[("WAV File", "*.wav")]
        )
        if filepath:
            try:
                self.rec.save_wav(filepath)
                messagebox.showinfo("Saved", "WAV file saved successfully.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def save_mp3(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".mp3", filetypes=[("MP3 File", "*.mp3")]
        )
        if filepath:
            try:
                self.rec.save_mp3(filepath)
                messagebox.showinfo("Saved", "MP3 file saved successfully.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # UPDATE LOOP -------------------------------------------------------------

    def _update_ui(self):
        moved = self.rec.collect_from_queue()

        # Add ONLY NEW frames (do not delete old frames)
        if moved > 0:
            new_frames = self.rec.frames[-moved:]
            for arr in new_frames:
                mono = arr.flatten()
                self.wave_deque.extend(mono.tolist())

        # Draw waveform
        samples = np.array(self.wave_deque, dtype=np.float32)

        if samples.size == 0:
            y = np.zeros(MAX_WAVE_SAMPLES)
        else:
            if samples.size < MAX_WAVE_SAMPLES:
                pad = MAX_WAVE_SAMPLES - samples.size
                y = np.concatenate((np.zeros(pad), samples))
            else:
                y = samples[-MAX_WAVE_SAMPLES:]

        x = np.arange(len(y))
        self.line.set_data(x, y)
        self.ax.set_xlim(0, len(y))
        self.canvas.draw()

        # Level meter
        if len(samples) > 0:
            last_n = min(len(samples), CHUNK_SIZE)
            recent = samples[-last_n:].astype(np.float64)
            rms = np.sqrt(np.mean(recent ** 2))
            self.last_level = self.last_level * 0.8 + rms * 0.2
            self.level_var.set(self.last_level)

        # Timer
        if self.rec.recording and self.start_time:
            self.elapsed_seconds = int(time.time() - self.start_time)
            self.timer_label.config(text=str(timedelta(seconds=self.elapsed_seconds)))

        self.samples_label.config(text=f"Samples: {len(self.wave_deque)}")

        # Repeat loop
        self.after(50, self._update_ui)


# RUN APP --------------------------------------------------------------------

if __name__ == "__main__":
    app = VoiceRecorderApp()
    app.mainloop()
