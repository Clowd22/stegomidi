from mido import MidiFile

# --- 埋め込みルールと対応表（エンコードと逆向き） ---
pitch_table_rev = {
    60: '0000', 62: '0001', 64: '0010', 67: '0011', 69: '0100',
    72: '0101', 74: '0110', 76: '0111', 79: '1000', 81: '1001',
    84: '1010', 86: '1011', 88: '1100', 91: '1101', 93: '1110',
    96: '1111'
}

rhythm_table_rev = {
    480: '00',  # 4分音符
    240: '01',  # 8分音符
}

rest_rhythm_table_rev = {
    480: '10',  # 4分休符
    240: '11',  # 8分休符
}

velocity_table_rev = {0: '00', 1: '01', 2: '10', 3: '11'}
base_velocity = 80

def decode_midi_to_bitstream(input_filename):
    try:
        mid = MidiFile(input_filename)
        track = mid.tracks[0]
    except FileNotFoundError:
        print(f"エラー: ファイル '{input_filename}' が見つかりません。")
        return

    bitstream = ""
    i = 0

    while i < len(track) - 1:
        msg_on = track[i]
        msg_off = track[i + 1]

        # まずリズム（休符か音符か）をベロシティで判定
        if msg_on.type == 'note_on' and msg_off.type == 'note_off':
            # 休符（ベロシティ0）
            if msg_on.velocity == 0:
                rest_duration = msg_on.time
                rest_bits = rest_rhythm_table_rev.get(rest_duration, None)
                before = bitstream
                if rest_bits is None:
                    rest_bits = '0' * 2
                    print(f"[休符] duration={rest_duration} → 未知なので'00'で埋める")
                else:
                    print(f"[休符] duration={rest_duration} → {rest_bits}")
                bitstream += rest_bits
                """
                print(f"  追加前: {before}")
                print(f"  追加後: {bitstream}")
                """
                i += 2
                continue
            # 音符（ベロシティ>0）
            elif msg_on.velocity > 0:
                # リズム（音価）2bit
                duration = msg_off.time
                rhythm_bits = rhythm_table_rev.get(duration, None)
                before = bitstream
                if rhythm_bits is None:
                    rhythm_bits = '0' * 2
                    print(f"[音符] rhythm duration={duration} → 未知なので'00'で埋める")
                else:
                    print(f"[音符] rhythm duration={duration} → {rhythm_bits}")
                bitstream += rhythm_bits
                """
                print(f"  追加前: {before}")
                print(f"  追加後: {bitstream}")
                """

                # 音階4bit
                pitch_bits = pitch_table_rev.get(msg_on.note, None)
                before = bitstream
                if pitch_bits is None:
                    pitch_bits = '0' * 4
                    print(f"[音符] pitch note={msg_on.note} → 未知なので'0000'で埋める")
                else:
                    print(f"[音符] pitch note={msg_on.note} → {pitch_bits}")
                bitstream += pitch_bits
                """
                print(f"  追加前: {before}")
                print(f"  追加後: {bitstream}")
                """

                # ベロシティ2bit
                velocity_change = msg_on.velocity - base_velocity
                velocity_bits = velocity_table_rev.get(velocity_change, None)
                before = bitstream
                if velocity_bits is None:
                    velocity_bits = '0' * 2
                    print(f"[音符] velocity change={velocity_change} → 未知なので'00'で埋める")
                else:
                    print(f"[音符] velocity change={velocity_change} → {velocity_bits}")
                bitstream += velocity_bits

                i += 2
                continue
        i += 1

    print("▼ 復元されたビット列:")
    print(bitstream)
    # bitstreamをUTF-8文字列に変換
    bytes_list = []
    for j in range(0, len(bitstream), 8):
        byte = bitstream[j:j+8]
        if len(byte) == 8:
            bytes_list.append(int(byte, 2))
    if bytes_list:
        text = bytes(bytes_list).decode('utf-8', errors='ignore')
    else:
        text = ""
    print("▼ 復元された文字列:")
    print(text)


if __name__ == '__main__':
    for i in range(1, 11):
        print(f"\n--- テストケース{i} ---")
        input_filename = f"encoded_{i}.mid"
        decode_midi_to_bitstream(input_filename)
