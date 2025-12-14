import tkinter as tk

def show_splash():
    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.configure(bg="#121212")
    splash.geometry("400x200+500+300")

    tk.Label(
        splash, text="🎙 Advanced Voice Recorder",
        fg="white", bg="#121212",
        font=("Segoe UI", 16, "bold")
    ).pack(expand=True)

    splash.after(2000, splash.destroy)
    splash.mainloop()
