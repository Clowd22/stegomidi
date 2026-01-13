# 共通定義・パス
from pathlib import Path
import os

ROOT = Path(__file__).parent
MID_DIR = ROOT / "mid"
ARTIFACTS_DIR = ROOT / "artifacts"
ENCODERS_DIR = ROOT

MID_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR.mkdir(exist_ok=True)

ENCODER_SCRIPT = "makemidi_adaptive_timeshift.py"
DECODER_SCRIPT = "decode_adaptive_timeshift_decode.py"

SAMPLE_TEXTS = [
    "Hello",
    "The quick brown fox jumps over the lazy dog",
    "Some sample text for testing,but its length is not too long.",
    "これは日本語のテストです。",
    "短い",
    # 長いサンプルは必要に応じてここに入れる
    "日本国民は、正当に選挙された国会における代表者を通じて行動し、われらとわれらの子孫のために、諸国民との協和による成果と、わが国全土にわたつて自由のもたらす恵沢を確保し、政府の行為によつて再び戦争の惨禍が起ることのないやうにすることを決意し、ここに主権が国民に存することを宣言し、この憲法を確定する。",
    "Emoji test 👍🚀🎵",
]

def script_path(name: str):
    return str((ROOT / name).resolve())

# 共有: ノート名・MIDI番号・設定・確率テーブル・CRC等
NOTE_NAMES = ["G3", "A3", "B3", "C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]

# 元の実装で使っていた値に対して +12 （1オクターブ上げる）
NOTE_TO_MIDI = {
    "G3": 55 + 12, "A3": 57 + 12, "B3": 59 + 12,
    "C4": 60 + 12, "D4": 62 + 12, "E4": 64 + 12, "F4": 65 + 12,
    "G4": 67 + 12, "A4": 69 + 12, "B4": 71 + 12, "C5": 72 + 12
}

RELATIVE_WEIGHTS = [1, 2, 3, 3, 3, 2, 1, 1]

DURATION_TABLE = {
    "00": 480,
    "01": 240,
    "10": 960,
    "11": 720
}

KEYFRAME_INTERVAL = 20
BASE_VELOCITY = 80
KEYFRAME_PHRASE = [
    ("D4", 240), ("E4", 240), ("A4", 240), ("A3", 240)
]
KEYFRAME_VELOCITY = BASE_VELOCITY
KEYFRAME_DURATION_SHIFT = 1  # ticks

def make_probability_table(prev_note):
    if prev_note not in NOTE_NAMES:
        prev_note = "C4"
    center_index = NOTE_NAMES.index(prev_note)
    prob_table = {}
    for offset, weight in enumerate(RELATIVE_WEIGHTS):
        rel_idx = offset - 3
        target_index = center_index + rel_idx
        if 0 <= target_index < len(NOTE_NAMES):
            note = NOTE_NAMES[target_index]
            prob_table[note] = prob_table.get(note, 0) + weight
    total = sum(prob_table.values()) or 1
    for k in list(prob_table.keys()):
        prob_table[k] = prob_table[k] / total
    return prob_table

def make_mapping_from_prob_table(prob_table):
    notes = []
    keys = list(prob_table.keys())
    if not keys:
        # fallback: use NOTE_NAMES center
        keys = NOTE_NAMES[:]
    for note in NOTE_NAMES:
        prob = prob_table.get(note, 0)
        if prob <= 0:
            continue
        count = max(1, round(prob * 16))
        notes.extend([note] * count)
    while len(notes) < 16:
        notes.append(keys[len(notes) % len(keys)])
    notes = notes[:16]
    return {format(i, '04b'): notes[i] for i in range(16)}

def print_mapping_verbose(prob_table, mapping, step, prev_note, chunk, pitch_bits_for_map, slot_index):
    print("\n--- ENCODE STEP (詳細) ---")
    print(f"Step {step} | prev_note={prev_note} | input_chunk={chunk} (pitch={chunk[:4]} dur={chunk[4:]})")
    print("確率分布:")
    for n, p in prob_table.items():
        print(f"  {n:<3}: {p:.4f} {'█'*int(p*40)}")
    print("4bit -> 音 のマッピング (index順):")
    for bits in sorted(mapping.keys(), key=lambda x: int(x,2)):
        mark = "<-- selected" if bits == pitch_bits_for_map else ""
        print(f"  {bits} -> {mapping[bits]:4s} {mark}")
    print(f"pitch_bits_for_map={pitch_bits_for_map} slot_index={slot_index}")

def crc8_bits(bitstr):
    if len(bitstr) % 8 != 0:
        bitstr = bitstr + '0' * (8 - (len(bitstr) % 8))
    data = [int(bitstr[i:i+8], 2) for i in range(0, len(bitstr), 8)]
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) & 0xFF) ^ 0x07
            else:
                crc = (crc << 1) & 0xFF
    return crc
