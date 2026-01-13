import re
import subprocess
import sys
from pathlib import Path
import csv
import time

import mido

from midi_shared import MID_DIR
from runner import encode_text, decode_mid

OUT_DIR = Path("results")
OUT_DIR.mkdir(exist_ok=True)

def extract_saved_mid(stdout, fallback):
    m = re.search(r"MIDI saved:\s*(?:mid/)?([^\s]+\.mid)", stdout)
    if m:
        return m.group(1)
    return f"{fallback}.mid"

def collect_note_on_indices(mid_path):
    mid = mido.MidiFile(mid_path)
    lst = []
    for ti, track in enumerate(mid.tracks):
        for mi, msg in enumerate(track):
            if getattr(msg, "type", None) == "note_on" and getattr(msg, "velocity", 0) > 0:
                lst.append((ti, mi))
    return lst

def extract_decoded_text(dec_stdout):
    # try marker
    m = re.search(r"復号テキスト:\s*", dec_stdout)
    if m:
        tail = dec_stdout[m.end():].lstrip("\r\n")
        sep = re.search(r"\n(?:===|---|\[|MIDI saved:)", tail)
        if sep:
            return tail[:sep.start()].rstrip()
        return tail.rstrip()
    # fallback last non-empty line
    lines = [l.strip() for l in (dec_stdout or "").splitlines() if l.strip()]
    return lines[-1] if lines else ""

def analyze_decode_stdout(dec):
    out = dec.stdout or ""
    crc_mismatch = bool(re.search(r"CRC MISMATCH", out))
    sync_hits = len([l for l in out.splitlines() if "SYNC" in l and ("READ" in l or "WRITE" in l)])
    return crc_mismatch, sync_hits, out

def run_all(text, title):
    print("Encoding...")
    enc = encode_text(text, title)
    saved = extract_saved_mid(enc.stdout, title)
    saved_path = MID_DIR / saved
    if not saved_path.exists():
        print("ERROR: saved midi not found:", saved_path)
        print("encoder stdout:", enc.stdout)
        return

    note_list = collect_note_on_indices(saved_path)
    total = len(note_list)
    print(f"Saved: {saved_path} note_on count = {total}")

    csv_path = OUT_DIR / f"{title}_keyframe_resilience_{int(time.time())}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index","total_notes","ok","crc_mismatch","sync_hits","recovered_len","recovered_preview","dec_returncode","enc_saved","corrupt_file"])
        for idx in range(total):
            corrupt_name = saved_path.stem + f"_corrupt_idx{idx}.mid"
            corrupt_path = MID_DIR / corrupt_name
            cmd = [sys.executable, "simulate_loss.py", str(saved_path.name), "--mode", "indices", "--param", str(idx), "--out", corrupt_path.name]
            p = subprocess.run(cmd, cwd=str(MID_DIR.parent), capture_output=True, text=True)
            if p.returncode != 0:
                print(f"simulate_loss failed for idx={idx}:", p.stderr.strip())
                writer.writerow([idx,total,"simulate_fail","","","",p.stderr.strip(),saved_path.name,""])
                continue

            corrupt_basename = corrupt_path.stem
            dec = decode_mid(corrupt_basename)
            crc_mismatch, sync_hits, dec_out = analyze_decode_stdout(dec)
            recovered = extract_decoded_text(dec_out)
            ok = (recovered.strip() == text.strip())
            preview = (recovered[:120].replace("\n","\\n"))
            print(f"idx={idx} ok={ok} crc_mismatch={crc_mismatch} sync_hits={sync_hits} recovered_len={len(recovered)}")
            writer.writerow([idx,total,ok,crc_mismatch,sync_hits,len(recovered),preview,dec.returncode,saved_path.name,corrupt_path.name])
    print("Finished. CSV:", csv_path)

if __name__ == "__main__":
    sample_text = "Some sample text for testing,but its length is not too long."
    sample_title = "test_keyframe_all"
    run_all(sample_text, sample_title)
