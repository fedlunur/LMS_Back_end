"""
Utility functions for processing H5P files.

H5P files are ZIP archives containing:
- h5p.json: Metadata about the content
- content/content.json: The actual content parameters
- Libraries: Folders like H5P.Quiz-1.0/ containing library.json and assets
- Content files: Images, videos, etc. in the content/ folder
"""

import os
import json
import zipfile
import shutil
import tempfile
import logging
from pathlib import Path
from django.conf import settings
from django.core.files import File
from .models import H5PLibrary, H5PContent, H5PFile

logger = logging.getLogger(__name__)


def process_h5p_file(h5p_file_path, title=None):
    """
    Process an uploaded .h5p file and extract its contents.
    
    Args:
        h5p_file_path: Path to the uploaded .h5p file
        title: Optional title override for the content
    
    Returns:
        H5PContent instance
    """
    extract_dir = tempfile.mkdtemp(prefix='h5p_extract_')
    
    try:
        # Extract the ZIP file
        with zipfile.ZipFile(h5p_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Parse metadata
        h5p_json_path = os.path.join(extract_dir, 'h5p.json')
        if not os.path.exists(h5p_json_path):
            raise ValueError("Invalid H5P file: h5p.json not found")
        
        with open(h5p_json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Parse content parameters
        content_dir = os.path.join(extract_dir, 'content')
        content_json_path = os.path.join(content_dir, 'content.json')
        
        if os.path.exists(content_json_path):
            with open(content_json_path, 'r', encoding='utf-8') as f:
                parameters = json.load(f)
        else:
            parameters = {}
        
        # Extract and process libraries
        main_library = None
        libraries_dir = extract_dir
        
        # Find main library from metadata
        main_lib_name = metadata.get('mainLibrary', '')
        if not main_lib_name:
            raise ValueError("Invalid H5P file: mainLibrary not specified in h5p.json")
        
        # Process all libraries in the extract directory
        for item in os.listdir(libraries_dir):
            item_path = os.path.join(libraries_dir, item)
            if os.path.isdir(item_path) and '-' in item:
                # This looks like a library folder (e.g., H5P.Quiz-1.0)
                lib_json_path = os.path.join(item_path, 'library.json')
                if os.path.exists(lib_json_path):
                    with open(lib_json_path, 'r', encoding='utf-8') as f:
                        lib_data = json.load(f)
                    
                    lib_name = lib_data.get('machineName', '')
                    major = lib_data.get('majorVersion', 0)
                    minor = lib_data.get('minorVersion', 0)
                    patch = lib_data.get('patchVersion', 0)
                    
                    # Get or create library
                    library, created = H5PLibrary.objects.get_or_create(
                        name=lib_name,
                        major_version=major,
                        minor_version=minor,
                        patch_version=patch,
                        defaults={
                            'title': lib_data.get('title', lib_name),
                            'runnable': lib_data.get('runnable', False),
                            'preloaded_js': lib_data.get('preloadedJs', []),
                            'preloaded_css': lib_data.get('preloadedCss', []),
                            'dependencies': lib_data.get('preloadedDependencies', []),
                            'metadata_settings': lib_data,
                        }
                    )
                    
                    # If library was created, copy library files to media storage
                    if created:
                        library_target = os.path.join(settings.MEDIA_ROOT, 'h5p', 'libraries', item)
                        os.makedirs(library_target, exist_ok=True)
                        
                        # Copy all files from library directory
                        for root, dirs, files in os.walk(item_path):
                            for file_name in files:
                                src_file = os.path.join(root, file_name)
                                rel_path = os.path.relpath(src_file, item_path)
                                dst_file = os.path.join(library_target, rel_path)
                                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                                shutil.copy2(src_file, dst_file)
                        
                        library.library_path = os.path.join('h5p', 'libraries', item)
                        library.save()
                    
                    # Track main library
                    if lib_name == main_lib_name:
                        main_library = library
        
        if not main_library:
            raise ValueError(f"Main library '{main_lib_name}' not found in H5P file")
        
        # Create H5P content
        content_title = title or metadata.get('title', 'Untitled H5P Content')
        h5p_content = H5PContent.objects.create(
            title=content_title,
            library=main_library,
            parameters=parameters,
            metadata=metadata,
            content_path=''  # Will be set correctly after content ID is available
        )
        
        # Process content files (images, videos, etc.)
        # Always create the content directory, even if content_dir doesn't exist in the ZIP
        content_target_dir = os.path.join(settings.MEDIA_ROOT, 'h5p', 'content', str(h5p_content.id))
        os.makedirs(content_target_dir, exist_ok=True)
        
        # Always save content.json to the content directory (required for H5P rendering)
        content_json_dst = os.path.join(content_target_dir, 'content.json')
        if os.path.exists(content_json_path):
            try:
                shutil.copy2(content_json_path, content_json_dst)
            except Exception as e:
                # If copy fails, create from parameters
                with open(content_json_dst, 'w', encoding='utf-8') as f:
                    json.dump(parameters, f, ensure_ascii=False, indent=2)
        else:
            # Create content.json from parameters if it doesn't exist in the ZIP
            with open(content_json_dst, 'w', encoding='utf-8') as f:
                json.dump(parameters, f, ensure_ascii=False, indent=2)
        
        # Copy all content files (if content directory exists in the extracted ZIP)
        if os.path.exists(content_dir):
            file_count = 0
            for root, dirs, files in os.walk(content_dir):
                for file_name in files:
                    if file_name == 'content.json':
                        continue  # Skip content.json, already processed above
                    
                    src_file = os.path.join(root, file_name)
                    
                    # Calculate relative path from content_dir to preserve directory structure
                    rel_path = os.path.relpath(src_file, content_dir)
                    
                    # Skip if it's a directory (shouldn't happen, but just in case)
                    if not os.path.isfile(src_file):
                        continue
                    
                    dst_file = os.path.join(content_target_dir, rel_path)
                    
                    # Create directory structure if needed
                    dst_dir = os.path.dirname(dst_file)
                    if dst_dir and dst_dir != content_target_dir:
                        os.makedirs(dst_dir, exist_ok=True)
                    
                    try:
                        # Copy file to media storage
                        shutil.copy2(src_file, dst_file)
                        file_count += 1
                        
                        # Determine file type
                        ext = os.path.splitext(file_name)[1].lower()
                        file_type = 'other'
                        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']:
                            file_type = 'image'
                        elif ext in ['.mp4', '.webm', '.ogg']:
                            file_type = 'video'
                        elif ext in ['.mp3', '.wav', '.ogg']:
                            file_type = 'audio'
                        
                        # Create H5PFile record
                        with open(dst_file, 'rb') as f:
                            django_file = File(f, name=os.path.basename(rel_path))
                            h5p_file = H5PFile.objects.create(
                                content=h5p_content,
                                file=django_file,
                                original_path=rel_path,
                                file_type=file_type
                            )
                            # Manually set the path after saving
                            h5p_file.file.name = os.path.join('h5p', 'content', str(h5p_content.id), rel_path)
                            h5p_file.save()
                    except Exception as e:
                        # Log error but continue with other files
                        logger.warning(f"Failed to copy content file {rel_path}: {str(e)}")
                        continue
        
        # Update content_path
        h5p_content.content_path = os.path.join('h5p', 'content', str(h5p_content.id))
        h5p_content.save()
        
        return h5p_content
    
    finally:
        # Cleanup temporary extraction directory
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)


def get_h5p_library_url(library):
    """
    Get the URL prefix for a library's assets.
    """
    if library.library_path:
        return f"{settings.MEDIA_URL}{library.library_path}/"
    return f"{settings.MEDIA_URL}h5p/libraries/{library.name}-{library.major_version}.{library.minor_version}.{library.patch_version}/"


def get_h5p_content_url(content):
    """
    Get the URL prefix for content's assets.
    """
    if content.content_path:
        return f"{settings.MEDIA_URL}{content.content_path}/"
    return f"{settings.MEDIA_URL}h5p/content/{content.id}/"


def get_h5p_core_files(request=None):
    """
    Get URLs for H5P core files required for rendering.
    
    These files are the base H5P framework and must be loaded before any H5P content.
    
    Returns a dict with:
    - core_js_urls: List of JavaScript file URLs
    - core_css_urls: List of CSS file URLs
    
    Currently configured to use static files (production mode).
    To switch to CDN, comment out the static files section and uncomment the CDN section.
    """
    # Option 1: Use CDN (for development/testing)
    # Uncomment below and comment out static files section to use CDN
    # cdn_base = "https://cdn.jsdelivr.net/npm/@lumieducation/h5p-webcomponents@1/dist"
    # return {
    #     "core_js_urls": [
    #         f"{cdn_base}/h5p/js/h5p.js",
    #         f"{cdn_base}/h5p/js/h5p-event-dispatcher.js",
    #         f"{cdn_base}/h5p/js/h5p-content-type.js",
    #     ],
    #     "core_css_urls": [
    #         f"{cdn_base}/h5p/styles/h5p.css",
    #     ]
    # }
    
    # Option 2: Serve from static files (currently active - for production)
    # Make sure to download H5P core files and place them in static/h5p/core/
    # See H5P_CORE_FILES_SETUP.md for instructions
    base_url = ""
    if request:
        base_url = request.build_absolute_uri('/').rstrip('/')
    
    # Using static files path
    static_base = f"{base_url}/static/h5p/core"
    
    return {
        "core_js_urls": [
            f"{static_base}/js/h5p.js",
            f"{static_base}/js/h5p-event-dispatcher.js",
            f"{static_base}/js/h5p-content-type.js",
        ],
        "core_css_urls": [
            f"{static_base}/styles/h5p.css",
        ]
    }
