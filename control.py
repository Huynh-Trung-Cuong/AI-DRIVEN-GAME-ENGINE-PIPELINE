import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

ROOT = os.path.dirname(os.path.abspath(__file__))
CODEX = r"C:\Users\DELL\AppData\Roaming\npm\codex.cmd"


def codex(prompt):
    codex_bin = CODEX

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    npm_bin = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm")
    env["PATH"] = npm_bin + os.pathsep + env.get("PATH", "")

    return subprocess.run(
        [
            codex_bin,
            "exec",
            "-m", "gpt-5.4",
            "-c", "model_reasoning_effort=medium",
            "-C", ROOT,
            "--skip-git-repo-check",
            "--sandbox", "workspace-write",
            "-",
        ],
        input=prompt,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        env=env,
    ).returncode


def get_keywords():
    root = tk.Tk()
    root.title("Keywords")
    root.geometry("350x200")

    data = {"p1": "", "p2": ""}

    tk.Label(root, text="Player A:").pack(pady=(10, 0))
    e1 = tk.Entry(root, width=40)
    e1.pack(pady=5)

    tk.Label(root, text="Player B:").pack(pady=(10, 0))
    e2 = tk.Entry(root, width=40)
    e2.pack(pady=5)

    def submit():
        data["p1"] = e1.get().strip()
        data["p2"] = e2.get().strip()
        if not data["p1"] or not data["p2"]:
            messagebox.showwarning("Warning", "Enter keywords for both players.")
            return
        root.destroy()

    tk.Button(root, text="Start", command=submit).pack(pady=15)
    root.mainloop()
    return data["p1"], data["p2"]


def run_game_loop():
    while True:
        log = open(os.path.join(ROOT, "latest_run.log"), "w", encoding="utf-8")
        game = subprocess.Popen(
            [sys.executable, "base.py"],
            cwd=ROOT,
            stdout=log,
            stderr=log,
        )

        root = tk.Tk()
        root.title("Feedback")
        root.geometry("350x250")
        root.attributes("-topmost", True)

        state = {"feedback": None, "crash": False}

        tk.Label(root, text="Bug / Feedback:").pack(pady=5)
        text = tk.Text(root, width=40, height=8)
        text.pack(pady=5)

        def submit():
            value = text.get("1.0", tk.END).strip()
            if not value:
                messagebox.showwarning("Warning", "Enter feedback before submitting.")
                return
            state["feedback"] = value
            root.destroy()

        def check():
            code = game.poll()
            if code is not None:
                state["crash"] = code != 0
                root.destroy()
            else:
                root.after(500, check)

        tk.Button(root, text="Submit & Fix", command=submit).pack(pady=5)
        root.after(500, check)
        root.mainloop()
        log.close()

        if state["feedback"]:
            if game.poll() is None:
                game.terminate()

            with open(os.path.join(ROOT, "feedback.txt"), "w", encoding="utf-8") as f:
                f.write(state["feedback"])

            codex("Call the tester agent. Read `feedback.txt` and `latest_run.log` if present, fix `player.py`, update `bug.txt`, and report the Definition of Done.")
            continue

        if state["crash"]:
            codex("Call the tester agent. Read `latest_run.log`, find the root cause, fix `player.py`, update `bug.txt`, and report the Definition of Done.")
            continue

        break


def main():
    p1, p2 = get_keywords()
    if not p1 and not p2:
        return

    codex(f"Call the skill_architect agent. Player A keywords: {p1}. Player B keywords: {p2}. Overwrite the design in `skill_mechanics_extracted.md`.")
    codex("Call the planner agent. Create `plan.txt` using `plan_template.txt` and do not modify `player.py`.")
    codex("Call the game_dev agent. Implement `plan.txt` in `player.py` using `template.txt` as the structural reference.")
    codex("Call the tester agent. Validate `player.py`, run tests if available, update `bug.txt`, and report the Definition of Done.")

    run_game_loop()


if __name__ == "__main__":
    main()
