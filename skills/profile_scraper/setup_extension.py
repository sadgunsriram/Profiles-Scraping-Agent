import os
import urllib.request
import zipfile
import io
import struct

def setup_signalhire_extension():
    ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "extensions", "signalhire"))
    manifest_path = os.path.join(ext_dir, "manifest.json")
    
    if os.path.exists(manifest_path):
        print(f"SignalHire extension already unpacked at {ext_dir}")
        return ext_dir
        
    print("Downloading and unpacking SignalHire extension...")
    os.makedirs(ext_dir, exist_ok=True)
    ext_id = 'aeidadjdhppdffggfgjpanbafaedankd'
    url = f'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=122.0.0.0&acceptformat=crx2,crx3&x=id%3D{ext_id}%26uc'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
        
    header_len = struct.unpack('<I', data[8:12])[0]
    zip_data = data[12 + header_len:]
    
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        z.extractall(ext_dir)
        
    metadata_dir = os.path.join(ext_dir, "_metadata")
    if os.path.exists(metadata_dir):
        import shutil
        shutil.rmtree(metadata_dir, ignore_errors=True)
        
    print(f"Successfully unpacked SignalHire extension to {ext_dir}")
    return ext_dir

if __name__ == "__main__":
    setup_signalhire_extension()
