import re
import subprocess
import sys
from pathlib import Path

import mido

from midi_shared import MID_DIR, KEYFRAME_INTERVAL
from runner import encode_text, decode_mid

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

def run_test(text, title):
    print("Encoding...")
    enc = encode_text(text, title)
    saved = extract_saved_mid(enc.stdout, title)
    saved_path = MID_DIR / saved
    if not saved_path.exists():
        print("ERROR: saved midi not found:", saved_path)
        print("encoder stdout:", enc.stdout)
        return

    print("Saved:", saved_path)
    note_list = collect_note_on_indices(saved_path)
    if not note_list:
        print("no note_on found in generated mid")
        return

    total_notes = len(note_list)
    print(f"note_on count = {total_notes}")

    # choose test indices relative to KEYFRAME_INTERVAL
    k = KEYFRAME_INTERVAL
    candidates = sorted(set([
        0,
        max(0, k-2),
        max(0, k-1),
        k-0,      # keyframe index as 1-based in encoder; here we use 0-based list index approximate
        k+1,
        total_notes//2,
        total_notes-1
    ]))
    print("Test indices (0-based note_on index):", candidates)

    results = []
    for idx in candidates:
        if idx < 0 or idx >= total_notes:
            continue
        corrupt_name = saved_path.stem + f"_corrupt_idx{idx}.mid"
        corrupt_path = MID_DIR / corrupt_name
        # call simulate_loss.py to delete the note_on (uses --mode indices --param <index>)
        print(f"\n-- simulate loss: removing note_on index {idx} -> {corrupt_path.name}")
        cmd = [sys.executable, "simulate_loss.py", str(saved_path.name), "--mode", "indices", "--param", str(idx), "--out", corrupt_path.name]
        # run in project dir so simulate_loss finds files by name
        p = subprocess.run(cmd, cwd=str(MID_DIR.parent), capture_output=True, text=True)
        if p.returncode != 0:
            print("simulate_loss failed:", p.stderr)
            results.append((idx, "simulate_fail"))
            continue

        # decode corrupt file (pass basename without extension)
        corrupt_basename = Path(corrupt_path).stem
        print("Decoding corrupt:", corrupt_basename)
        dec = decode_mid(corrupt_basename)
        out = dec.stdout or ""
        # check for CRC mismatch messages or SYNC read
        crc_mismatch = "CRC MISMATCH" in out or "CRC MISMATCH!" in out
        sync_lines = [l for l in out.splitlines() if "SYNC" in l and ("READ" in l or "WRITE" in l)]
        # extract復号テキスト
        m = re.search(r"復号テキスト:\s*", out)
        recovered = ""
        if m:
            tail = out[m.end():].lstrip("\r\n")
            sep = re.search(r"\n(?:===|---|\[|MIDI saved:)", tail)
            recovered = tail[:sep.start()].rstrip() if sep else tail.rstrip()
        else:
            # fallback: last non-empty line
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if lines:
                recovered = lines[-1]

        ok = (recovered.strip() == text.strip())
        print(f"index={idx} ok={ok} crc_mismatch={crc_mismatch} sync_hits={len(sync_lines)}")
        results.append((idx, ok, crc_mismatch, len(sync_lines), recovered))
    # summary
    print("\n=== SUMMARY ===")
    for r in results:
        print(r)
    return results

if __name__ == "__main__":
    # adjust test text/title as needed
    sample_text = "Some sample text for testing,but its length is not too long."
    sample_title = "test_keyframe"
    run_test(sample_text, sample_title)
