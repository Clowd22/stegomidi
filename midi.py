import mido
import os
input_dir = "mid"
os.makedirs(input_dir, exist_ok=True)
input_filename = os.path.join(input_dir, "auto_sample_timeshift_deterministic_deterministic.mid")
midi = mido.MidiFile(input_filename)
print(midi)
