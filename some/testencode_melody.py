# encode_melody.py

from mido import Message, MidiFile, MidiTrack
import math

# --- 埋め込みルールと対応表 ---
pitch_table = {
    '0000': 60, '0001': 62, '0010': 64, '0011': 67, '0100': 69,
    '0101': 72, '0110': 74, '0111': 76, '1000': 79, '1001': 81,
    '1010': 84, '1011': 86, '1100': 88, '1101': 91, '1110': 93,
    '1111': 96
}

rhythm_table = {
    '00': 480, '01': 240, '10': 480, '11': 240
}

rhythm_name_table = {
    '00': '4分音符', '01': '8分音符', '10': '4分休符', '11': '8分休符'
}

velocity_table = {
    '00': 0, '01': 1, '10': 2, '11': 3
}
base_velocity = 80

# --- メインのエンコード処理 ---
def encode_text_to_midi(text, output_filename):
    byte_stream = text.encode('utf-8')
    binary_data = ''.join(f'{b:08b}' for b in byte_stream)
    print(binary_data)
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    
    bit_pointer = 0
    
    print("\n▼ エンコード詳細:")
    while bit_pointer < len(binary_data):
        # 2ビットを読み込む前に、足りなければパディング
        if bit_pointer + 2 > len(binary_data):
            pad_len = (bit_pointer + 2) - len(binary_data)
            binary_data += '0' * pad_len
            print(f"[パディング] 2bitリズム用に末尾に{'0'*pad_len}を追加")

        rhythm_bits = binary_data[bit_pointer:bit_pointer+2]
        
        if rhythm_bits in ['10', '11']:  # 休符の場合:
            time = rhythm_table[rhythm_bits]
            track.append(Message('note_on', note=0, velocity=0, time=time))
            track.append(Message('note_off', note=0, velocity=0, time=0))
            bit_pointer += 2
            print(f"ビット列: {rhythm_bits:<2}  -> {rhythm_name_table[rhythm_bits]:<5} (休符)")
        else:  # 音符の場合:
            # 8ビット必要なので、足りなければパディング
            if bit_pointer + 8 > len(binary_data):
                pad_len = (bit_pointer + 8) - len(binary_data)
                binary_data += '0' * pad_len
                print(f"[パディング] 8bit音符用に末尾に{'0'*pad_len}を追加")
            time = rhythm_table[rhythm_bits]
            pitch_bits = binary_data[bit_pointer+2:bit_pointer+6]
            velocity_bits = binary_data[bit_pointer+6:bit_pointer+8]
            
            note = pitch_table[pitch_bits]
            velocity_change = velocity_table[velocity_bits]
            new_velocity = base_velocity + velocity_change
            
            track.append(Message('note_on', note=note, velocity=new_velocity, time=0))
            track.append(Message('note_off', note=note, velocity=0, time=time))
            
            print(f"ビット列: {rhythm_bits:<2} {pitch_bits:<4} {velocity_bits:<2} -> 音階: {note}, リズム: {rhythm_name_table[rhythm_bits]}, ベロシティ: {new_velocity}")
            bit_pointer += 8

    mid.save(output_filename)
    print(f"\nMIDIファイル '{output_filename}' が作成されました。")

if __name__ == '__main__':
    test_texts = [
        "Hello, World!", 
        "MIDIエンコードテスト", 
        "PythonでMIDIを作成", 
        "秘密のメッセージ", 
        "1234567890!@#$%^&*()",
        "長い文章のテスト。これはMIDIファイルにエンコードされるべきです。",
        "短い",
        "A1",
        "😊🎵🚀",
        "The quick brown fox jumps over the lazy dog."
    ]
    for i, text in enumerate(test_texts):
        print(f"\n--- テストケース{i+1}: '{text}' ---")
        encode_text_to_midi(text, f"encoded_{i+1}.mid")

