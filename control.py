import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import os

def run_gemini_cli(prompt_text):
    """Hàm hỗ trợ gọi Gemini CLI với auto_edit"""
    print(f"\n[+] Đang chạy CLI: {prompt_text}")
    # Chạy CLI, để shell=True để có thể chạy lệnh gemini như gõ trên terminal
    cmd = f'gemini -p "{prompt_text}" --approval-mode auto_edit'
    
    # Bỏ capture_output để tiến trình của Gemini hiện trực tiếp ra console cho bạn dễ theo dõi
    result = subprocess.run(cmd, shell=True)
    return result.returncode

def step_1_get_keywords():
    """Tạo UI cho 2 người chơi nhập từ khóa"""
    root = tk.Tk()
    root.title("Thiết lập Keywords")
    root.geometry("350x200")
    
    # Biến lưu trữ
    keywords = {"p1": "", "p2": ""}
    
    tk.Label(root, text="Người chơi A (Nhập 3 từ khóa, cách nhau bởi dấu phẩy):").pack(pady=(10, 0))
    entry_p1 = tk.Entry(root, width=40)
    entry_p1.pack(pady=5)
    
    tk.Label(root, text="Người chơi B (Nhập 3 từ khóa, cách nhau bởi dấu phẩy):").pack(pady=(10, 0))
    entry_p2 = tk.Entry(root, width=40)
    entry_p2.pack(pady=5)

    def submit():
        keywords["p1"] = entry_p1.get().strip()
        keywords["p2"] = entry_p2.get().strip()
        if not keywords["p1"] or not keywords["p2"]:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập đủ từ khóa cho cả 2 người!")
            return
        root.destroy() # Tắt UI sau khi submit

    tk.Button(root, text="Xác nhận & Bắt đầu", command=submit, bg="lightblue").pack(pady=15)
    
    # Chặn luồng ở đây cho đến khi cửa sổ tắt
    root.mainloop()
    return keywords["p1"], keywords["p2"]

def loop_test_game():
    """Vòng lặp chạy game base.py, mở UI Feedback và xử lý lỗi"""
    while True:
        print("\n[====================================]")
        print("[*] Đang khởi động base.py...")
        
        # Chạy game base.py và ghi log ra file để tránh tràn bộ nhớ đệm (deadlock)
        log_file = open("latest_run.log", "w", encoding="utf-8")
        game_process = subprocess.Popen([sys.executable, 'base.py'], stdout=log_file, stderr=log_file)
        
        # Mở UI Feedback song song
        f_root = tk.Tk()
        f_root.title("Feedback In-game")
        f_root.geometry("350x250")
        f_root.attributes('-topmost', True) # Ghim lên trên cùng
        
        tk.Label(f_root, text="Phát hiện Bug / Cần sửa gì?").pack(pady=5)
        text_feedback = tk.Text(f_root, height=8, width=40)
        text_feedback.pack(pady=5)
        
        state = {"feedback_text": None, "is_crashed": False}
        
        def on_submit_feedback():
            txt = text_feedback.get("1.0", tk.END).strip()
            if txt:
                state["feedback_text"] = txt
                f_root.destroy()
            else:
                messagebox.showwarning("Cảnh báo", "Vui lòng nhập nội dung feedback.")
                
        tk.Button(f_root, text="Submit Feedback & Sửa Code", command=on_submit_feedback, bg="lightgreen").pack(pady=5)
        
        # Hàm kiểm tra liên tục xem tiến trình game còn sống không
        def check_game_process():
            ret_code = game_process.poll()
            if ret_code is not None:
                # Game đã tắt
                log_file.close()
                if ret_code != 0:
                    state["is_crashed"] = True
                f_root.destroy() # Tắt luôn UI feedback
            else:
                # Vòng lặp check mỗi 500ms
                f_root.after(500, check_game_process)

        f_root.after(500, check_game_process)
        f_root.mainloop() # Chờ đến khi UI feedback tắt
        
        # Kịch bản 1: Người chơi chủ động Submit feedback
        if state["feedback_text"] is not None:
            # Nếu game vẫn đang chạy thì ép tắt
            if game_process.poll() is None:
                game_process.terminate()
            log_file.close()
            
            print("\n[+] Đã nhận feedback, đang lưu vào feedback.txt...")
            with open("feedback.txt", "w", encoding="utf-8") as f:
                f.write(state["feedback_text"])
            
            prompt = "@game-dev hãy fix lại code @player.py, người chơi đã gửi feedback những điều cần sửa trong @feedback.txt."
            run_gemini_cli(prompt)
            continue # Lặp lại loop (chạy lại game)
            
        # Kịch bản 2: Game tự crash / bị tắt do lỗi (return code != 0)
        elif state["is_crashed"]:
            print("\n[!] Game bị crash! Đang trích xuất log lỗi vào bug.txt...")
            with open("latest_run.log", "r", encoding="utf-8") as log_read:
                error_log = log_read.read()
                
            with open("bug.txt", "w", encoding="utf-8") as f:
                f.write(error_log[-2000:]) # Cắt lấy 2000 ký tự cuối để tránh log quá dài
            
            prompt = "@game-dev hãy fix lại code @player.py, log lỗi nằm trong @bug.txt"
            run_gemini_cli(prompt)
            continue # Lặp lại loop
            
        # Kịch bản 3: Người chơi tự tắt game bình thường (không lỗi, không feedback)
        else:
            print("\n[*] Game đóng bình thường. Kết thúc quá trình test.")
            break

def main():
    # Bước 1: Hiện UI lấy từ khóa
    p1, p2 = step_1_get_keywords()
    
    # Người dùng ấn 'X' tắt UI mà chưa submit
    if not p1 and not p2:
        print("Đã hủy quá trình.")
        return

    # Bước 2 & 3: Gõ prompt lấy skill từ AI
    prompt_skill = f"@skill-architect Người chơi A:{{{p1}}}, Người chơi B:{{{p2}}}, ghi đè kết quả vào file @skill_mechanics_extracted.md"
    run_gemini_cli(prompt_skill)
    
    # Bước 4: Chuyển luồng cơ chế vào file player.py
    prompt_mechanics = "@game-dev hãy code cơ chế có trong @skill_mechanics_extracted.md vào file @player.py"
    run_gemini_cli(prompt_mechanics)
    
    # Bước 5 & 6: Khởi động vòng lặp Test Game & Fix Bug
    loop_test_game()

if __name__ == "__main__":
    main()