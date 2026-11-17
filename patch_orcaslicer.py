"""
Automatic OrcaSlicer JSON Patcher for Creality K1 Series
Automatically finds Creality K1 / K1 Max / K1C machine profiles in OrcaSlicer
and sets 'print_host_webui' to the local camera dashboard.
"""

import os
import sys
import glob
import json
import shutil
import platform

TARGET_URL = "http://127.0.0.1:1984/dashboard.html"

def get_orca_machine_dirs():
    dirs = []
    system = platform.system()
    if system == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            base = os.path.join(appdata, "OrcaSlicer", "user")
            if os.path.exists(base):
                for user_dir in os.listdir(base):
                    m_dir = os.path.join(base, user_dir, "machine")
                    if os.path.isdir(m_dir):
                        dirs.append(m_dir)
    elif system == "Darwin": # macOS
        base = os.path.expanduser("~/Library/Application Support/OrcaSlicer/user")
        if os.path.exists(base):
            for user_dir in os.listdir(base):
                m_dir = os.path.join(base, user_dir, "machine")
                if os.path.isdir(m_dir):
                    dirs.append(m_dir)
    elif system == "Linux":
        base = os.path.expanduser("~/.config/OrcaSlicer/user")
        if os.path.exists(base):
            for user_dir in os.listdir(base):
                m_dir = os.path.join(base, user_dir, "machine")
                if os.path.isdir(m_dir):
                    dirs.append(m_dir)
    return dirs

def patch_profiles():
    machine_dirs = get_orca_machine_dirs()
    if not machine_dirs:
        print("[!] Could not locate OrcaSlicer user profiles directory.")
        return 0

    patched_count = 0
    for m_dir in machine_dirs:
        for json_file in glob.glob(os.path.join(m_dir, "*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Check if it's a Creality K1 profile
                name = data.get("name", "")
                inherits = data.get("inherits", "")
                host_type = data.get("host_type", "")

                is_k1 = any("K1" in s for s in [name, inherits, json_file]) or host_type == "crealityprint"

                if is_k1:
                    current_val = data.get("print_host_webui", "")
                    if current_val != TARGET_URL:
                        shutil.copy2(json_file, json_file + ".bak")
                        data["print_host_webui"] = TARGET_URL
                        with open(json_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4, ensure_ascii=False)
                        print(f"[+] Successfully patched: {os.path.basename(json_file)}")
                        patched_count += 1
                    else:
                        print(f"[*] Already patched: {os.path.basename(json_file)}")
            except Exception as e:
                pass

    return patched_count

if __name__ == "__main__":
    print("=" * 65)
    print("  OrcaSlicer Auto-Patcher for Creality K1 / K1 Max / K1C")
    print("=" * 65)
    count = patch_profiles()
    if count > 0:
        print(f"\n[SUCCESS] Patched {count} profile(s). Please restart OrcaSlicer to see changes!")
    else:
        print("\n[*] All profiles are already up to date or no K1 profiles found.")
    print("=" * 65)
