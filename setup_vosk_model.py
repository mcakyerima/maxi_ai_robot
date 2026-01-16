#!/usr/bin/env python3
"""
Setup script to download and prepare Vosk model for wake word detection
"""

import os
import urllib.request
import zipfile
import sys

def download_model():
    """Download and extract Vosk model with progress bar"""
    
    model_url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
    model_zip = "vosk-model-en-us-0.22.zip"
    model_dir = "vosk-model-en-us-0.22"
    
    if os.path.exists(model_dir):
        print(f"✅ Model already exists at {model_dir}")
        return True
    
    print("📥 Downloading Vosk model (this may take a while, ~1.8GB)...")
    
    try:
        # First install tqdm if not already available
        try:
            from tqdm import tqdm
        except ImportError:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
            from tqdm import tqdm

        class DownloadProgressBar(tqdm):
            def update_to(self, b=1, bsize=1, tsize=None):
                if tsize is not None:
                    self.total = tsize
                self.update(b * bsize - self.n)

        # Download with progress bar
        with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=model_zip) as t:
            urllib.request.urlretrieve(
                model_url,
                filename=model_zip,
                reporthook=t.update_to
            )
        
        print("✅ Download completed")
        
        # Extract the model
        print("📦 Extracting model...")
        with zipfile.ZipFile(model_zip, 'r') as zip_ref:
            zip_ref.extractall('.')
        
        # Clean up zip file
        os.remove(model_zip)
        
        print(f"✅ Model extracted to {model_dir}")
        return True
        
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        return False

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "vosk"])
        print("✅ Dependencies installed")
        return True
    except Exception as e:
        print(f"❌ Error installing dependencies: {e}")
        return False

if __name__ == "__main__":
    print("🤖 Setting up Vosk Wake Word Detector")
    print("=" * 40)
    
    # Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Download model
    if not download_model():
        sys.exit(1)
    
    print("\n🎯 Setup Summary:")
    print("- Vosk package installed")
    print("- English model downloaded (~1.8GB)")
    print("- Ready for wake word detection!")
    print("\n💡 Usage: Replace your existing WakeWordDetector import")
    print("   The new detector is a drop-in replacement for Porcupine.")