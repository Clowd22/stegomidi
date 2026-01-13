import pyautogui
import time
import keyboard
import threading
import sys
import os

# 停止フラグをグローバル変数として定義
is_running = False
toggle_key = 'f8'
toggle_lock = threading.Lock()

# ⚠️ クリックしたい座標を直接ここに記述してください
coordinates = [
    (598, 374),
    (813, 383),
    (1107, 374),
    (1314, 373),
    (600, 563),
    (823, 552),
    (1059, 552),
    (1339, 528),
    (651, 746),
    (839, 733),
    (1056, 744),
    (1271, 733),
]

def toggle_run():
    """
    F8キーが押されたら、実行状態を切り替えます。
    """
    global is_running
    with toggle_lock:
        is_running = not is_running
        status = "実行中" if is_running else "停止中"
        print(f"\n--- プログラムの状態: {status} ---")

def keyboard_monitor():
    """
    キー入力を監視し、トグルキーが押されたら状態を切り替える。
    """
    print(f"\nキーボード監視スレッドを開始しました。'{toggle_key}' で開始/停止します。")
    keyboard.add_hotkey(toggle_key, toggle_run)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

def main():
    """
    メインの自動クリック処理
    """
    # キーボード監視スレッドを開始
    monitor_thread = threading.Thread(target=keyboard_monitor)
    monitor_thread.daemon = True
    monitor_thread.start()

    if not coordinates:
        print("エラー: 座標が設定されていません。")
        input("プログラムを終了するには、Enterキーを押してください...")
        return

    print("以下の座標でクリックを実行します:")
    for x, y in coordinates:
        print(f"  - X: {x}, Y: {y}")
    
    # ゲームのウィンドウタイトルを指定
    game_window_title = 'Roblox'
    
    print("\nゲームウィンドウをアクティブ化します。")
    try:
        window = pyautogui.getWindowsWithTitle(game_window_title)[0]
        if window:
            window.activate()
            print(f"'{game_window_title}' ウィンドウをアクティブにしました。")
            time.sleep(2)
    except IndexError:
        print(f"警告: タイトル '{game_window_title}' のウィンドウが見つかりませんでした。")
        print("手動でゲームウィンドウをアクティブにしてください。")
        time.sleep(5)

    print("\n--- 自動クリックを開始するには、F8キーを押してください ---")
    
    while True:
        if is_running:
            for x, y in coordinates:
                if not is_running:
                    break
                pyautogui.click(x, y)
                time.sleep(0.5)

        time.sleep(0.1)

if __name__ == "__main__":
    main()
