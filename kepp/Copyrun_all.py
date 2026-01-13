import subprocess
import sys
import os

# サンプル文字列とタイトル（必要に応じて変更）
SAMPLE_TEXT = "Some sample text for testing,but its length is not too long."
TITLE = "auto_sample copy"

SCRIPT_DIR = os.path.dirname(__file__)
ENCODE_SCRIPT = os.path.join(SCRIPT_DIR, "makemidi_adaptive copy.py")
DECODE_SCRIPT = os.path.join(SCRIPT_DIR, "decode_adaptive copy.py")

def run_encode():
    print(">>> encode を実行します...")
    # makemidi_adaptive.py は stdin で text と title を受け取るため、2行を渡す
    proc = subprocess.run([sys.executable, ENCODE_SCRIPT],
                          input=f"{SAMPLE_TEXT}\n{TITLE}\n",
                          text=True, capture_output=True, cwd=SCRIPT_DIR)
    print(f"encode returncode: {proc.returncode}")
    if proc.stdout:
        print("---- encode stdout ----")
        print(proc.stdout)
    if proc.stderr:
        print("---- encode stderr ----")
        print(proc.stderr)
    print("encode 終了。出力ファイル: mid/{}_deterministic.mid".format(TITLE))

def run_decode():
    print(">>> decode を実行します...")
    midi_basename = f"{TITLE}_deterministic"  # decode 側に渡す文字列（.mid は不要）
    proc = subprocess.run([sys.executable, DECODE_SCRIPT],
                          input=f"{midi_basename}\n",
                          text=True, capture_output=True, cwd=SCRIPT_DIR)
    print(f"decode returncode: {proc.returncode}")
    if proc.stdout:
        print("---- decode stdout ----")
        print(proc.stdout)
    if proc.stderr:
        print("---- decode stderr ----")
        print(proc.stderr)
    print("decode 終了。出力ログ: output_decode.txt (存在する場合)")

if __name__ == "__main__":
    run_encode()
    run_decode()
