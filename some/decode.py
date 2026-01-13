from mido import MidiFile

pitch_to_bits = {60: '000', 62: '001', 64: '010', 65: '011', 67: '100', 69: '101', 71: '110', 72: '111'}

midi = MidiFile("test1001.mid")
bitstream = ""

for msg in midi.tracks[0]:
    if msg.type == 'note_on' and msg.velocity > 0 and msg.note in pitch_to_bits:
        pitch_bits = pitch_to_bits[msg.note]
        velocity_bits = format(msg.velocity, '07b')[-2:]
        bitstream += pitch_bits + velocity_bits

# 8bitごとに文字復元
print(f"復元されたbit列: {bitstream}")
text = "".join([chr(int(bitstream[i:i+8], 2)) for i in range(0, len(bitstream), 8) if len(bitstream[i:i+8]) == 8])
print(f"復元されたテキスト: {text}")

