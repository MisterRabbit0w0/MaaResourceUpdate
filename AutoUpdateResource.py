import os
import json
import requests
import colorama
import time
import platform
import ctypes
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
from colorama import Fore, Style, init
from dotenv import load_dotenv

# 配置信息
REMOTE_BASE = "https://github.com/MaaAssistantArknights/MaaAssistantArknights/raw/dev/resource/"
GITHUB_REPO_API = "https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/contents/"
LOCAL_RESOURCE = Path("resource")
VERSION_FILE = LOCAL_RESOURCE / "version.json"
MANIFEST_FILE = LOCAL_RESOURCE / ".manifest.json"
# GITHUB_TOKEN = "your_token_here"

# 计时器
class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.elapsed_s = self.end - self.start 

# 全局错误状态
_error_occurred = False

def log(message: str, level: str = "info") -> None:
    """记录日志到文件并输出到控制台"""
    global _error_occurred
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}][{level.upper()}] {message}"
    
    # 写入日志文件
    with open("update.log", "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
    
    # 控制台彩色输出
    if level.lower() == "error":
        _error_occurred = True
        print(f"{Fore.RED}[{level}]{Style.RESET_ALL} {message}")
    elif level.lower() == "warn":
        print(f"{Fore.YELLOW}[{level}]{Style.RESET_ALL} {message}")
    else:
        print(f"{Fore.GREEN}[{level}]{Style.RESET_ALL} {message}")

def validate_github_token(token):
    # 验证 token 是否有效
    
    if not token:
        log("没有有效token", "warn")
        return False
        
    headers = {
        'Authorization': f'token {token}',
        'User-Agent': 'GitHubAPIHelper/1.0'
    }
    
    try:
        respose = requests.get(
            'http://api.github.com/user',
            headers=headers,
            timeout=5
        )

        if respose.status_code == 200:
            log("Token验证成功", "info")
            return True
        
        elif respose.status_code == 401:
            log("Token验证失败", "warn")

        else:
            log(f"Token异常，原因{respose.status_code}", "warn")
        
        return False

    except requests.exceptions.RequestException as e:
        log(f"网络连接异常：{str(e)}", "warn")
        return False

def get_remote_files_recursive(headers, path="resource"):
    """递归获取远程文件信息（处理分页）"""
    files = []
    url = f"{GITHUB_REPO_API}{path}?ref=dev"
    
    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            for item in response.json():
                if item["type"] == "dir":
                    files += get_remote_files_recursive(headers, item["path"])
                elif item["type"] == "file":
                    if item["path"].startswith("resource/"):
                        relative_path = item["path"][len("resource/"):]
                    else:
                        continue
                    files.append({
                        "path": relative_path,
                        "sha": item["sha"],
                        "size": item["size"],
                        "download_url": item["download_url"]
                    })
            
            if "next" in response.links:
                url = response.links["next"]["url"]
            else:
                url = None
                
        except Exception as e:
            log(f"获取目录 {path} 失败: {str(e)}", "error")
            return []
    
    return files

def load_local_manifest():
    """加载本地SHA记录"""
    try:
        with open(MANIFEST_FILE, "r") as f:
            data = json.load(f)
            if "files" not in data:
                return {"files": {}}
            return data
    except FileNotFoundError:
        return {"version": "1.0", "generated_at": datetime.now().isoformat(), "files": {}}

def save_local_manifest(manifest):
    """保存本地SHA记录"""
    manifest["generated_at"] = datetime.now().isoformat()
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

def check_file_update(remote_files):
    """检查需要更新的文件"""
    manifest = load_local_manifest()
    need_update = []
    
    for file in remote_files:
        local_record = manifest["files"].get(file["path"])
        if not local_record or local_record.get("sha1") != file["sha"]:
            need_update.append(file)
    
    return need_update

def download_with_retry(file_info, retries=3):
    """带重试的文件下载"""
    local_path = LOCAL_RESOURCE / file_info["path"]
    os.makedirs(local_path.parent, exist_ok=True)
    
    for attempt in range(retries):
        try:
            response = requests.get(file_info["download_url"], stream=True)
            response.raise_for_status()
            
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            log(f"下载重试 ({attempt+1}/{retries}) {file_info['path']}: {str(e)}", "warn")
    return False

def safe_update():
    log("启动安全增量更新", "info")
    
    # 获取远程文件信息
    log("正在获取远程文件清单...", "info")

    load_dotenv(dotenv_path="GITHUB_TOKEN.env")
    token = os.environ.get("GITHUB_TOKEN")
    
    headers = {
        # "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHubAPIHelper/1.0"
    }

    if validate_github_token(token):
        headers["Authorization"] = f"token {token}"

    # bef_tim = time.perf_counter()
    with Timer() as t:
        remote_files = get_remote_files_recursive(headers)

    log(f"消耗时间：{t.elapsed_s:.3f}s", "info")

    if not remote_files:
        log("无法获取远程文件列表", "error")
        return
    
    # 校验文件差异
    need_update = check_file_update(remote_files)
    if not need_update:
        log("所有文件均为最新状态", "info")
        return
    
    # 执行增量更新
    total = len(need_update)
    log(f"需要更新 {total} 个文件", "info")
    
    manifest = load_local_manifest()
    success = 0
    
    for idx, file in enumerate(need_update, 1):
        if download_with_retry(file):
            manifest["files"][file["path"]] = {
                "sha1": file["sha"],
                "size": file["size"],
                "modified": datetime.now().timestamp()
            }
            success += 1
            log(f"成功下载 {file['path']} | {idx}/{total}", "info")
        else:
            log(f"下载失败 {file['path']} | {idx}/{total}", "error")
            log("请检查网络连接", "error")
    
    # 保存最新记录
    save_local_manifest(manifest)
    if success == total:
        log(f"更新完成！成功 {success}/{total}", "info")
    else:
        log(f"更新异常！成功 {success}/{total}", "error")

if __name__ == "__main__":
    init(autoreset=True)
    safe_update()
    
    # 错误弹窗提示（仅Windows）
    if _error_occurred and platform.system() == "Windows":
        ctypes.windll.user32.MessageBoxW(
            0,
            "更新过程中发生错误，请查看 update.log 文件。",
            "自动更新错误",
            0x30  # MB_ICONWARNING
        )
