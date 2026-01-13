from mido import MidiFile
import sys

# ピッチと音名の対応
pitch_to_label = {
    60: ('000', 'ド'),
    62: ('001', 'レ'),
    64: ('010', 'ミ'),
    65: ('011', 'ファ'),
    67: ('100', 'ソ'),
    69: ('101', 'ラ'),
    71: ('110', 'シ'),
    72: ('111', 'ド↑')
}

# MIDI読み込み　実行時の引数にファイル名を指定
filename = sys.argv[1] 
mid = MidiFile(filename) 

bitstream = ""
log = []

for msg in mid.tracks[0]:
    if msg.type == 'note_on' and msg.velocity > 0:
        pitch = msg.note
        velocity = msg.velocity

        if pitch in pitch_to_label:
            pitch_bits, label = pitch_to_label[pitch]
            velocity_bits = format(velocity, '07b')[-2:]
            total_bits = pitch_bits + velocity_bits
            bitstream += total_bits

            log.append({
                '音名': label,
                'MIDIノート': pitch,
                'ベロシティ': velocity,
                '埋め込まれたビット': total_bits
            })

# 8bitずつ区切って文字復元
byte_chunks = [bitstream[i:i+8] for i in range(0, len(bitstream), 8)]
text = ''.join(chr(int(b, 2)) for b in byte_chunks if len(b) == 8)

# 表示
print("▼ デコード詳細:")
for i, entry in enumerate(log):
    print(f"{i+1:02}: 音名: {entry['音名']:<3}  ノート: {entry['MIDIノート']}  "
    f"Vel: {entry['ベロシティ']}  → 埋め込みビット: {entry['埋め込まれたビット']}")

print("\n▼ 復元された文字列:")
print(text)
