#!/usr/bin/env python3
"""
Script to install (or upgrade) the MaterialX addon to the latest Blender version on macOS or Windows.

This script will:
1. Detect the latest Blender installation available on your system
2. Remove any existing MaterialX addon from that Blender installation
3. Copy the current addon to Blender's addon directory
4. Handle errors and edge-cases appropriately

Currently supported operating systems: macOS, Windows
"""

import os
import sys
import shutil
import glob
import subprocess
from pathlib import Path
import platform

def find_latest_blender():
    """Find the latest Blender installation on the current system (macOS or Windows)."""
    system = platform.system()
    
    # ---------------------------------
    # macOS logic
    # ---------------------------------
    if system == 'Darwin':
        blender_paths = [
            "/Applications/Blender.app",
            "/Applications/Blender 4.5.app",
            "/Applications/Blender 4.4.app",
            "/Applications/Blender 4.3.app",
            "/Applications/Blender 4.2.app",
            "/Applications/Blender 4.1.app",
            "/Applications/Blender 4.0.app",
        ]
        # Also check for any Blender*.app in Applications
        applications_dir = "/Applications"
        if os.path.exists(applications_dir):
            blender_apps = glob.glob(os.path.join(applications_dir, "Blender*.app"))
            blender_paths.extend(blender_apps)
    
    # ---------------------------------
    # Windows logic
    # ---------------------------------
    elif system == 'Windows':
        blender_paths = []
        program_dirs = []
        if 'PROGRAMFILES' in os.environ:
            program_dirs.append(os.environ['PROGRAMFILES'])
        if 'PROGRAMFILES(X86)' in os.environ:
            program_dirs.append(os.environ['PROGRAMFILES(X86)'])
        
        for base in program_dirs:
            foundation_dir = os.path.join(base, 'Blender Foundation')
            if os.path.exists(foundation_dir):
                blender_paths.extend(glob.glob(os.path.join(foundation_dir, 'Blender*')))
        
        # If Blender is on PATH, add its directory as a candidate
        blender_on_path = shutil.which('blender')
        if blender_on_path:
            blender_paths.append(os.path.dirname(blender_on_path))
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")
    
    # ---------------------------------
    # Evaluate candidates and pick the newest
    # ---------------------------------
    latest_blender = None
    latest_version = (0, 0, 0)
    
    for blender_path in blender_paths:
        if not os.path.exists(blender_path):
            continue
        
        # -----------------------------------------------------
        # 1. Try to parse version from the directory/app name
        # -----------------------------------------------------
        dir_name = os.path.basename(blender_path)
        version_str = dir_name.replace('Blender', '').replace('.app', '').strip()
        if version_str.startswith('-'):
            version_str = version_str[1:]
        
        parsed_from_name = False
        if version_str:
            try:
                version_parts = [int(x) for x in version_str.split('.')]
                while len(version_parts) < 3:
                    version_parts.append(0)
                version_tuple = tuple(version_parts[:3])
                parsed_from_name = True
            except ValueError:
                version_tuple = (0, 0, 0)
        else:
            version_tuple = (0, 0, 0)
        
        # -----------------------------------------------------
        # 2. If parsing failed, query the executable directly
        # -----------------------------------------------------
        if not parsed_from_name:
            if system == 'Darwin':
                blender_exe = os.path.join(blender_path, "Contents/MacOS/Blender")
            else:  # Windows
                blender_exe = os.path.join(blender_path, "blender.exe")
        
            if os.path.exists(blender_exe):
                try:
                    result = subprocess.run([blender_exe, "--version"], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and "Blender" in result.stdout:
                        version_match = result.stdout.split("Blender")[1].strip().split()[0]
                        version_parts = [int(x) for x in version_match.split('.')]
                        while len(version_parts) < 3:
                            version_parts.append(0)
                        version_tuple = tuple(version_parts[:3])
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    version_tuple = (0, 0, 0)
        
        # Keep track of the newest version found
        if version_tuple > latest_version:
            latest_version = version_tuple
            latest_blender = blender_path
    
    if not latest_blender:
        raise RuntimeError("Could not find any Blender installation on this system")
    
    print(f"Found Blender {latest_version[0]}.{latest_version[1]}.{latest_version[2]} at: {latest_blender}")
    return latest_blender
    


def get_blender_addon_directory(blender_path):
    """Get the addon directory for the given Blender installation."""
    system = platform.system()
    
    if system == 'Darwin':
        # macOS: ~/Library/Application Support/Blender/<version>/scripts/addons/
        home_dir = os.path.expanduser("~")
        support_dir = os.path.join(home_dir, "Library", "Application Support", "Blender")
    elif system == 'Windows':
        # Windows: %APPDATA%\Blender Foundation\Blender\<version>\scripts\addons
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA environment variable not set; cannot locate Blender addon directory")
        support_dir = os.path.join(appdata, "Blender Foundation", "Blender")
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")
    
    if not os.path.exists(support_dir):
        raise RuntimeError(f"Blender support directory not found: {support_dir}")
    
    # Find the version directory
    version_dirs = []
    for item in os.listdir(support_dir):
        item_path = os.path.join(support_dir, item)
        if os.path.isdir(item_path) and item.replace('.', '').isdigit():
            version_dirs.append(item)
    
    if not version_dirs:
        raise RuntimeError(f"No Blender version directories found in: {support_dir}")
    
    # Sort by version and get the latest
    version_dirs.sort(key=lambda x: [int(i) for i in x.split('.')], reverse=True)
    latest_version_dir = version_dirs[0]
    
    addon_dir = os.path.join(support_dir, latest_version_dir, "scripts", "addons")
    
    if not os.path.exists(addon_dir):
        # Try to create the directory
        try:
            os.makedirs(addon_dir, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Could not create addon directory {addon_dir}: {e}")
    
    print(f"Using addon directory: {addon_dir}")
    return addon_dir

def remove_existing_addon(addon_dir, addon_name="materialx_addon"):
    """Remove existing MaterialX addon if it exists."""
    existing_addon_path = os.path.join(addon_dir, addon_name)
    
    if os.path.exists(existing_addon_path):
        print(f"Removing existing addon: {existing_addon_path}")
        try:
            shutil.rmtree(existing_addon_path)
            print("Existing addon removed successfully")
        except OSError as e:
            raise RuntimeError(f"Could not remove existing addon {existing_addon_path}: {e}")
    else:
        print("No existing addon found")

def copy_addon_to_blender(addon_dir, source_dir):
    """Copy the current addon to Blender's addon directory."""
    addon_name = "materialx_addon"
    target_path = os.path.join(addon_dir, addon_name)
    
    print(f"Copying addon from {source_dir} to {target_path}")
    
    try:
        shutil.copytree(source_dir, target_path)
        print("Addon copied successfully")
    except OSError as e:
        raise RuntimeError(f"Could not copy addon to {target_path}: {e}")

def main():
    """Main installation function."""
    print("=" * 60)
    print("MaterialX Addon Installer")
    print("=" * 60)
    
    try:
        # Get the current script directory (project root)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        addon_source_dir = os.path.join(script_dir, "materialx_addon")
        
        # Verify the addon source exists
        if not os.path.exists(addon_source_dir):
            raise RuntimeError(f"Addon source directory not found: {addon_source_dir}")
        
        print(f"Addon source directory: {addon_source_dir}")
        
        # Find the latest Blender installation
        blender_path = find_latest_blender()
        
        # Get the addon directory
        addon_dir = get_blender_addon_directory(blender_path)
        
        # Remove existing addon
        remove_existing_addon(addon_dir)
        
        # Copy the new addon
        copy_addon_to_blender(addon_dir, addon_source_dir)
        
        print("=" * 60)
        print("Installation completed successfully!")
        print("=" * 60)
        print("To enable the addon in Blender:")
        print("1. Open Blender")
        print("2. Go to Edit > Preferences > Add-ons")
        print("3. Search for 'MaterialX'")
        print("4. Enable the 'Material: MaterialX Export' addon")
        print("=" * 60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 