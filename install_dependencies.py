import subprocess
import sys

# List of required Python packages
packages = [
    "crawl4ai",
    "playwright",
    "sentence-transformers",
    "faiss-cpu",
    "beautifulsoup4"
]

def install_package(pkg):
    """Install a Python package using pip."""
    print(f"🔹 Installing {pkg}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

def check_and_install_packages(packages):
    """Check and install all required packages."""
    import importlib
    for pkg in packages:
        pkg_name = pkg.split("==")[0]  # remove version pin if exists
        try:
            importlib.import_module(pkg_name.replace("-", "_"))
            print(f"✅ {pkg} already installed")
        except ImportError:
            install_package(pkg)

def install_playwright_browsers():
    """Install Playwright browsers."""
    print("🌐 Installing Playwright browsers...")
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])

def main():
    print("🚀 Starting auto-installation of crawler dependencies...")
    check_and_install_packages(packages)
    install_playwright_browsers()
    print("🎉 All dependencies installed successfully!")

if __name__ == "__main__":
    main()
