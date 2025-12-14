"""
Script to download and set up H5P core files for static file serving.

This script downloads H5P core files from jsDelivr CDN and sets them up
in the static/h5p/core/ directory structure.

Run this script once to set up H5P core files:
    python setup_h5p_core_files.py
"""

import os
import urllib.request
from pathlib import Path

# Base directory (where this script is located)
BASE_DIR = Path(__file__).resolve().parent

# Directory structure
STATIC_DIR = BASE_DIR / 'static' / 'h5p' / 'core'
JS_DIR = STATIC_DIR / 'js'
STYLES_DIR = STATIC_DIR / 'styles'

# CDN base URL
CDN_BASE = "https://cdn.jsdelivr.net/npm/@lumieducation/h5p-webcomponents@1/dist/h5p"

# Files to download
FILES_TO_DOWNLOAD = {
    'js': [
        'js/h5p.js',
        'js/h5p-event-dispatcher.js',
        'js/h5p-content-type.js',
    ],
    'styles': [
        'styles/h5p.css',
    ]
}


def download_file(url, destination):
    """Download a file from URL to destination."""
    try:
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, destination)
        print(f"✓ Saved to {destination}")
        return True
    except Exception as e:
        print(f"✗ Error downloading {url}: {e}")
        return False


def setup_h5p_core_files():
    """Download and set up H5P core files."""
    print("Setting up H5P core files...")
    print(f"Base directory: {BASE_DIR}")
    print()
    
    # Create directories
    print("Creating directory structure...")
    JS_DIR.mkdir(parents=True, exist_ok=True)
    STYLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created {JS_DIR}")
    print(f"✓ Created {STYLES_DIR}")
    print()
    
    # Download JS files
    print("Downloading JavaScript files...")
    js_success = 0
    for file_path in FILES_TO_DOWNLOAD['js']:
        filename = os.path.basename(file_path)
        url = f"{CDN_BASE}/{file_path}"
        destination = JS_DIR / filename
        
        if download_file(url, destination):
            js_success += 1
    print()
    
    # Download CSS files
    print("Downloading CSS files...")
    css_success = 0
    for file_path in FILES_TO_DOWNLOAD['styles']:
        filename = os.path.basename(file_path)
        url = f"{CDN_BASE}/{file_path}"
        destination = STYLES_DIR / filename
        
        if download_file(url, destination):
            css_success += 1
    print()
    
    # Summary
    total_files = len(FILES_TO_DOWNLOAD['js']) + len(FILES_TO_DOWNLOAD['styles'])
    total_success = js_success + css_success
    
    print("=" * 50)
    print(f"Download Summary:")
    print(f"  JavaScript files: {js_success}/{len(FILES_TO_DOWNLOAD['js'])}")
    print(f"  CSS files: {css_success}/{len(FILES_TO_DOWNLOAD['styles'])}")
    print(f"  Total: {total_success}/{total_files}")
    print()
    
    if total_success == total_files:
        print("✓ All files downloaded successfully!")
        print()
        print("Next steps:")
        print("1. Run: python manage.py collectstatic")
        print("2. Restart your Django server")
        print("3. Verify the files are accessible at /static/h5p/core/")
    else:
        print("⚠ Some files failed to download. Please check the errors above.")
        print("You may need to download them manually or check your internet connection.")


if __name__ == '__main__':
    setup_h5p_core_files()
