# updater.py - 初始化资源清单工具
import os
import json
import hashlib
from pathlib import Path

LOCAL_RESOURCE = Path("resource")
MANIFEST_FILE = LOCAL_RESOURCE / ".manifest.json"

def calculate_sha256(filepath):
    """计算文件的SHA256哈希值"""
    sha = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()
    except IOError as e:
        print(f"无法读取文件 {filepath}: {str(e)}")
        return None

def calculate_git_sha1(filepath):
    """计算与 GitHub 一致的 Git SHA-1 值"""
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        
        # 构造 Git blob 对象
        header = f"blob {len(content)}\0".encode()
        git_object = header + content
        
        # 计算 SHA-1
        sha = hashlib.sha1(git_object).hexdigest()
        return sha
    except Exception as e:
        print(f"计算 {filepath} 哈希失败: {str(e)}")
        return None

def generate_manifest():
    """生成初始清单文件"""
    if not LOCAL_RESOURCE.exists():
        print(f"❌ 资源目录 {LOCAL_RESOURCE} 不存在")
        return False

    manifest = {
        "version": "1.0",
        "generated_at": None,
        "files": {}
    }

    file_count = 0
    for filepath in LOCAL_RESOURCE.rglob("*"):
        if filepath.is_file() and filepath != MANIFEST_FILE:
            relative_path = str(filepath.relative_to(LOCAL_RESOURCE)).replace("\\", "/")
            file_hash = calculate_git_sha1(filepath)
            
            if file_hash:
                manifest["files"][relative_path] = {
                    "sha1": file_hash,
                    "size": filepath.stat().st_size,
                    "modified": filepath.stat().st_mtime
                }
                file_count += 1

    if file_count == 0:
        print("⚠️ 未找到可记录的文件")
        return False

    manifest["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    try:
        with open(MANIFEST_FILE, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"✅ 清单文件已生成 | 路径: {MANIFEST_FILE}")
        print(f"📊 统计: 记录了 {file_count} 个文件")
        return True
    except IOError as e:
        print(f"❌ 写入清单文件失败: {str(e)}")
        return False

if __name__ == "__main__":
    import time
    print("🛠️ 资源清单初始化工具")
    print(f"工作目录: {LOCAL_RESOURCE.absolute()}")
    
    if MANIFEST_FILE.exists():
        choice = input("检测到已有清单文件，是否覆盖？(y/n): ").lower()
        if choice != 'y':
            print("操作已取消")
            exit()
    
    start_time = time.time()
    success = generate_manifest()
    elapsed = time.time() - start_time
    
    if success:
        print(f"⏱️ 耗时: {elapsed:.2f} 秒")