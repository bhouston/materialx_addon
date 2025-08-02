#!/usr/bin/env python3
"""
Command-line MaterialX Exporter for Blender

This script runs Blender in headless mode to export a specific material
from a .blend file to MaterialX format.

Usage:
    python cmdline_export.py <blend_file> <material_name> <output_mtlx_file> [options]

Examples:
    python cmdline_export.py scene.blend "MyMaterial" output.mtlx
    python cmdline_export.py scene.blend "MyMaterial" output.mtlx --export-textures --texture-path ./textures
    python cmdline_export.py scene.blend "MyMaterial" output.mtlx --version 1.38 --relative-paths

Arguments:
    blend_file      Path to the .blend file containing the material
    material_name   Name of the material to export
    output_mtlx_file Path for the output .mtlx file

Options:
    --export-textures    Export texture files (default: False)
    --texture-path PATH  Directory to export textures to (default: ./textures)
    --version VERSION    MaterialX version (default: 1.38)
    --relative-paths     Use relative paths for textures (default: True)
    --copy-textures      Copy texture files (default: True)
    --active-uvmap NAME  Active UV map name (default: UVMap)
    --blender-path PATH  Path to Blender executable (auto-detected if not specified)
    --help              Show this help message
"""

import argparse
import subprocess
import sys
import os
import tempfile
from pathlib import Path
import json
import shutil
import glob


import re


def _extract_version_from_path(path: str):
    """Try to extract a version tuple (major, minor, patch) from a Blender path."""
    # Look for "Blender 4.5" or "Blender4.5" etc.
    match = re.search(r"Blender\s*([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?", path, re.IGNORECASE)
    if match:
        parts = [int(p) if p is not None else 0 for p in match.groups()]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    return (0, 0, 0)


def find_blender_executable():
    """Find the newest Blender executable on the system."""
    # Accumulate candidate paths
    possible_paths = []
    
    # macOS
    possible_paths.extend([
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/Applications/Blender/blender.app/Contents/MacOS/blender",
    ])
    
    # Linux
    possible_paths.extend([
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/opt/blender/blender",
    ])
    
    # Windows – search common install locations, including versioned folders
    if os.name == "nt":
        program_dirs = []
        if 'PROGRAMFILES' in os.environ:
            program_dirs.append(os.environ['PROGRAMFILES'])
        if 'PROGRAMFILES(X86)' in os.environ:
            program_dirs.append(os.environ['PROGRAMFILES(X86)'])
        
        for base in program_dirs:
            foundation_dir = os.path.join(base, 'Blender Foundation')
            if os.path.exists(foundation_dir):
                # Blender\blender.exe OR Blender 4.0\blender.exe etc.
                for exe in glob.glob(os.path.join(foundation_dir, 'Blender*', 'blender.exe')):
                    possible_paths.append(exe)

    
    # Check if blender is in PATH (cross-platform)
    blender_on_path = shutil.which("blender" if os.name != "nt" else "blender.exe")
    if blender_on_path:
        possible_paths.append(blender_on_path)
    
    # Deduplicate
    possible_paths = list(dict.fromkeys(possible_paths))

    # Evaluate candidates and pick newest version
    latest_path = None
    latest_version = (0, 0, 0)
    for path in possible_paths:
        if not (os.path.exists(path) and os.access(path, os.X_OK)):
            continue
        version = _extract_version_from_path(path)
        # If we couldn't parse version from path, fall back to --version query (expensive)
        if version == (0, 0, 0):
            try:
                result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and "Blender" in result.stdout:
                    match = re.search(r"Blender\s+([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", result.stdout)
                    if match:
                        parts = [int(p) if p is not None else 0 for p in match.groups()]
                        while len(parts) < 3:
                            parts.append(0)
                        version = tuple(parts[:3])
            except Exception:
                pass
        if version > latest_version:
            latest_version = version
            latest_path = path
    return latest_path


