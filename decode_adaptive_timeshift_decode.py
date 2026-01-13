from mido import MidiFile
import os
import re
from midi_shared import (
    NOTE_NAMES, NOTE_TO_MIDI, RELATIVE_WEIGHTS, DURATION_TABLE,
    KEYFRAME_INTERVAL, BASE_VELOCITY, KEYFRAME_PHRASE,
    KEYFRAME_VELOCITY, KEYFRAME_DURATION_SHIFT,
    make_probability_table, make_mapping_from_prob_table,
    print_mapping_verbose, crc8_bits
)

# 逆引きテーブル（MIDI番号 -> ノート名）
MIDI_TO_NOTE = {v: k for k, v in NOTE_TO_MIDI.items()}

def midi_to_note_name(note_num):
    """MIDIノート番号を NOTE_NAMES にマップ。厳密一致がなければ最も近い番号を採用。"""
    if note_num is None:
        return None
    if note_num in MIDI_TO_NOTE:
        return MIDI_TO_NOTE[note_num]
    # 近いキーを探す（安全策）
    closest = min(MIDI_TO_NOTE.keys(), key=lambda x: abs(x - note_num))
    return MIDI_TO_NOTE[closest]

# --- ヘルパ ---
def select_slot_from_velocity(note_name, mapping, velocity):
    candidates = [bits for bits, n in mapping.items() if n == note_name]
    candidates.sort(key=lambda x: int(x, 2))
    if not candidates:
        return None
    vel_index = velocity - BASE_VELOCITY
    if vel_index < 0:
        vel_index = 0
    idx = vel_index % len(candidates)
    return candidates[idx]

# find paired note_off index and compute duration_ticks
def find_note_duration_and_off_index(all_msgs, start_idx):
    msg_len = len(all_msgs)
    accum = 0
    note_num = getattr(all_msgs[start_idx], "note", None)
    for j in range(start_idx + 1, msg_len):
        m = all_msgs[j]
        accum += getattr(m, "time", 0)
        if (getattr(m, "type", None) == "note_off" and getattr(m, "note", None) == note_num) or \
           (getattr(m, "type", None) == "note_on" and getattr(m, "velocity", 0) == 0 and getattr(m, "note", None) == note_num):
            return accum, j
    return None, None

# デバッグ出力（簡潔）
VERBOSE = True
def print_decode_verbose(*args, **kwargs):
    # timeshift 用デコーダでは詳細表示は不要なので無害なダミーにする
    return

