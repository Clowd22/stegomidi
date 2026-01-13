# =======================================================
# Adaptive MIDI Encoder (4bit pitch + 2bit duration)
# 確率的対応表を4bitに拡張し、自然なメロディを生成する。
# 音価は2bitで指定され、6bit単位でテキストをエンコード。
# =======================================================

from mido import Message, MidiFile, MidiTrack, MetaMessage
import os

# ---------------------------
# 音階・基準設定
# ---------------------------
NOTE_NAMES = ["G3", "A3", "B3", "C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
NOTE_TO_MIDI = {
    "G3": 55, "A3": 57, "B3": 59,
    "C4": 60, "D4": 62, "E4": 64, "F4": 65,
    "G4": 67, "A4": 69, "B4": 71, "C5": 72
}

RELATIVE_WEIGHTS = [1, 2, 3, 3, 3, 2, 1, 1]

DURATION_TABLE = {
    "00": 480,
    "01": 240,
    "10": 960,
    "11": 720
}

# KEYFRAME を 20 音ごとに挿入する
KEYFRAME_INTERVAL = 20
BASE_VELOCITY = 80   # ベースベロシティ（slot_index を加算して 80..83 の範囲にする）

# --- キーフレーズ ---
KEYFRAME_PHRASE = [
    ("D4", 240),   # 8分
    ("E4", 240),   # 8分
    ("A4", 240),   # 8分
    ("A3", 240)    # 8分
]
KEYFRAME_VELOCITY = 80  # 0ベースに合わせてキーフレーズは80で統一（slot offset と同じ基準）

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
    # 決定論的に NOTE_NAMES 順で割当
    for note in NOTE_NAMES:
        prob = prob_table.get(note, 0)
        if prob <= 0:
            continue
        count = max(1, round(prob * 16))
        notes.extend([note] * count)
    # ここでの埋め草を「最も確率の高い音」で埋める（安定化）
    if notes:
        most_probable = max(prob_table.items(), key=lambda kv: kv[1])[0]
    else:
        # 万一 prob_table が空なら中心の音（従来の挙動に近い）
        most_probable = NOTE_NAMES[len(NOTE_NAMES)//2]
    while len(notes) < 16:
        notes.append(most_probable)
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

def hamming_encode_4bits(nibble):
    # 削除: ハミングを使わない前提のため未使用。ただし残す場合はコメントアウトするか削除可。
    d1, d2, d3, d4 = (int(x) for x in nibble)
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p4 = d2 ^ d3 ^ d4
    return f"{p1}{p2}{d1}{p4}{d2}{d3}{d4}"

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

def main():
    text = input("Enter text to encode in MIDI: ")
    title = input("Enter title for MIDI data: ")

    binary_data = ''.join(f'{ord(c):08b}' for c in text)
    chunks = [binary_data[i:i+6].ljust(6, '0') for i in range(0, len(binary_data), 6)]

    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)

    prev_note = "C4"
    block_bits = ""
    notes_since_keyframe = 0
    print("\n=== Adaptive MIDI Encoding (verbose) ===")

    for step, chunk in enumerate(chunks, 1):
        pitch_bits = chunk[:4]
        dur_bits = chunk[4:]

        # ハミングは行わない: pitch_bits をそのまま対応表のキーとして使う
        pitch_bits_for_map = pitch_bits
        parity_bits = ""  # 未使用

        prob_table = make_probability_table(prev_note)
        mapping = make_mapping_from_prob_table(prob_table)

        # スロット位置（同音の候補内での位置）を求める（表示用）
        candidates = [b for b, n in mapping.items() if n == mapping[pitch_bits_for_map]]
        candidates.sort(key=lambda x: int(x,2))
        try:
            slot_index = candidates.index(pitch_bits_for_map)
        except ValueError:
            slot_index = 0

        # 表示
        print_mapping_verbose(prob_table, mapping, step, prev_note, chunk, pitch_bits_for_map, slot_index)

        note_name = mapping[pitch_bits_for_map]
        duration = DURATION_TABLE[dur_bits]

        # velocity に BASE_VELOCITY + slot_index を保存（復号で slot を復元する）
        new_velocity = BASE_VELOCITY + slot_index
        if new_velocity > 127:
            new_velocity = 127

        note_num = NOTE_TO_MIDI[note_name]
        # ノートを書き出したらカウント
        track.append(Message('note_on', note=note_num, velocity=new_velocity, time=0))
        track.append(Message('note_off', note=note_num, velocity=0, time=duration))

        notes_since_keyframe += 1

        # ブロック用に追加（エンコードされるビットは元の pitch_bits + dur_bits）
        block_bits += pitch_bits + dur_bits

        # 20 音に到達したときのみキーフレームを挿入（到達未満なら挿入しない）
        if notes_since_keyframe >= KEYFRAME_INTERVAL:
            # 直前ブロックの CRC を計算して SYNC とともに書き出す
            crc = crc8_bits(block_bits)
            # キーフレーズを挿入
            for k_note, k_dur in KEYFRAME_PHRASE:
                if k_note not in NOTE_TO_MIDI:
                    continue
                k_num = NOTE_TO_MIDI[k_note]
                track.append(Message('note_on', note=k_num, velocity=KEYFRAME_VELOCITY, time=0))
                track.append(Message('note_off', note=k_num, velocity=0, time=k_dur))
            # キーフレームの最後の音名を SYNC に含め、ブロック CRC を通知
            last_note = KEYFRAME_PHRASE[-1][0] if KEYFRAME_PHRASE else note_name
            sync_text = f"SYNC:{step}:{last_note}:{crc:02X}"
            track.append(MetaMessage('text', text=sync_text, time=0))
            print(f"[SYNC+KEYFRAME WRITE] step={step} block_bits_len={len(block_bits)} crc={crc:02X} keyframe_last={last_note} text='{sync_text}'")
            # リセット
            block_bits = ""
            notes_since_keyframe = 0

        prev_note = note_name

    output_dir = "mid"
    os.makedirs(output_dir, exist_ok=True)
    output_filename = os.path.join(output_dir, f"{title}_deterministic.mid")
    mid.save(output_filename)
    print(f"\nMIDI saved: {output_filename}")

if __name__ == "__main__":
    import sys
    from contextlib import redirect_stdout

    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, s):
            for st in self.streams:
                st.write(s)
        def flush(self):
            for st in self.streams:
                try:
                    st.flush()
                except:
                    pass

    out_path = "output_encode.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        tee = Tee(sys.stdout, f)
        with redirect_stdout(tee):
            try:
                main()
            except Exception as e:
                # 例外は両方に出力される
                print("ERROR:", e)


