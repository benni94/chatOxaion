import os
import sys
import subprocess
import venv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, "venv")
CRAWL4AI_DIR = os.path.join(BASE_DIR, "crawl4ai")

def run(cmd, cwd=None):
    print(f"➡️  {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=cwd)

def pip_exec():
    if sys.platform == "win32":
        return os.path.join(VENV_DIR, "Scripts", "pip.exe")
    return os.path.join(VENV_DIR, "bin", "pip")

def python_exec():
    if sys.platform == "win32":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")

# 1. Create venv if missing
if not os.path.exists(VENV_DIR):
    print("📦 Creating virtual environment...")
    venv.create(VENV_DIR, with_pip=True)

# 2. Upgrade pip
run([pip_exec(), "install", "--upgrade", "pip"])

# 3. Clone crawl4ai if missing
if not os.path.exists(CRAWL4AI_DIR):
    print("📥 Cloning crawl4ai repo...")
    run(["git", "clone", "https://github.com/unclecode/crawl4ai.git", CRAWL4AI_DIR])

# 4. Install required dependencies (skip madoka)
requirements = [
    "playwright",
    "beautifulsoup4",
    "faiss-cpu",
    "sentence-transformers",
    "tqdm",
    "gradio",
]
for pkg in requirements:
    run([pip_exec(), "install", pkg])

# 5. Ensure playwright browsers are installed
run([python_exec(), "-m", "playwright", "install", "chromium"])

print("\n✅ Setup complete!")
print(f"To use CLI: {python_exec()} query.py")
print(f"To run GUI: {python_exec()} app.py")
