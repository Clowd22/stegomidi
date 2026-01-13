from mido import MidiFile
import os

# --- 設定（エンコードと一致させること） ---
NOTE_NAMES = ["G3", "A3", "B3", "C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
NOTE_TO_MIDI = {
    "G3": 55, "A3": 57, "B3": 59,
    "C4": 60, "D4": 62, "E4": 64, "F4": 65,
    "G4": 67, "A4": 69, "B4": 71, "C5": 72
}
MIDI_TO_NOTE = {v: k for k, v in NOTE_TO_MIDI.items()}

RELATIVE_WEIGHTS = [1, 2, 3, 3, 3, 2, 1, 1]  # -3..+4

DURATION_TABLE = {
    "00": 480,   # 4分音符
    "01": 240,   # 8分音符
    "10": 960,   # 2分音符
    "11": 720    # 付点4分音符
}

# キーフレーム間隔（エンコーダと一致）
KEYFRAME_INTERVAL = 20
BASE_VELOCITY = 80
KEYFRAME_VELOCITY = 80  # エンコーダと一致（0ベース）
KEYFRAME_DURATION_SHIFT = 1  # timeshift エンコーダと一致（20音目の duration を +1）

# キーフレーズ（エンコーダと一致）
KEYFRAME_PHRASE = [
    ("D4", 240),   # 8分
    ("E4", 240),   # 8分
    ("A4", 240),   # 8分
    ("A3", 240)    # 8分
]

# --- キーフレーズ検出ヘルパ ---
def find_keyframe_block(all_msgs, start_idx):
    """
    start_idx にキーフレーズ先頭の note_on があるかを判定（time は無視）。
    - start_idx 以降に KEYFRAME_PHRASE と同じ音列が順に note_on（かつ velocity == KEYFRAME_VELOCITY）で現れる
    - 最後の音の直後に "SYNC:" テキストがあればキーフレーム
    見つかれば (skip_set, sync_index, sync_text) を返す。見つからなければ None を返す。
    """
    if not KEYFRAME_PHRASE:
        return None
    msg_len = len(all_msgs)
    needed = [NOTE_TO_MIDI[n] for n, _ in KEYFRAME_PHRASE]
    found_on_idxs = []
    i = start_idx
    # note_on を順に集める（間に note_off や delta-time が入ってもよいが、text が出たら中断）
    while i < msg_len and len(found_on_idxs) < len(needed):
        m = all_msgs[i]
        if getattr(m, "type", None) == "note_on" and getattr(m, "velocity", None) == KEYFRAME_VELOCITY:
            found_on_idxs.append(i)
        elif getattr(m, "type", None) == "text":
            # text が挟まるとキーフレーズではないとみなす（SYNC と混同しないため）
            return None
        i += 1
    if len(found_on_idxs) != len(needed):
        return None
    # ノート番号が期待どおりか確認
    for idx, expect in zip(found_on_idxs, needed):
        if getattr(all_msgs[idx], "note", None) != expect:
            return None
    # 対応する note_off（または note_on vel=0）があれば収集（なくても可）
    off_indices = []
    for on_idx in found_on_idxs:
        note_num = getattr(all_msgs[on_idx], "note", None)
        off_idx = None
        for j in range(on_idx + 1, min(on_idx + 1 + 64, msg_len)):
            mm = all_msgs[j]
            if (getattr(mm, "type", None) == "note_off" and getattr(mm, "note", None) == note_num) or \
               (getattr(mm, "type", None) == "note_on" and getattr(mm, "velocity", 0) == 0 and getattr(mm, "note", None) == note_num):
                off_idx = j
                break
        if off_idx is not None:
            off_indices.append(off_idx)
    last_off = off_indices[-1] if off_indices else found_on_idxs[-1]
    # last_off の直後に SYNC テキストがあるか探す（余裕をもって64メッセージ以内）
    for t in range(last_off + 1, min(last_off + 1 + 64, msg_len)):
        mt = all_msgs[t]
        if getattr(mt, "type", None) == "text" and isinstance(getattr(mt, "text", None), str) and mt.text.startswith("SYNC:"):
            skip_set = set(found_on_idxs) | set(off_indices)
            return skip_set, t, mt.text
    return None

# --- 前の音から確率分布を生成  ---
def make_probability_table(prev_note):
    """prev_note を中心に -3..+4 の重みを割り当て正規化した確率表を返す"""
    if prev_note not in NOTE_NAMES:
        prev_note = "C4"
    center_index = NOTE_NAMES.index(prev_note)
    prob_table = {}
    for offset, weight in enumerate(RELATIVE_WEIGHTS):
        rel_idx = offset - 3  # -3..+4
        target_index = center_index + rel_idx
        if 0 <= target_index < len(NOTE_NAMES):
            note = NOTE_NAMES[target_index]
            prob_table[note] = prob_table.get(note, 0) + weight
    total = sum(prob_table.values()) or 1
    for k in list(prob_table.keys()):
        prob_table[k] = prob_table[k] / total
    return prob_table


# --- 確率分布から対応表（4bit）を生成 ---
def make_mapping_from_prob_table(prob_table):
    # makemidi と同じ deterministic 実装に置換
    notes = []
    for note in NOTE_NAMES:
        prob = prob_table.get(note, 0)
        if prob <= 0:
            continue
        count = max(1, round(prob * 16))
        notes.extend([note] * count)
    # 埋め草を最も確率の高い音で埋める（エンコーダと一致させる）
    if notes:
        most_probable = max(prob_table.items(), key=lambda kv: kv[1])[0]
    else:
        most_probable = NOTE_NAMES[len(NOTE_NAMES)//2]
    while len(notes) < 16:
        notes.append(most_probable)
    notes = notes[:16]
    return {format(i, '04b'): notes[i] for i in range(16)}


# --- ベロシティで音スロットを選択（エンコーダと一致） ---
def select_slot_from_velocity(note_name, mapping, velocity):
    """
    mapping 内で note_name に対応するビット候補を取得し、
    velocity - BASE_VELOCITY を slot_index と見なして候補を選ぶ。
    """
    candidates = [bits for bits, n in mapping.items() if n == note_name]
    candidates.sort(key=lambda x: int(x, 2))
    if not candidates:
        return None
    vel_index = velocity - BASE_VELOCITY
    if vel_index < 0:
        vel_index = 0
    idx = vel_index % len(candidates)
    return candidates[idx]


# --- デバッグ出力 ---
def print_table(prob_table, mapping, step, prev_note, note_name, duration_ticks, velocity, selected_bits):
    print(f"\n[Step {step}] 前の音: {prev_note} → 現在の音: {note_name} (duration: {duration_ticks}, velocity: {velocity})")
    print("確率分布:")
    for n, p in prob_table.items():
        print(f"  {n:<3}: {p:.3f} {'█'*int(p*40)}")
    print("対応表（4bit→音）:")
    for bits, n in mapping.items():
        mark = "◀" if bits == selected_bits else " "
        print(f"  {bits} → {n} {mark}")
    if selected_bits:
        print(f"→ ベロシティ下位2bit に基づき選択されたスロット: {selected_bits} ({note_name})")

# --- Hamming(7,4) 復号ヘルパ ---
def hamming_decode_7bits(bits7):
    """
    bits7: 'b1b2b3b4b5b6b7' (文字列)
    返回: (corrected_7bit_str, data4bit_str, error_pos)
    """
    b = [0] + [int(x) for x in bits7]  # 1-indexed
    s1 = b[1] ^ b[3] ^ b[5] ^ b[7]
    s2 = b[2] ^ b[3] ^ b[6] ^ b[7]
    s3 = b[4] ^ b[5] ^ b[6] ^ b[7]
    syndrome = s1 + (s2 << 1) + (s3 << 2)  # 1..7 or 0
    if syndrome != 0 and 1 <= syndrome <= 7:
        b[syndrome] ^= 1  # エラー訂正（1ビット）
        error_pos = syndrome
    else:
        error_pos = 0
    corrected = ''.join(str(x) for x in b[1:])
    # data bits are positions 3,5,6,7
    data4 = f"{b[3]}{b[5]}{b[6]}{b[7]}"
    return corrected, data4, error_pos

def crc8_bits(bitstr):
    """encoder と同じ CRC-8 実装"""
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

def dump_all_msgs(mid):
    """デバッグ: 全メッセージを一覧出力（index, type, note, vel, time, text）"""
    i = 0
    for ti, track in enumerate(mid.tracks):
        abs_t = 0
        print(f"--- Track {ti} ---")
        for msg in track:
            abs_t += getattr(msg, "time", 0)
            if getattr(msg, "type", None) == "text":
                print(f"{i:04d} TEXT  time={abs_t} text={msg.text}")
            else:
                print(f"{i:04d} {getattr(msg,'type', ''):6s} note={getattr(msg,'note', '')} vel={getattr(msg,'velocity', '')} time={abs_t}")
            i += 1

# --- メイン処理 ---
def main():
    name = input("解析するMIDIファイル名を入力してください（拡張子 .mid は不要）: ")
    path = os.path.join("mid", f"{name}.mid")
    if not os.path.exists(path):
        print(f"ファイルが見つかりません: {path}")
        return

    mid = MidiFile(path)
    prev_note = "C4"
    step = 1
    bit_string = ""

    # 全メッセージをまとめる（相対time を保持）
    all_msgs = []
    for track in mid.tracks:
        all_msgs.extend(track)
    msg_len = len(all_msgs)

    block_bits_accum = ""  # ブロックCRC用蓄積
    skip_indices = set()
    idx_msg = 0
    while idx_msg < msg_len:
        msg = all_msgs[idx_msg]

        # キーフレーズ（KEYFRAME_PHRASE）検出：velocity が KEYFRAME_VELOCITY の note_on を起点に探す
        if idx_msg not in skip_indices and getattr(msg, "type", None) == "note_on" and getattr(msg, "velocity", None) == KEYFRAME_VELOCITY:
            res = find_keyframe_block(all_msgs, idx_msg)
            if res is not None:
                skip_set, sync_idx, sync_text = res
                # SYNC を解析してブロック検証（存在すれば CRC を照合）
                parts = sync_text.split(":", 3)
                if len(parts) >= 4:
                    _, s_step, s_note, s_crc = parts
                    print(f"[Keyframe+SYNC READ] step={s_step} prev_note を {s_note} に同期、reported_crc={s_crc}")
                    actual_crc = crc8_bits(block_bits_accum)
                    try:
                        reported_crc = int(s_crc, 16)
                    except:
                        reported_crc = None
                    print(f"  block_bits_len={len(block_bits_accum)} actual_crc={actual_crc:02X}")
                    if reported_crc is not None and actual_crc != reported_crc:
                        print(f"  CRC MISMATCH! reported={reported_crc:02X} actual={actual_crc:02X}")
                    elif reported_crc is not None:
                        print("  CRC OK")
                # キーフレーズはデータではないので復元対象から除外し、prev_note を同期して蓄積をリセット
                prev_note = KEYFRAME_PHRASE[-1][0] if KEYFRAME_PHRASE else prev_note
                block_bits_accum = ""
                # スキップ対象を登録（note_on, 対応する note_off, SYNC）
                for si in skip_set:
                    skip_indices.add(si)
                skip_indices.add(sync_idx)
                idx_msg = sync_idx + 1
                continue

        if idx_msg in skip_indices:
            idx_msg += 1
            continue

        # only process note_on with velocity>0
        if getattr(msg, "type", None) != "note_on" or getattr(msg, "velocity", 0) == 0:
            idx_msg += 1
            continue

        # --- duration の検出 ---
        dur_ticks = 0
        off_idx = None
        note_num = getattr(msg, "note", None)
        for j in range(idx_msg + 1, msg_len):
            mm = all_msgs[j]
            dur_ticks += getattr(mm, "time", 0)
            if (getattr(mm, "type", None) == "note_off" and getattr(mm, "note", None) == note_num) or \
               (getattr(mm, "type", None) == "note_on" and getattr(mm, "velocity", 0) == 0 and getattr(mm, "note", None) == note_num):
                off_idx = j
                break

        velocity = getattr(msg, "velocity", 0)
        note_name = MIDI_TO_NOTE.get(note_num)
        if note_name is None:
            idx_msg += 1
            continue

        # reconstruct mapping and select slot
        prob_table = make_probability_table(prev_note)
        mapping = make_mapping_from_prob_table(prob_table)
        selected_bits = select_slot_from_velocity(note_name, mapping, velocity)
        if selected_bits is None:
            print(f"[Step {step}] slot 選択失敗: note_name={note_name}")
            idx_msg += 1
            continue
        data4 = selected_bits

        # round duration to nearest 2bit code
        closest = min(DURATION_TABLE.items(), key=lambda kv: abs(kv[1] - dur_ticks))
        dur_bits = closest[0]

        full_bits = data4 + dur_bits
        bit_string += full_bits
        block_bits_accum += full_bits

        # detect keyframe marker by shifted duration (base duration + KEYFRAME_DURATION_SHIFT)
        for code, base_dur in DURATION_TABLE.items():
            if dur_ticks == base_dur + KEYFRAME_DURATION_SHIFT and off_idx is not None:
                # look for SYNC meta after off_idx
                for t in range(off_idx + 1, min(off_idx + 1 + 64, msg_len)):
                    mt = all_msgs[t]
                    if getattr(mt, "type", None) == "text" and isinstance(getattr(mt, "text", None), str) and mt.text.startswith("SYNC:"):
                        parts = mt.text.split(":", 3)
                        if len(parts) >= 4:
                            _, s_step, s_note, s_crc = parts
                            print(f"[Keyframe+SYNC READ] step={s_step} prev_note を {s_note} に同期、reported_crc={s_crc}")
                            actual_crc = crc8_bits(block_bits_accum)
                            try:
                                reported_crc = int(s_crc, 16)
                            except:
                                reported_crc = None
                            print(f"  block_bits_len={len(block_bits_accum)} actual_crc={actual_crc:02X}")
                            if reported_crc is not None and actual_crc != reported_crc:
                                print(f"  CRC MISMATCH! reported={reported_crc:02X} actual={actual_crc:02X}")
                            elif reported_crc is not None:
                                print("  CRC OK")
                        # consume SYNC
                        skip_indices.add(t)
                        # synchronize prev_note
                        try:
                            prev_note = s_note
                        except:
                            prev_note = note_name
                        block_bits_accum = ""
                        break
                break

        print(f"[Step {step}] decoded note={note_name} dur={dur_ticks} vel={velocity} -> bits={full_bits}")
        prev_note = note_name
        step += 1
        idx_msg += 1

    # パディングは行わず、末尾の未満ビットは切り捨てて復号（元データは6bit単位なので切り捨てが発生することがある）
    usable_len = len(bit_string) - (len(bit_string) % 8)
    if usable_len != len(bit_string):
        dropped = len(bit_string) - usable_len
        print(f"[INFO] 末尾の不完全なビットを{dropped}個切り捨てて復号します")
    bytes_list = [int(bit_string[i:i+8], 2) for i in range(0, usable_len, 8)]
    try:
        text = bytes(bytes_list).decode('utf-8', errors='ignore')
    except Exception:
        text = "".join(chr(b) for b in bytes_list)

    print("\n=== デコード結果 ===")
    print(f"復号ビット列: {bit_string}")
    print(f"復号テキスト: {text}")


# --- デバッグ出力の制御 ---
VERBOSE = True

def print_decode_verbose(prob_table, mapping, step, prev_note, note_name, duration_ticks, vel, data4, dur_bits, block_bits_accum):
    """各ステップの詳細表示（VERBOSE=True のとき有効）"""
    if not VERBOSE:
        return
    print("\n--- DECODE STEP (詳細) ---")
    print(f"Step {step} | prev_note={prev_note} | midi_note={note_name} | duration_ticks={duration_ticks} | velocity={vel}")
    print(f"selected data4 = {data4} | dur_bits = {dur_bits}")
    print("確率分布 (prev_note を基準):")
    for n, p in prob_table.items():
        bar = '█' * int(p * 40)
        print(f"  {n:<3}: {p:.4f} {bar}")
    print("4bit -> 音 のマッピング (index順):")
    for bits in sorted(mapping.keys(), key=lambda x: int(x, 2)):
        mapped = mapping[bits]
        mark = "<-- decoded" if bits == data4 else ""
        print(f"  {bits} -> {mapped:4s} {mark}")
    mapped_note_for_data4 = mapping.get(data4)
    if mapped_note_for_data4 is not None:
        ok = "(OK)" if mapped_note_for_data4 == note_name else "(MISMATCH)"
        print(f"decoded data4 -> mapped note: {data4} -> {mapped_note_for_data4} {ok}")
    print(f"block_bits_accum_len={len(block_bits_accum)} bits")
    print("--- /DECODE STEP ---\n")


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

    out_path = "output_decode.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        tee = Tee(sys.stdout, f)
        with redirect_stdout(tee):
            try:
                main()
            except Exception as e:
                print("ERROR:", e)
