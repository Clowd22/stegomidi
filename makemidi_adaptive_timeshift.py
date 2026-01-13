# makemidi_adaptive のコピーを基に、キーフレーム音の duration を微小にずらす（+1 tick）実装
from mido import Message, MidiFile, MidiTrack, MetaMessage
import os
from midi_shared import (
    NOTE_NAMES, NOTE_TO_MIDI, RELATIVE_WEIGHTS, DURATION_TABLE,
    KEYFRAME_INTERVAL, BASE_VELOCITY, KEYFRAME_PHRASE,
    KEYFRAME_VELOCITY, KEYFRAME_DURATION_SHIFT,
    make_probability_table, make_mapping_from_prob_table,
    print_mapping_verbose, crc8_bits
)

def main():
    import sys
    # stdin がパイプ/リダイレクトの場合は全入力を読み取り、
    # 「末尾の空でない行」を title、それ以前を text（改行を保持）とする。
    if not sys.stdin.isatty():
        raw = sys.stdin.read().splitlines()
        if len(raw) == 0:
            text = input("Enter text to encode in MIDI: ")
            title = input("Enter title for MIDI data: ")
        elif len(raw) == 1:
            text = raw[0]
            title = input("Enter title for MIDI data: ")
        else:
            idx = len(raw) - 1
            while idx >= 0 and raw[idx].strip() == "":
                idx -= 1
            title = raw[idx].strip()
            text = "\n".join(raw[:idx])
    else:
        # 対話モードで改行を含むテキストを入力できるようにする。
        print("Enter text to encode in MIDI. 終了は単独の '.' を入力して確定、Ctrl-D でも終了できます。")
        lines = []
        try:
            while True:
                line = input()
                if line == ".":
                    break
                lines.append(line)
        except EOFError:
            # Ctrl-D で終了
            pass
        text = "\n".join(lines).rstrip("\n")
        if text == "":
            # 空なら1行入力にフォールバック
            text = input("Empty input — Enter single-line text to encode: ")
        title = input("Enter title for MIDI data: ")

    # UTF-8 バイト列でエンコード（日本語・絵文字を正しく扱う）
    payload_bytes = text.encode('utf-8')
    # 先頭に元のバイト長を 4 バイト（big-endian）で付与しておく
    length_header = len(payload_bytes).to_bytes(4, 'big')
    bytes_data = length_header + payload_bytes
    binary_data = ''.join(f'{b:08b}' for b in bytes_data)
    chunks = [binary_data[i:i+6].ljust(6, '0') for i in range(0, len(binary_data), 6)]

    # DEBUG: エンコード情報出力（ビット・チャンク数・末尾チャンク）
    print(f"[ENCODE INFO] payload_bytes_len={len(payload_bytes)} total_bytes_len={len(bytes_data)} "
          f"binary_bits_len={len(binary_data)} chunks={len(chunks)} last_chunk={chunks[-1]!r}")

    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)

    prev_note = "C4"
    block_bits = ""
    notes_since_keyframe = 0
    print("\n=== Adaptive MIDI Encoding (timeshift keyframe) ===")

    for step, chunk in enumerate(chunks, 1):
        pitch_bits = chunk[:4]
        dur_bits = chunk[4:]
        pitch_bits_for_map = pitch_bits

        prob_table = make_probability_table(prev_note)
        mapping = make_mapping_from_prob_table(prob_table)

        candidates = [b for b, n in mapping.items() if n == mapping[pitch_bits_for_map]]
        candidates.sort(key=lambda x: int(x,2))
        try:
            slot_index = candidates.index(pitch_bits_for_map)
        except ValueError:
            slot_index = 0

        print_mapping_verbose(prob_table, mapping, step, prev_note, chunk, pitch_bits_for_map, slot_index)

        note_name = mapping[pitch_bits_for_map]
        duration = DURATION_TABLE[dur_bits]
        new_velocity = BASE_VELOCITY + slot_index
        if new_velocity > 127:
            new_velocity = 127

        note_num = NOTE_TO_MIDI[note_name]

        # decide whether THIS data note is the KEYFRAME (i.e. the N=KEYFRAME_INTERVAL-th note)
        is_keyframe_note = (notes_since_keyframe + 1) >= KEYFRAME_INTERVAL

        # append data note; if it's keyframe note, add duration shift to its note_off
        track.append(Message('note_on', note=note_num, velocity=new_velocity, time=0))
        off_time = duration + (KEYFRAME_DURATION_SHIFT if is_keyframe_note else 0)
        track.append(Message('note_off', note=note_num, velocity=0, time=off_time))

        # accumulate bits (include this 20th note's bits)
        block_bits += pitch_bits + dur_bits

        # update notes counter / handle keyframe action AFTER adding the 20th note
        notes_since_keyframe += 1
        if is_keyframe_note:
            crc = crc8_bits(block_bits)
            # emit SYNC text immediately after the shifted note_off
            last_note = note_name
            sync_text = f"SYNC:{step}:{last_note}:{crc:02X}"
            track.append(MetaMessage('text', text=sync_text, time=0))
            print(f"[SYNC(timeshift) WRITE] step={step} block_bits_len={len(block_bits)} crc={crc:02X} keyframe_note={last_note} text='{sync_text}'")
            block_bits = ""
            notes_since_keyframe = 0

        prev_note = note_name

    output_dir = "mid"
    os.makedirs(output_dir, exist_ok=True)
    output_filename = os.path.join(output_dir, f"{title}_timeshift.mid")
    mid.save(output_filename)
    print(f"\nMIDI saved: {output_filename}")

if __name__ == "__main__":
    main()
