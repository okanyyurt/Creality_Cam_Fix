"""
Creality K1 / K1 Max / K1C Camera & Dashboard Bridge for OrcaSlicer
Zero-Root | Auto-Discovery | Stock Firmware Compatible

Automatically discovers Creality K1 printers on LAN, bridges the internal WebRTC stream
to an MJPEG / WebRTC stream, and hosts a unified bilingual control dashboard for OrcaSlicer.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import subprocess
import zipfile
import re
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GO2RTC_EXE = os.path.join(BASE_DIR, "go2rtc.exe")
CONFIG_PATH = os.path.join(BASE_DIR, "go2rtc.yaml")
CACHE_FILE = os.path.join(BASE_DIR, "last_known_ip.txt")
WWW_DIR = os.path.join(BASE_DIR, "www")
DASHBOARD_FILE = os.path.join(WWW_DIR, "dashboard.html")
INDEX_FILE = os.path.join(WWW_DIR, "index.html")

PORT_WEBRTC = 8000
GO2RTC_API_PORT = 1984
GO2RTC_VERSION = "v1.9.15"
GO2RTC_DOWNLOAD_URL = f"https://github.com/AlexxIT/go2rtc/releases/download/{GO2RTC_VERSION}/go2rtc_win64.zip"

def get_local_ip():
    """Gets the active local IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def check_k1_ip(ip, timeout=0.8):
    """Checks if an IP is a Creality K1/K1C/K1 Max with WebRTC enabled on port 8000."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        if s.connect_ex((ip, PORT_WEBRTC)) != 0:
            s.close()
            return False
        s.close()
        
        # Test webrtc_local endpoint
        url = f"http://{ip}:{PORT_WEBRTC}/call/webrtc_local"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False

def discover_printer_ip():
    """Finds the printer's IP automatically via OrcaSlicer, Cache, or fast subnet sweep."""
    print("[-] Searching for Creality K1 / K1 Max on your network...")
    
    # 1. Try to read active printer IP from OrcaSlicer Remote API (if open)
    try:
        req = urllib.request.Request("http://127.0.0.1:13130/api/v1/printer/devices")
        with urllib.request.urlopen(req, timeout=0.3) as resp:
            devs = json.loads(resp.read().decode('utf-8'))
            for d in devs.get('devices', []):
                ip = d.get('ip')
                if ip and check_k1_ip(ip, timeout=0.5):
                    print(f"[+] Found printer directly via OrcaSlicer API: {ip}")
                    save_cached_ip(ip)
                    return ip
    except Exception:
        pass

    # 2. Check last known IP from cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cached_ip = f.read().strip()
            if cached_ip and check_k1_ip(cached_ip, timeout=0.8):
                print(f"[+] Found printer at cached IP: {cached_ip}")
                return cached_ip
        except Exception:
            pass

    # 3. Fast multi-threaded subnet scan
    local_ip = get_local_ip()
    if local_ip != '127.0.0.1':
        prefix = ".".join(local_ip.split(".")[:3])
        print(f"[-] Scanning subnet {prefix}.1 - 254 for Creality WebRTC service...")
        
        candidates = [f"{prefix}.{i}" for i in range(1, 255)]
        with ThreadPoolExecutor(max_workers=50) as executor:
            results = executor.map(check_k1_ip, candidates)
            for ip, is_k1 in zip(candidates, results):
                if is_k1:
                    print(f"[+] Found printer at IP: {ip}")
                    save_cached_ip(ip)
                    return ip

    # 4. Check mDNS hostnames as fallback
    mdns_hosts = [
        "creality-k1-max.local",
        "k1-max.local",
        "creality-k1.local",
        "k1.local",
        "creality-k1c.local"
    ]
    for host in mdns_hosts:
        try:
            ip = socket.gethostbyname(host)
            if check_k1_ip(ip, timeout=0.8):
                print(f"[+] Found printer via hostname ({host}): {ip}")
                save_cached_ip(ip)
                return ip
        except Exception:
            pass

    return None

def save_cached_ip(ip):
    try:
        with open(CACHE_FILE, "w") as f:
            f.write(ip)
    except Exception:
        pass