# --- メイン ---
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

    # flatten all messages (preserve relative times)
    all_msgs = []
    for tr in mid.tracks:
        all_msgs.extend(tr)
    msg_len = len(all_msgs)

    block_bits_accum = ""
    block_note_count = 0
    # header_aligned == True なら既に先頭ヘッダ位置が確定しており、以降のブロックは素直に append する
    header_aligned = False
    skip_indices = set()
    idx = 0
    while idx < msg_len:
        msg = all_msgs[idx]
        if idx in skip_indices:
            idx += 1
            continue

        # standalone SYNC text を検出した場合はここで再同期（simulate_loss 等で note が削除されて
        # SYNC が独立して現れるケースに対応）
        if getattr(msg, "type", None) == "text" and isinstance(getattr(msg, "text", None), str) and msg.text.startswith("SYNC:"):
            parts = msg.text.split(":", 3)
            if len(parts) >= 4:
                _, s_step, s_note, s_crc = parts
                print(f"[SYNC(READ-STANDALONE)] step={s_step} prev_note を {s_note} に同期、reported_crc={s_crc}")
                # 再同期: 現在のブロックを破棄し、prev_note を報告ノートに合わせる
                block_bits_accum = ""
                block_note_count = 0
                prev_note = s_note
            idx += 1
            continue

        # only process note_on with velocity>0
        if getattr(msg, "type", None) != "note_on" or getattr(msg, "velocity", 0) == 0:
            idx += 1
            continue

        # compute duration (find corresponding note_off)
        dur_ticks, off_idx = find_note_duration_and_off_index(all_msgs, idx)
        if dur_ticks is None:
            dur_ticks = 0

        note_num = getattr(msg, "note", None)
        note_name = midi_to_note_name(note_num)
        # note_name を使って以降の復号処理を行う
        velocity = getattr(msg, "velocity", 0)
        if note_name is None:
            idx += 1
            continue

        # reconstruct mapping and select slot
        prob_table = make_probability_table(prev_note)
        mapping = make_mapping_from_prob_table(prob_table)
        selected_bits = select_slot_from_velocity(note_name, mapping, velocity)
        if selected_bits is None:
            print(f"[Step {step}] slot 選択失敗: note_name={note_name}")
            idx += 1
            continue
        data4 = selected_bits
        # round duration to nearest 2bit code
        closest = min(DURATION_TABLE.items(), key=lambda kv: abs(kv[1] - dur_ticks))
        dur_bits = closest[0]

        full_bits = data4 + dur_bits
        # ブロック単位で検証するため、まずは block_bits_accum にだけ蓄える。
        # CRC 検証で OK ならその時点で bit_string にコミットする（下記の keyframe/SYNC 処理内で行う）。
        block_bits_accum += full_bits
        block_note_count += 1

        # check whether this note is a timeshift keyframe marker:
        # if dur_ticks equals some canonical duration + KEYFRAME_DURATION_SHIFT, and a SYNC meta follows the note_off,
        # then treat SYNC as block boundary. The note itself remains part of data (we already added its bits).
        is_keyframe_marker = False
        for code, base_dur in DURATION_TABLE.items():
            if dur_ticks == base_dur + KEYFRAME_DURATION_SHIFT:
                # check for SYNC text shortly after off_idx
                if off_idx is not None:
                    for j in range(off_idx + 1, min(off_idx + 1 + 64, msg_len)):
                        m = all_msgs[j]
                        if getattr(m, "type", None) == "text" and isinstance(getattr(m, "text", None), str) and m.text.startswith("SYNC:"):
                            # validate CRC on block_bits_accum (which currently includes this note)
                            parts = m.text.split(":", 3)
                            if len(parts) >= 4:
                                if len(parts) >= 4:
                                    _, s_step, s_note, s_crc = parts
                                    print(f"[Keyframe+SYNC READ] step={s_step} prev_note を {s_note} に同期、reported_crc={s_crc}")
                                    # synchronize decoder step counter to encoder's reported step
                                    try:
                                        step = int(s_step) + 1
                                    except Exception:
                                        pass
                                    actual_crc = crc8_bits(block_bits_accum)
                                    try:
                                        reported_crc = int(s_crc, 16)
                                    except:
                                        reported_crc = None
                                    print(f"  block_bits_len={len(block_bits_accum)} actual_crc={actual_crc:02X}")
                                    # CRC が報告されている場合は検証して OK のときのみコミット、NG のときは破棄する
                                    if reported_crc is not None:
                                        if actual_crc != reported_crc:
                                            print(f"  CRC MISMATCH! reported={reported_crc:02X} actual={actual_crc:02X}")
                                            # 破棄（何もしない）
                                        else:
                                            print("  CRC OK -> commit block bits (attempt header align)")
                                            # header が未整列の場合はこのブロック内でヘッダ探索を行い、見つかればそこからコミットする
                                            if not header_aligned:
                                                found_shift = None
                                                found_len = None
                                                for s in range(0, 8):
                                                    if len(block_bits_accum) < s + 32:
                                                        continue
                                                    cand = block_bits_accum[s:s+32]
                                                    try:
                                                        b = bytes(int(cand[i:i+8], 2) for i in range(0, 32, 8))
                                                    except Exception:
                                                        continue
                                                    try:
                                                        expect_len = int.from_bytes(b, 'big')
                                                    except Exception:
                                                        continue
                                                    # 単純チェック：正の長さで過大でないこと
                                                    if 0 < expect_len < 10_000_000:
                                                        found_shift = s
                                                        found_len = expect_len
                                                        break
                                                if found_shift is not None:
                                                    print(f"    header found in block at shift={found_shift} expected_len={found_len}")
                                                    # commit starting from header bit
                                                    bit_string += block_bits_accum[found_shift:]
                                                    header_aligned = True
                                                else:
                                                    print("    header not found in this block -> skip commit (await later block)")
                                            else:
                                                # 既に整列済みならそのまま append
                                                bit_string += block_bits_accum
                                    else:
                                        # CRC 情報が無ければ暫定的にコミット
                                        if header_aligned:
                                            bit_string += block_bits_accum
                                        else:
                                            print("    no CRC info and header not aligned -> skip commit")
                            # debug: show how many notes were in this block
                            print(f"  block_note_count={block_note_count} block_bits_len={len(block_bits_accum)}")
                            # consume the SYNC meta (skip its index)
                            skip_indices.add(j)
                            # synchronize prev_note to reported note
                            prev_note = s_note if s_note else note_name
                            # reset block accumulator and counter after handling (whether committed or discarded)
                            block_bits_accum = ""
                            block_note_count = 0
                            is_keyframe_marker = True
                            break
                break

        print(f"[Step {step}] decoded note={note_name} dur={dur_ticks} vel={velocity} -> bits={full_bits}")
        prev_note = note_name
        step += 1
        idx += 1

    # EOF 到達時: 最後に残ったブロックのビット列はコミットしてパディング対象とする
    if block_bits_accum:
        # EOF 時点でもヘッダ未整列ならこの最後のブロック内でヘッダ探索を試みる
        if not header_aligned:
            found_shift = None
            for s in range(0, 8):
                if len(block_bits_accum) < s + 32:
                    continue
                cand = block_bits_accum[s:s+32]
                try:
                    b = bytes(int(cand[i:i+8], 2) for i in range(0, 32, 8))
                    expect_len = int.from_bytes(b, 'big')
                except Exception:
                    continue
                if 0 < expect_len < 10_000_000:
                    found_shift = s
                    break
            if found_shift is not None:
                print(f"[EOF] header found in final block at shift={found_shift} -> commit from there")
                bit_string += block_bits_accum[found_shift:]
                header_aligned = True
            else:
                print("[EOF] header not found in final block -> skipping final commit")
        else:
            bit_string += block_bits_accum

    # パディング方針：末尾の不完全バイトはゼロでパディングして復元する
    rem = len(bit_string) % 8
    print(f"[DECODE INFO] bit_string_len={len(bit_string)} rem={rem} (last32={bit_string[-32:]!r})")
    if rem != 0:
        pad = 8 - rem
        print(f"[INFO] 末尾の不完全なビットを{rem}個検出、{pad}個の'0'でパディングして復号します")
        bit_string = bit_string + '0' * pad
    bytes_list = [int(bit_string[i:i+8], 2) for i in range(0, len(bit_string), 8)]
    try:
        reconstructed_bytes = bytes(bytes_list)
    except Exception:
        reconstructed_bytes = b"".join(bytes([b]) for b in bytes_list)

    print(f"[DECODE INFO] reconstructed_bytes_len={len(reconstructed_bytes)} "
        f"first4={reconstructed_bytes[:4].hex()} last4={reconstructed_bytes[-4:].hex()}")
    # ヘッダ付き出力を想定: 先頭4バイトが元データ長 (big-endian)
    # ここで先頭4バイトが本当に payload-length を示しているかを確認する。
    # 先頭がバイト境界からずれている可能性があるため、0..7 ビットずらして妥当なヘッダを探索する。
    def find_valid_header(bitstr, max_payload=10_000_000):
        # bitstr は '0'/'1' 文字列
        for shift in range(0, 8):
            # skip shift bits from the start
            if len(bitstr) < shift + 32:
                continue
            cand = bitstr[shift:shift+32]
            # convert to 4 bytes
            b = bytes(int(cand[i:i+8], 2) for i in range(0, 32, 8))
            expected_len = int.from_bytes(b, 'big')
            # reasonable check: non-zero and not absurdly large
            avail_bytes = (len(bitstr) - shift) // 8 - 4
            if 0 < expected_len <= max_payload and expected_len <= max(0, avail_bytes):
                return shift, expected_len
        return None, None

    # attempt to find valid header (可能ならば先頭ビットを削る)
    shift, expected_len = find_valid_header(bit_string)
    if shift and shift > 0:
        print(f"[DECODE] adjusted bit_string by removing {shift} leading bits to align header")
        bit_string = bit_string[shift:]
    if len(bit_string) >= 32:
        reconstructed_bytes = bytes(int(bit_string[i:i+8], 2) for i in range(0, len(bit_string), 8))
        expected_len = int.from_bytes(reconstructed_bytes[:4], 'big')
        print(f"[DECODE INFO] expected_payload_len={expected_len} available={len(reconstructed_bytes)-4}")
        # 期待長が手元のバイト数内に収まればその分だけ取り出す。足りなければ残りをデコード。
        if expected_len <= len(reconstructed_bytes) - 4:
            # ...existing code for extracting payload...
            pass
        else:
            # not enough bytes yet — keep waiting / report partial
            pass
    else:
        print("[DECODE INFO] not enough bits to form header yet")
        reconstructed_bytes = b""
        expected_len = 0

    decoded_text = reconstructed_bytes.decode('utf-8', errors='replace')
    print(f"復号テキスト: {decoded_text}")

if __name__ == "__main__":
    main()
