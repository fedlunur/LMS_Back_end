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
from pathlib import Path
from django.conf import settings
from django.core.files import File
from .models import H5PLibrary, H5PContent, H5PFile


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
            content_path=os.path.join('h5p', 'content', str(main_library.id))
        )
        
        # Process content files (images, videos, etc.)
        if os.path.exists(content_dir):
            content_target_dir = os.path.join(settings.MEDIA_ROOT, 'h5p', 'content', str(h5p_content.id))
            os.makedirs(content_target_dir, exist_ok=True)
            
            for root, dirs, files in os.walk(content_dir):
                for file_name in files:
                    if file_name == 'content.json':
                        continue  # Skip content.json, already processed
                    
                    src_file = os.path.join(root, file_name)
                    rel_path = os.path.relpath(src_file, content_dir)
                    
                    # Determine file type
                    ext = os.path.splitext(file_name)[1].lower()
                    file_type = 'other'
                    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']:
                        file_type = 'image'
                    elif ext in ['.mp4', '.webm', '.ogg']:
                        file_type = 'video'
                    elif ext in ['.mp3', '.wav', '.ogg']:
                        file_type = 'audio'
                    
                    # Copy file to media storage
                    dst_file = os.path.join(content_target_dir, rel_path)
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    
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