def create_blender_script(blend_file, material_name, output_mtlx_file, options, project_root):
    """Create a temporary Blender Python script to perform the export."""
    
    # Convert options to Python literal format
    options_str = str(options).replace("'", '"')
    
    # Convert file paths to POSIX style so they are safe to embed in the
    # generated script regardless of host operating system (Blender on
    # Windows happily accepts forward slashes).
    safe_blend_path = Path(blend_file).resolve().as_posix()
    safe_output_path = Path(output_mtlx_file).resolve().as_posix()
    project_root_posix = Path(project_root).resolve().as_posix()
    
    script_content = f'''
import sys, os
# Ensure our addon is importable
root_dir = r"{project_root_posix}"
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import bpy
import logging
import sys
import os

# Simple stdout logger
logger = logging.getLogger("MaterialXExporter")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(stream=sys.stdout)
_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(_handler)

try:
    # Import the MaterialX exporter
    from materialx_addon.blender_materialx_exporter import export_material_to_materialx
    
    # Load the blend file
    print(f"Loading blend file: {safe_blend_path}")
    bpy.ops.wm.open_mainfile(filepath="{safe_blend_path}")
    
    # Find the material
    material = bpy.data.materials.get("{material_name}")
    if not material:
        print(f"ERROR: Material '{material_name}' not found in the blend file")
        print("Available materials:")
        for mat in bpy.data.materials:
            print(f"  - {{mat.name}}")
        sys.exit(1)
    
    print(f"Found material: {{material.name}}")
    
    # Export options
    export_options = {options_str}
    
    # Export the material
    print(f"Exporting material to: {safe_output_path}")
    success = export_material_to_materialx(material, "{safe_output_path}", logger, export_options)
    
    if success:
        print("SUCCESS: Material exported successfully")
        sys.exit(0)
    else:
        print("ERROR: Failed to export material")
        sys.exit(1)
        
except ImportError as e:
    print(f"ERROR: Failed to import MaterialX exporter: {{e}}")
    print("Make sure the materialx_addon directory is in the same directory as this script")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
    
    return script_content


def run_blender_export(blend_file, material_name, output_mtlx_file, options, blender_path=None, verbose=False):
    """Run Blender in headless mode to export the material."""
    
    # Find Blender executable if not provided
    if not blender_path:
        blender_path = find_blender_executable()
        if not blender_path:
            print("ERROR: Blender executable not found!")
            print("Please install Blender or specify the path with --blender-path")
            return False
    
    print(f"Using Blender executable: {blender_path}")
    
    # Create temporary script file
    project_root = os.path.dirname(os.path.abspath(__file__))
    script_content = create_blender_script(blend_file, material_name, output_mtlx_file, options, project_root)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        script_path = f.name
        f.write(script_content)
    
    try:
        # Prepare Blender command
        cmd = [
            blender_path,
            "--background",              # Headless
            "--factory-startup",         # Skip user prefs/add-ons for speed
            "--disable-autoexec",        # Safety
            "--python", script_path,
            "--",                        # End of Blender options
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        
        if verbose:
            # Stream output live
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            try:
                for line in process.stdout:
                    print(line.rstrip())
                process.wait()
            except KeyboardInterrupt:
                process.kill()
                raise
            returncode = process.returncode
        else:
            # Run Blender and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
            returncode = result.returncode
        # Evaluate result
        if returncode == 0 and os.path.exists(output_mtlx_file):
            print(f"SUCCESS: Material exported to {output_mtlx_file}")
            return True
        else:
            print(f"ERROR: Blender process failed or output file missing (code={returncode})")
            return False
            
    finally:
        # Clean up temporary script
        try:
            os.unlink(script_path)
        except:
            pass


def main():
    """Main function to handle command-line arguments and run the export."""
    parser = argparse.ArgumentParser(
        description="Export a material from a Blender file to MaterialX format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Required arguments
    parser.add_argument("blend_file", help="Path to the .blend file")
    parser.add_argument("material_name", help="Name of the material to export")
    parser.add_argument("output_mtlx_file", help="Path for the output .mtlx file")
    
    # Optional arguments
    parser.add_argument("--export-textures", action="store_true", 
                       help="Export texture files (default: False)")
    parser.add_argument("--texture-path", default="./textures",
                       help="Directory to export textures to (default: ./textures)")
    parser.add_argument("--version", default="1.38",
                       help="MaterialX version (default: 1.38)")
    parser.add_argument("--relative-paths", action="store_true", default=True,
                       help="Use relative paths for textures (default: True)")
    parser.add_argument("--copy-textures", action="store_true", default=True,
                       help="Copy texture files (default: True)")
    parser.add_argument("--active-uvmap", default="UVMap",
                       help="Active UV map name (default: UVMap)")
    parser.add_argument("--blender-path",
                       help="Path to Blender executable (auto-detected if not specified)")
    parser.add_argument("--verbose", action="store_true", help="Stream Blender output in real-time")
    
    args = parser.parse_args()
    
    # Validate input files
    if not os.path.exists(args.blend_file):
        print(f"ERROR: Blend file not found: {args.blend_file}")
        return 1
    
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(args.output_mtlx_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Prepare export options
    options = {
        'export_textures': args.export_textures,
        'texture_path': args.texture_path,
        'materialx_version': args.version,
        'relative_paths': args.relative_paths,
        'copy_textures': args.copy_textures,
        'active_uvmap': args.active_uvmap,
    }
    
    print("=" * 60)
    print("MaterialX Command-Line Exporter")
    print("=" * 60)
    print(f"Blend file: {args.blend_file}")
    print(f"Material name: {args.material_name}")
    print(f"Output file: {args.output_mtlx_file}")
    print(f"Options: {options}")
    print("=" * 60)
    
    # Run the export
    success = run_blender_export(
        args.blend_file,
        args.material_name,
        args.output_mtlx_file,
        options,
        args.blender_path,
        args.verbose
    )
    
    if success:
        print("Export completed successfully!")
        return 0
    else:
        print("Export failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 