def ensure_go2rtc():
    """Ensures go2rtc.exe is present, downloading it automatically if needed."""
    if os.path.exists(GO2RTC_EXE):
        return True
    
    print(f"[-] go2rtc.exe not found. Downloading official release ({GO2RTC_VERSION})...")
    zip_path = os.path.join(BASE_DIR, "go2rtc.zip")
    try:
        urllib.request.urlretrieve(GO2RTC_DOWNLOAD_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(BASE_DIR)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        print("[+] go2rtc.exe successfully downloaded and ready.")
        return True
    except Exception as e:
        print(f"[!] Failed to auto-download go2rtc: {e}")
        print(f"[!] Please manually download go2rtc.exe from https://github.com/AlexxIT/go2rtc/releases and place it in {BASE_DIR}")
        return False

def write_config(printer_ip):
    """Generates the go2rtc.yaml configuration file."""
    www_path = WWW_DIR.replace("\\", "/")
    config_content = f"""# Auto-generated by K1 Camera Bridge for OrcaSlicer
log:
  level: info

streams:
  k1: "webrtc:http://{printer_ip}:{PORT_WEBRTC}/call/webrtc_local#format=creality"

api:
  listen: "127.0.0.1:{GO2RTC_API_PORT}"
  static_dir: "{www_path}"

webrtc:
  listen: "127.0.0.1:8555"

rtsp:
  listen: "127.0.0.1:8554"
"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(config_content)
    print(f"[+] Configuration updated for printer IP: {printer_ip}")

    # Update dashboard and index HTML with active printer IP
    for html_file in [DASHBOARD_FILE, INDEX_FILE]:
        if os.path.exists(html_file):
            try:
                with open(html_file, "r", encoding="utf-8") as f:
                    content = f.read()
                content = re.sub(r'http://\d+\.\d+\.\d+\.\d+', f'http://{printer_ip}', content)
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                print(f"[!] Error updating {html_file}:", e)

def is_go2rtc_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{GO2RTC_API_PORT}/api/streams", timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False

def start_go2rtc():
    if not ensure_go2rtc():
        return None
    
    print("[-] Starting go2rtc background service...")
    cmd = [GO2RTC_EXE, "-c", CONFIG_PATH]
    
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0 # SW_HIDE

    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=startupinfo
    )
    return proc

def main():
    print("=" * 70)
    print("  Creality K1 / K1 Max / K1C Camera & Dashboard Bridge for OrcaSlicer")
    print("  Zero-Root | Auto-Discovery | Stock Firmware Compatible")
    print("=" * 70)

    printer_ip = discover_printer_ip()
    if not printer_ip:
        print("[!] Could not automatically find K1 printer on your network.")
        printer_ip = input("Enter your printer IP manually (e.g. 192.168.1.140): ").strip()
        if not printer_ip:
            print("[!] Exiting.")
            return

    write_config(printer_ip)
    
    proc = None
    if not is_go2rtc_running():
        proc = start_go2rtc()
        time.sleep(1.0)
    else:
        print("[+] go2rtc is already running. Reloading configuration...")
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{GO2RTC_API_PORT}/api/restart", data=b"{}", method="POST")
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("  [SUCCESS] CAMERA & DASHBOARD BRIDGE IS ONLINE")
    print("=" * 70)
    print(f"  Printer IP         : {printer_ip}")
    print(f"  OrcaSlicer URL     : http://127.0.0.1:{GO2RTC_API_PORT}/dashboard.html")
    print(f"  MJPEG Stream URL   : http://127.0.0.1:{GO2RTC_API_PORT}/api/stream.mjpeg?src=k1")
    print(f"  Direct Web View    : http://127.0.0.1:{GO2RTC_API_PORT}/dashboard.html")
    print("=" * 70)
    print("\nOrcaSlicer Configuration:")
    print("  1. In OrcaSlicer -> Prepare -> Printer Edit (pen icon) -> Basic Information")
    print("  2. Set 'Device UI' (print_host_webui) to:")
    print(f"     http://127.0.0.1:{GO2RTC_API_PORT}/dashboard.html")
    print("  3. Open 'Device' tab to see full printer controls + live camera!\n")
    print("Monitoring connection in background (Press Ctrl+C to stop)...\n")

    try:
        while True:
            time.sleep(10)
            if not check_k1_ip(printer_ip, timeout=1.5):
                print(f"[!] Warning: Lost connection to {printer_ip}. Checking if IP changed...")
                new_ip = discover_printer_ip()
                if new_ip and new_ip != printer_ip:
                    print(f"[+] Printer IP changed from {printer_ip} to {new_ip}!")
                    printer_ip = new_ip
                    write_config(printer_ip)
                    try:
                        req = urllib.request.Request(f"http://127.0.0.1:{GO2RTC_API_PORT}/api/restart", data=b"{}", method="POST")
                        urllib.request.urlopen(req, timeout=1.0)
                        print("[+] Bridge reloaded with new IP successfully!")
                    except Exception as e:
                        print("[!] Error restarting bridge:", e)
    except KeyboardInterrupt:
        print("\n[-] Stopping camera bridge...")
        if proc:
            proc.terminate()
        print("[-] Goodbye!")

if __name__ == "__main__":
    main()
