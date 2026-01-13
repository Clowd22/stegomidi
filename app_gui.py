import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
from pathlib import Path
import re

from midi_shared import MID_DIR, ARTIFACTS_DIR, ENCODER_SCRIPT, DECODER_SCRIPT, KEYFRAME_INTERVAL
from runner import encode_text, decode_mid

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MIDI My Sample — GUI")
        self.geometry("1000x700")
        self._build()

    def _build(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)

        btn_frame = tk.Frame(top)
        btn_frame.pack(side="right")
        tk.Button(btn_frame, text="Open mid folder", command=self.open_mid_folder).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Open artifacts", command=self.open_artifacts).pack(side="left", padx=4)

        body = tk.PanedWindow(self, sashrelief="raised", sashwidth=6, orient="horizontal")
        body.pack(expand=True, fill="both", padx=8, pady=8)

        # --- Encode panel ---
        enc_frame = tk.LabelFrame(body, text="Encode: text → MIDI", padx=6, pady=6)
        body.add(enc_frame, stretch="always")

        tk.Label(enc_frame, text="Title (basename):").grid(row=0, column=0, sticky="w")
        self.enc_title = tk.Entry(enc_frame, width=40)
        self.enc_title.grid(row=0, column=1, sticky="we", padx=4, pady=2)
        self.enc_title.insert(0, "auto_sample_timeshift")

        tk.Label(enc_frame, text="Text to encode:").grid(row=1, column=0, sticky="nw")
        self.enc_text = scrolledtext.ScrolledText(enc_frame, width=60, height=18, wrap="word")
        self.enc_text.grid(row=1, column=1, sticky="nsew", padx=4)
        enc_frame.columnconfigure(1, weight=1)
        # allow the encode log area to expand downward
        enc_frame.rowconfigure(1, weight=1)
        enc_frame.rowconfigure(3, weight=1)

        enc_btn = tk.Button(enc_frame, text="Encode → MIDI", command=self.on_encode)
        enc_btn.grid(row=2, column=1, sticky="e", pady=6)
        # キーフレーム精度チェックボタン
        chk_btn = tk.Button(enc_frame, text="Check Keyframes", command=self.on_check_keyframes)
        chk_btn.grid(row=2, column=0, sticky="w", padx=(0,6))

        # larger log area for encoder
        self.enc_out = scrolledtext.ScrolledText(enc_frame, height=14, wrap="word", state="disabled")
        self.enc_out.grid(row=3, column=0, columnspan=2, sticky="we", pady=(4,0))

        # --- Decode panel ---
        dec_frame = tk.LabelFrame(body, text="Decode: MIDI → text", padx=6, pady=6)
        body.add(dec_frame, stretch="always")

        tk.Label(dec_frame, text="MIDI file (.mid):").grid(row=0, column=0, sticky="w")
        self.dec_mid_path = tk.Entry(dec_frame, width=50)
        self.dec_mid_path.grid(row=0, column=1, sticky="we", padx=4)
        tk.Button(dec_frame, text="Browse", command=self.browse_mid).grid(row=0, column=2, padx=4)

        dec_btn = tk.Button(dec_frame, text="Decode → Text", command=self.on_decode)
        dec_btn.grid(row=1, column=2, sticky="e", pady=6)

        tk.Label(dec_frame, text="Decoded text:").grid(row=1, column=0, sticky="nw")
        self.dec_text = scrolledtext.ScrolledText(dec_frame, width=60, height=12, wrap="word")
        self.dec_text.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=4)
        dec_frame.columnconfigure(1, weight=1)
        # allow decoded text area and log area to expand
        dec_frame.rowconfigure(2, weight=1)
        dec_frame.rowconfigure(3, weight=1)
        # larger log area for decoder
        self.dec_out = scrolledtext.ScrolledText(dec_frame, height=14, wrap="word", state="disabled")
        self.dec_out.grid(row=3, column=0, columnspan=3, sticky="we", pady=(4,0))

    def log_to_widget(self, widget, text):
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def open_mid_folder(self):
        p = MID_DIR.resolve()
        if not p.exists():
            messagebox.showwarning("Open mid folder", f"{p} が存在しません")
            return
        import subprocess
        subprocess.run(["open", str(p)])

    def open_artifacts(self):
        p = ARTIFACTS_DIR.resolve()
        if not p.exists():
            messagebox.showwarning("Open artifacts", f"{p} が存在しません")
            return
        import subprocess
        subprocess.run(["open", str(p)])

    def browse_mid(self):
        p = filedialog.askopenfilename(initialdir=str(MID_DIR.resolve()),
                                       filetypes=[("MIDI files","*.mid"),("All files","*.*")])
        if p:
            self.dec_mid_path.delete(0, "end")
            self.dec_mid_path.insert(0, p)

    def _extract_saved_mid(self, stdout, fallback):
        m = re.search(r"MIDI saved:\s*(?:mid/)?([^\s]+\.mid)", stdout)
        if m:
            return m.group(1)
        return f"{fallback}.mid"

    def on_encode(self):
        title = self.enc_title.get().strip()
        text = self.enc_text.get("1.0", "end").rstrip("\n")
        if not text:
            messagebox.showwarning("Encode", "テキストを入力してください。")
            return
        self.enc_out.configure(state="normal")
        self.enc_out.delete("1.0", "end")
        # symmetric, verbose format
        self.log_to_widget(self.enc_out, "=== ENCODER ===")
        self.log_to_widget(self.enc_out, "Running encoder...")
        enc = encode_text(text, title)
        self.log_to_widget(self.enc_out, f"[returncode={enc.returncode}]")
        self.log_to_widget(self.enc_out, "=== STDOUT ===")
        if enc.stdout:
            self.log_to_widget(self.enc_out, enc.stdout)
        self.log_to_widget(self.enc_out, "=== STDERR ===")
        if enc.stderr:
            self.log_to_widget(self.enc_out, enc.stderr)
        self.log_to_widget(self.enc_out, "=== END ===")

        saved = self._extract_saved_mid(enc.stdout, title)
        mid_path = MID_DIR / saved
        if mid_path.exists():
            messagebox.showinfo("Encode", f"MIDI saved: {mid_path}")
        else:
            messagebox.showwarning("Encode", "MIDI が見つかりません。ログを確認してください。")

    def on_decode(self):
        p = self.dec_mid_path.get().strip()
        if not p:
            messagebox.showwarning("Decode", "MIDIファイルを選択してください。")
            return
        # allow full path or basename
        mid_path = Path(p)
        basename = mid_path.stem
        self.dec_out.configure(state="normal")
        self.dec_out.delete("1.0", "end")
        # symmetric, verbose format
        self.log_to_widget(self.dec_out, "=== DECODER ===")
        self.log_to_widget(self.dec_out, f"Decoding {p} ...")
        dec = decode_mid(basename)
        self.log_to_widget(self.dec_out, f"[returncode={dec.returncode}]")
        self.log_to_widget(self.dec_out, "=== STDOUT ===")
        if dec.stdout:
            self.log_to_widget(self.dec_out, dec.stdout)
        self.log_to_widget(self.dec_out, "=== STDERR ===")
        if dec.stderr:
            self.log_to_widget(self.dec_out, dec.stderr)
        self.log_to_widget(self.dec_out, "=== END ===")

        # try to extract decoded text
        # マーカー "復号テキスト:" の後ろ全てを復元テキストとする（改行を含む）
        text = ""
        m = re.search(r"復号テキスト:\s*", dec.stdout)
        if m:
            # マーカー直後から末尾までを取得
            text_tail = dec.stdout[m.end():]
            # 先頭の空行を除去
            text_tail = text_tail.lstrip("\r\n")
            # 後続のログ等が続く場合に備え、よくあるセパレータで切り取る
            sep = re.search(r"\n(?:===|---|\[|MIDI saved:)", text_tail)
            if sep:
                text = text_tail[:sep.start()].rstrip()
            else:
                text = text_tail.rstrip()
        else:
            lines = [l.rstrip() for l in dec.stdout.splitlines() if l.strip()]
            text = lines[-1] if lines else ""
        self.dec_text.delete("1.0", "end")
        self.dec_text.insert("1.0", text)
        messagebox.showinfo("Decode", "復号処理が完了しました。")

    def on_check_keyframes(self):
        title = self.enc_title.get().strip()
        text = self.enc_text.get("1.0", "end").rstrip("\n")
        if not text:
            messagebox.showwarning("Check Keyframes", "テキストを入力してください。")
            return
        self.enc_out.configure(state="normal")
        self.enc_out.delete("1.0", "end")
        self.log_to_widget(self.enc_out, "=== KEYFRAME CHECK (ENCODER RUN) ===")
        self.log_to_widget(self.enc_out, "Running encoder for keyframe check...")
        enc = encode_text(text, title)
        self.log_to_widget(self.enc_out, f"[returncode={enc.returncode}]")
        if enc.stdout:
            self.log_to_widget(self.enc_out, enc.stdout)
        if enc.stderr:
            self.log_to_widget(self.enc_out, "=== STDERR ===")
            self.log_to_widget(self.enc_out, enc.stderr)

        # parse SYNC write lines
        sync_lines = []
        for line in (enc.stdout or "").splitlines():
            if "SYNC(timeshift) WRITE" in line or line.strip().startswith("[SYNC(timeshift) WRITE]"):
                sync_lines.append(line.strip())

        expected_bits = KEYFRAME_INTERVAL * 6
        ok_count = 0
        bad_count = 0
        lens = []
        for s in sync_lines:
            m = re.search(r"step=(\d+)\s+block_bits_len=(\d+)\s+crc=([0-9A-Fa-f]{2})", s)
            if m:
                step = int(m.group(1))
                blen = int(m.group(2))
                crc = m.group(3)
                lens.append(blen)
                if blen == expected_bits:
                    ok_count += 1
                else:
                    bad_count += 1

        # summary
        self.log_to_widget(self.enc_out, "=== KEYFRAME CHECK SUMMARY ===")
        self.log_to_widget(self.enc_out, f"found_sync_count={len(sync_lines)} expected_bits_per_block={expected_bits}")
        if lens:
            self.log_to_widget(self.enc_out, f"block_bits_len_min={min(lens)} max={max(lens)} avg={sum(lens)/len(lens):.1f}")
        self.log_to_widget(self.enc_out, f"ok_blocks={ok_count} bad_blocks={bad_count}")
        if bad_count > 0:
            self.log_to_widget(self.enc_out, "Note: 不一致があるブロックはエンコードロジックや DURATION_TABLE/KEYFRAME_DURATION_SHIFT の影響を確認してください。")
        self.log_to_widget(self.enc_out, "=== END KEYFRAME CHECK ===")
        self.enc_out.configure(state="disabled")

if __name__ == "__main__":
    App().mainloop()
