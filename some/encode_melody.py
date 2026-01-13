# encode_melody.py

from mido import Message, MidiFile, MidiTrack
import datetime
import os

# 音階対応（C4=60）
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
    binary_data = ''.join(f'{ord(c):08b}' for c in text)
    print(binary_data)
    
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)

    bitpoiter = 0
    delta_time = 0
    
    print("▼ エンコード詳細:")
    while bitpoiter < len(binary_data):
        # 2ビットを読み込み
        if bitpoiter + 2 > len(binary_data):
            # データが足りない場合は0で埋める
            binary_data += '0' * (bitpoiter + 2 - len(binary_data))
        rhythm_bits = binary_data[bitpoiter:bitpoiter+2]
        
        if rhythm_bits in ['10', '11']:  # 休符の場合: 
            time = rhythm_table[rhythm_bits]
            delta_time += time
            bitpoiter += 2
            print(f"ビット列: {rhythm_bits:<2}  -> {rhythm_name_table[rhythm_bits]:<5} (休符)")
        else:  # 音符の場合: 
            # 6ビットを読み込み
            if bitpoiter + 8 > len(binary_data):
                # データが足りない場合は0で埋める
                binary_data += '0' * (bitpoiter + 8 - len(binary_data))
            time = rhythm_table[rhythm_bits]
            note = pitch_table[binary_data[bitpoiter+2:bitpoiter+6]]
            velocity_suffix = velocity_table[binary_data[bitpoiter+6:bitpoiter+8]]
            new_velocity = base_velocity + velocity_suffix
            
            # 音符イベントを生成し、累積したdelta_timeをtimeに設定
            track.append(Message('note_on', note=note, velocity=new_velocity, time=delta_time))
            track.append(Message('note_off', note=note, velocity=0, time=time))
            
            # delta_timeをリセット
            delta_time = 0
            bitpoiter += 8
            
            print(f"ビット列: {rhythm_bits:<2} {binary_data[bitpoiter-6:bitpoiter-2]:<4} {binary_data[bitpoiter-2:bitpoiter]:<2} -> 音階: {note}, リズム: {rhythm_name_table[rhythm_bits]}, ベロシティ: {new_velocity}")

    # testmid ディレクトリに保存
    os.makedirs("testmid", exist_ok=True)
    output_path = os.path.join("testmid", output_filename)
    mid.save(output_path)
    print(f"MIDIファイル '{output_filename}' が作成されました。")

if __name__ == '__main__':
    test_texts = [
        "Please check the attached file for more details now.This text string contains exactly fifty-two letters.I am looking forward to hearing from you very soon.", 
        "This is sample text for experimental purposes. It has been adjusted to be of appropriate length.",
        "実験用のサンプルテキストです。適当な長さになるように調整をしています。"
    ]
    for i, text in enumerate(test_texts):
        print(f"\n--- テストケース{i+1}: '{text}' ---")
        encode_text_to_midi(text, f"encoded_{i+1}.mid")

