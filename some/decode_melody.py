# decode_melody.py

from mido import MidiFile
import math


# --- 埋め込みルールと対応表（エンコードと逆向き） ---
# メロディ (4bit) - 15音階と休符に対応
pitch_table_rev = {
    60: '0000', 62: '0001', 64: '0010', 67: '0011', 69: '0100',
    72: '0101', 74: '0110', 76: '0111', 79: '1000', 81: '1001',
    84: '1010', 86: '1011', 88: '1100', 91: '1101', 93: '1110',
    96: '1111'
}

# リズム (2bit) - 音価と休符に対応
rhythm_table_rev = {
    480: '00',  # 4分音符
    240: '01',  # 8分音符
    480: '10',  # 4分休符
    240: '11'   # 8分休符
}

# ベロシティ (2bit) - 基準からの相対変化
velocity_table_rev = {0: '00', 1: '01', 2: '10', 3: '11'}
base_velocity = 80

# --- メインのデコード処理 ---
def decode_midi_to_text(input_filename):
    try:
        mid = MidiFile(input_filename)
        track = mid.tracks[0]
        
    except FileNotFoundError:
        print(f"エラー: ファイル '{input_filename}' が見つかりません。")
        return

    bitstream = ""
    
    i = 0
    while i < len(track):
        msg = track[i]
        
        # デルタタイムが休符を示している場合
        if msg.time > 0 and msg.type == 'note_on':
            if msg.time == 480:
                bitstream += '10'  # 4分休符
            elif msg.time == 240:
                bitstream += '11'  # 8分休符
            i += 1
            
        # 音符の場合 (note_onとそれに続くnote_off)
        elif msg.type == 'note_on' and msg.velocity > 0:
            pitch_bits = pitch_table_rev.get(msg.note, '????')
            velocity_change = msg.velocity - base_velocity
            velocity_bits = velocity_table_rev.get(velocity_change, '??')

            if i + 1 < len(track):
                next_msg = track[i + 1]
                if next_msg.type == 'note_off' and next_msg.note == msg.note:
                    duration = next_msg.time
                    rhythm_bits = rhythm_table_rev.get(duration, '??')
                    
                    if all(b != '??' for b in [rhythm_bits, pitch_bits, velocity_bits]):
                        bitstream += rhythm_bits + pitch_bits + velocity_bits
                    
            i += 2  # note_onとnote_offのペアをスキップ
        else:
            i += 1

    # 復元されたビット列を表示
    print("▼ 復元されたビット列:")
    print(bitstream)

    # 8bitずつに区切って文字復元
    byte_chunks = [bitstream[i:i+8] for i in range(0, len(bitstream), 8)]
    text = ""
    for b in byte_chunks:
        if len(b) == 8:
            try:
                char_code = int(b, 2)
                # パディングされた0ビットや非ASCII文字を検出して終了
                if char_code == 0:
                    break
                text += chr(char_code)
            except ValueError:
                break

    print("\n▼ 復元された文字列:")
    print(text)

if __name__ == '__main__':
    # テストケース
    for i in range(10):
        print(f"\n--- テストケース{i+1}---")
        input_filename = f"encoded_{i+1}.mid"
        decode_midi_to_text(input_filename)
