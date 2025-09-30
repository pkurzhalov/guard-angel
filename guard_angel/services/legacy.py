
from __future__ import annotations
import os, subprocess, time
from pathlib import Path

KOLOBOK_DIR = os.getenv("KOLOBOK_DIR")
KOLOBOK_PY = (os.path.join(KOLOBOK_DIR, "venv", "bin", "python") if KOLOBOK_DIR else None)
PYTHON = (KOLOBOK_PY if (KOLOBOK_PY and os.path.exists(KOLOBOK_PY)) else "python")

def _ensure_dir() -> Path:
    p = Path(KOLOBOK_DIR)
    if not KOLOBOK_DIR:
        raise RuntimeError("KOLOBOK_DIR is not set")
    if not p.exists():
        raise RuntimeError("KOLOBOK_DIR is invalid or not accessible")
    return p

def _fmt(cmd, out, err, code):
    head = f"$ { (cmd[0] if isinstance(cmd, list) else str(cmd)) } (exit {code})"
    body = []
    if out: body.append("stdout:\n" + out.strip())
    if err: body.append("stderr:\n" + err.strip())
    return head + ("\n\n" + "\n\n".join(body) if body else "")

def run_look_for_load() -> str:
    _ensure_dir()
    cmd = [PYTHON, "kolobok.py"]  # legacy look_load.sh
    p = subprocess.run(cmd, cwd=KOLOBOK_DIR, capture_output=True, text=True)
    return _fmt(cmd, p.stdout, p.stderr, p.returncode)

def run_sign_rc() -> str:
    _ensure_dir()
    # legacy sign_RC.sh: start sign_rc_bot.py, then kolobok_RC.py
    p1 = subprocess.Popen([PYTHON, "sign_rc_bot.py"], cwd=KOLOBOK_DIR,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    p2 = subprocess.run([PYTHON, "kolobok_RC.py"], cwd=KOLOBOK_DIR,
                        capture_output=True, text=True)
    out1, err1 = "", ""
    if p1.poll() is not None:
        try:
            out1, err1 = p1.communicate(timeout=5)
        except Exception:
            pass
    out = (p2.stdout or "")
    err = (p2.stderr or "")
    if out1 or err1:
        out += ("\n--- sign_rc_bot.py ---\n" + (out1 or ""))
        if err1:
            err += ("\n" + err1)
    return _fmt(["sign_rc_bot.py","&","kolobok_RC.py"], out, err, p2.returncode)

def run_send_invoice() -> str:
    _ensure_dir()
    # legacy send_invoice.sh: merge_pdf2_0.py (bg) + accounting.py
    p_merge = subprocess.Popen([PYTHON, "merge_pdf2_0.py"], cwd=KOLOBOK_DIR,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    p = subprocess.run([PYTHON, "accounting.py"], cwd=KOLOBOK_DIR,
                       capture_output=True, text=True)
    mout, merr = "", ""
    if p_merge.poll() is not None:
        try:
            mout, merr = p_merge.communicate(timeout=5)
        except Exception:
            pass
    out = (p.stdout or "") + ("\n--- merge_pdf2_0.py ---\n" + (mout or ""))
    err = (p.stderr or "") + (("\n" + merr) if merr else "")
    return _fmt(["accounting.py","&","merge_pdf2_0.py"], out, err, p.returncode)

def run_count_salary() -> str:
    _ensure_dir()
    try:
        p = subprocess.run([PYTHON, "count_salary.py"], cwd=KOLOBOK_DIR,
                           capture_output=True, text=True, timeout=120)
        return _fmt(["count_salary.py"], p.stdout, p.stderr, p.returncode)
    except subprocess.TimeoutExpired as te:
        out = te.stdout or ""
        err = (te.stderr or "") + "\n[Timeout] Legacy count_salary.py exceeded 120s.\n"
        err += "If this was waiting for Google OAuth, run it once manually to cache credentials:\n"
        err += "  (activate legacy venv) && python count_salary.py\n"
        return _fmt(["count_salary.py"], out, err, code:=124)
    except Exception as e:
        return f"run_count_salary failed: {e}"

