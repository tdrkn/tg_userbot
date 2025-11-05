import asyncio
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import mimetypes
from typing import Optional
import threading
import os
import logging

from dotenv import load_dotenv

# Set environment variables before importing the bot logic
load_dotenv()

# Add a check for GEMINI_MODEL environment variable
if not os.getenv("GEMINI_MODEL"):
    print("Error: GEMINI_MODEL is not set in your .env file. Please set it (e.g., 'gemini-1.5-flash').")
    exit(1)

# Import from the modular package
try:
    from tg_userbot.logging_setup import setup_logging
    from tg_userbot.ai import init_gemini, is_ready, smart_reply
    from tg_userbot.config import PROMPT_TPL, FALLBACK
except ImportError as e:
    print(f"Error importing bot modules: {e}")
    print("Please ensure the 'tg_userbot' package exists and is configured correctly.")
    exit(1)
except Exception as e:
    print(f"An unexpected error occurred during import: {e}")
    exit(1)

# Initialize logging and Gemini for the test app
setup_logging()
init_gemini()


class TestApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bot Test Interface")
        self.geometry("600x600")

        self.image_path: Optional[str] = None
        self.image_data: Optional[bytes] = None
        self.image_mime: Optional[str] = None

        # Post text input
        tk.Label(self, text="Post Text:").pack(pady=(10, 0))
        self.post_text = scrolledtext.ScrolledText(self, height=10, wrap=tk.WORD)
        self.post_text.pack(pady=5, padx=10, fill="x", expand=True)

        # Image selection
        self.image_label = tk.Label(self, text="No image selected.")
        self.image_label.pack(pady=5)
        tk.Button(self, text="Select Image", command=self.select_image).pack(pady=5)

        # Generate button
        tk.Button(self, text="Generate Reply", command=self.run_generate_reply).pack(pady=10)

        # Response display
        tk.Label(self, text="Generated Reply:").pack(pady=(10, 0))
        self.response_text = scrolledtext.ScrolledText(self, height=10, wrap=tk.WORD, state="disabled")
        self.response_text.pack(pady=5, padx=10, fill="x", expand=True)

    def select_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif *.webp")]
        )
        if path:
            self.image_path = path
            self.image_label.config(text=path.split('/')[-1])
            with open(path, "rb") as f:
                self.image_data = f.read()
            self.image_mime = mimetypes.guess_type(path)[0]

    def run_generate_reply(self):
        threading.Thread(target=self._run_async_task, daemon=True).start()

    def _run_async_task(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.generate_reply())
        except Exception as e:
            logging.error(f"An unexpected error occurred in test_app async task: {e}", exc_info=True)
            self.after(0, self.update_response_text, f"An unexpected error occurred in async task: {e}")
        finally:
            loop.close()

    def update_response_text(self, text):
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", tk.END)
        self.response_text.insert(tk.END, text)
        self.response_text.config(state="disabled")

    async def generate_reply(self):
        post_text_content = self.post_text.get("1.0", tk.END).strip()

        if not is_ready():
            messagebox.showerror("Error", "Gemini model is not initialized. Check your GEMINI_KEY in the .env file.")
            return

        self.after(0, self.update_response_text, "Generating...")

        try:
            response = await smart_reply(
                post_text=post_text_content,
                image_data=self.image_data,
                image_mime=self.image_mime
            )
            if not response:
                response = FALLBACK
        except Exception as e:
            response = f"An error occurred: {e}"
            logging.error(f"Error in generate_reply (test_app): {e}", exc_info=True)

        self.after(0, self.update_response_text, response)


if __name__ == "__main__":
    print("Starting test application...")
    app = TestApp()
    app.mainloop()
