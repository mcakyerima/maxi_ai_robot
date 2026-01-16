import os
import subprocess
import datetime

# User home
USER = "mcaky"
PROJECT_DIRS = [
    fr"C:\Users\{USER}\Downloads",
    fr"C:\Users\{USER}\Documents",
    fr"C:\Users\{USER}\Pictures"
]

# Log file path
LOG_FILE = fr"C:\Users\{USER}\requirements_export_log.txt"

# Counters
total_projects = 0
success_count = 0
fail_count = 0

def log(message):
    """Write message to log file and print it to console."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)

def is_python_project(path):
    """Check if folder looks like a Python project."""
    return any(os.path.exists(os.path.join(path, marker)) for marker in ["venv", ".venv", "requirements.txt", "setup.py"])

def export_requirements(project_path):
    """Export requirements.txt for a project."""
    global success_count, fail_count

    venv_path = os.path.join(project_path, "venv", "Scripts", "python.exe")
    alt_venv_path = os.path.join(project_path, ".venv", "Scripts", "python.exe")
    requirements_file = os.path.join(project_path, "requirements.txt")

    if os.path.exists(venv_path):
        python_exec = venv_path
        log(f"🔎 Found venv → Using {venv_path}")
    elif os.path.exists(alt_venv_path):
        python_exec = alt_venv_path
        log(f"🔎 Found .venv → Using {alt_venv_path}")
    else:
        python_exec = "python"
        log("⚠️ No venv found → Falling back to global python")

    try:
        log("📦 Exporting dependencies with pip freeze ...")
        with open(requirements_file, "w", encoding="utf-8") as f:
            subprocess.run([python_exec, "-m", "pip", "freeze"], stdout=f, stderr=subprocess.DEVNULL, text=True)
        log(f"✅ requirements.txt updated → {requirements_file}\n")
        success_count += 1
    except Exception as e:
        log(f"❌ Failed to export in {project_path}: {e}\n")
        fail_count += 1

def main():
    global total_projects
    # Start log file fresh
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"📑 Python project dependency export log — {datetime.datetime.now()}\n\n")

    for base_dir in PROJECT_DIRS:
        if not os.path.exists(base_dir):
            continue
        log(f"📂 Scanning directory: {base_dir}")
        for root, dirs, files in os.walk(base_dir):
            if is_python_project(root):
                total_projects += 1
                log(f"\n🚀 Found Python project: {root}")
                export_requirements(root)

    # Summary
    log("\n🎉 Finished scanning all project folders.")
    log(f"📊 Summary: {total_projects} projects processed — ✅ {success_count} success | ❌ {fail_count} failed")

if __name__ == "__main__":
    main()
