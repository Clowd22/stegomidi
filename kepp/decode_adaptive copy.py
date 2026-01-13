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

# キーフレーム間隔（エンコーダと一致させる）
KEYFRAME_INTERVAL = 8

# 追加: エンコーダ側と合わせるベースベロシティ
BASE_VELOCITY = 80


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
    while len(notes) < 16:
        notes.append(list(prob_table.keys())[len(prob_table)//2])
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

    block_bits_accum = ""  # デコード側でブロック復元用に保持
    expected_notes_in_block = KEYFRAME_INTERVAL

    for idx_msg, msg in enumerate(all_msgs):
        # SYNC メタメッセージを検出したら prev_note をリセット／同期
        if getattr(msg, "type", None) == "text" and isinstance(getattr(msg, "text", None), str):
            text = msg.text
            if text.startswith("SYNC:"):
                parts = text.split(":", 3)
                # フォーマット SYNC:step:note:CRC
                if len(parts) >= 4:
                    _, s_step, s_note, s_crc = parts
                    prev_note = s_note
                    print(f"[SYNC READ] step={s_step} prev_note を {s_note} に同期、reported_crc={s_crc}")
                    # ブロック検証
                    actual_crc = crc8_bits(block_bits_accum)
                    try:
                        reported_crc = int(s_crc, 16)
                    except:
                        reported_crc = None
                    print(f"  block_bits_len={len(block_bits_accum)} expected_notes={expected_notes_in_block} reconstructed_bits_len={len(block_bits_accum)} actual_crc={actual_crc:02X}")
                    if reported_crc is not None:
                        if actual_crc != reported_crc:
                            print(f"  CRC MISMATCH! reported={reported_crc:02X} actual={actual_crc:02X}")
                            # 欠損ノート数の推定（6bit/ノート）
                            expected_bits = expected_notes_in_block * 6
                            missing_bits = expected_bits - len(block_bits_accum)
                            missing_notes = (missing_bits + 5) // 6 if missing_bits > 0 else 0
                            print(f"  推定欠損ノート数: {missing_notes} (missing_bits={missing_bits})")
                        else:
                            print("  CRC OK")
                    else:
                        print("  SYNC に CRC がないか解析失敗")
                    # ブロックをリセットして次へ
                    block_bits_accum = ""
                else:
                    print(f"[SYNC] 不正な SYNC: {text}")
            continue

        if getattr(msg, "type", None) != "note_on" or getattr(msg, "velocity", 0) == 0:
            continue

        note_num = msg.note
        note_name = MIDI_TO_NOTE.get(note_num)
        velocity = getattr(msg, "velocity", 0)
        if note_name is None:
            print(f"[Step {step}] 未対応のMIDIノート: {note_num} → スキップ")
            continue

        # note_on の直後に現れる note_off / note_on(vel=0) までの相対時間を合算して duration を求める
        accum = 0
        found = False
        for j in range(idx_msg + 1, msg_len):
            m = all_msgs[j]
            accum += getattr(m, "time", 0)
            if getattr(m, "type", None) == "note_off" and getattr(m, "note", None) == note_num:
                duration_ticks = accum
                found = True
                break
            if getattr(m, "type", None) == "note_on" and getattr(m, "velocity", 0) == 0 and getattr(m, "note", None) == note_num:
                duration_ticks = accum
                found = True
                break
        if not found:
            # 見つからなければ残り時間を合算しておく（安全措置）
            duration_ticks = 0
            for k in range(idx_msg + 1, msg_len):
                duration_ticks += getattr(all_msgs[k], "time", 0)

        # ここで mapping 再現（prev_note に基づく）
        prob_table = make_probability_table(prev_note)
        mapping = make_mapping_from_prob_table(prob_table)

        # velocity から slot_index を復元して mapping 内のビットを選択
        selected_bits = select_slot_from_velocity(note_name, mapping, velocity)
        if selected_bits is None:
            print(f"[Step {step}] slot 選択失敗: note_name={note_name}")
            continue
        data4 = selected_bits
        slot_index = velocity - BASE_VELOCITY
        print(f"[Step {step}] velocity -> slot_index={slot_index} selected_bits={data4}")

        # duration を丸めて2bitを得る
        closest = min(DURATION_TABLE.items(), key=lambda kv: abs(kv[1] - duration_ticks))
        dur_bits = closest[0]

        # 最終的に「元データ4bit + 2bit duration」をビット列に追加
        full_bits = data4 + dur_bits
        bit_string += full_bits

        # 追加: 詳細表示を行う
        print_decode_verbose(prob_table, mapping, step, prev_note, note_name, duration_ticks, velocity, data4, dur_bits, block_bits_accum)

        # 既存の簡潔表示
        print(f"復元: selected_bits: {data4} | dur_bits: {dur_bits} | 合成: {full_bits}")

        prev_note = note_name
        step += 1

        # note_on の通常処理の後、full_bits を得たら block_bits_accum に追加する
        block_bits_accum += data4 + dur_bits

    # 8bit境界にパディングしてテキスト化
    if len(bit_string) % 8 != 0:
        pad_len = 8 - (len(bit_string) % 8)
        bit_string += '0' * pad_len
        print(f"[パディング] 8の倍数にするため末尾に{'0'*pad_len}を追加")

    # 8bitごとに変換して UTF-8 としてデコード（エラーは無視）
    bytes_list = [int(bit_string[i:i+8], 2) for i in range(0, len(bit_string), 8)]
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
    main()
