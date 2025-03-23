import os
import json
import requests
import time
import platform
import ctypes
import threading
import queue
import requests.adapters
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
from colorama import Fore, Style, init
from dotenv import load_dotenv
from concurrent.futures import wait, FIRST_COMPLETED

# 配置信息
REMOTE_BASE = "https://github.com/MaaAssistantArknights/MaaAssistantArknights/raw/dev/resource/"
GITHUB_REPO_API = "https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/contents/"
LOCAL_RESOURCE = Path("resource")
VERSION_FILE = LOCAL_RESOURCE / "version.json"
MANIFEST_FILE = LOCAL_RESOURCE / ".manifest.json"
# GITHUB_TOKEN = "your_token_here"

# ADAPTER = requests.adapters.HTTPAdapter(
#     pool_connections=100,
#     pool_maxsize=100,
#     max_retries=3
# )
# requests.sessions.Session.mount('https://', ADAPTER)
# requests.sessions.Session.mount('http://', ADAPTER)

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

def create_custom_session():
    """创建带自定义适配器的会话"""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=50,   # 根据实际需求调整
        pool_maxsize=100,
        max_retries=3,
        pool_block=False
    )
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def fetch_directory_sync(headers, path, session):
    """优化后的目录获取（并发处理分页）"""
    files = []
    subdirs = []
    base_url = f"{GITHUB_REPO_API}{path}?ref=dev&per_page=100"
    page_urls = [base_url]
    
    # 预获取分页链接（减少后续请求）
    try:
        first_res = session.get(base_url, headers=headers)
        first_res.raise_for_status()
        if "last" in first_res.links:
            total_pages = int(first_res.links["last"]["url"].split("&page=")[-1])
            page_urls = [f"{base_url}&page={i}" for i in range(1, total_pages+1)]
    except Exception as e:
        log(f"预获取分页失败 {path}: {str(e)}", "warn")
    
    # 并发处理所有分页
    with ThreadPoolExecutor(max_workers=5) as executor:  # 分页并发数
        future_to_page = {
            executor.submit(session.get, url, headers=headers): url
            for url in page_urls
        }
        
        for future in as_completed(future_to_page):
            #TODO 加入速率限制
            # remaining
            # reset_time

            try:
                response = future.result()
                response.raise_for_status()
                data = response.json()
                for item in data:
                    if item["type"] == "dir":
                        subdirs.append(item["path"])
                    elif item["type"] == "file":
                        if item["path"].startswith("resource/"):
                            relative_path = item["path"][len("resource/"):]
                            files.append({
                                "path": relative_path,
                                "sha": item["sha"],
                                "size": item["size"],
                                "download_url": item["download_url"]
                            })
            except Exception as e:
                log(f"处理分页失败 {path}: {str(e)}", "error")
    
    return files, subdirs

def process_directory(headers, path, session, dir_queue, files, lock):
    """工作线程任务"""
    try:
        with Timer() as t:
            current_files, subdirs = fetch_directory_sync(headers, path, session)
        
        log(f"Processed {path} in {t.elapsed_s:.3f}s, got {len(current_files)} files")
        
        with lock:
            files.extend(current_files)
        
        for subdir in subdirs:
            dir_queue.put(subdir)
        
    except Exception as e:
        log(f"处理目录失败 {path}: {str(e)}", "error")

def get_remote_files_recursive(headers, initial_path="resource"):
    """优化后的并发控制器"""
    files = []
    dir_queue = queue.Queue()
    dir_queue.put(initial_path)
    lock = threading.Lock()
    
    # 动态调整工作线程数
    max_workers = min(20, (os.cpu_count() or 4) * 8)  # 推荐值：CPU核心数*4
    session = get_session()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 改为动态提交
        futures = {}
        
        while True:
            # 动态提交任务
            while not dir_queue.empty() and len(futures) < max_workers * 2:
                path = dir_queue.get()
                future = executor.submit(
                    process_directory,
                    headers, path, session, dir_queue, files, lock
                )
                futures[future] = path
                
            # 处理完成的任务
            done, _ = wait(
                futures.keys(),
                timeout=0.1,
                return_when=FIRST_COMPLETED
            )
            
            for future in done:
                del futures[future]
                
            if dir_queue.empty() and not futures:
                break

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

thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = create_custom_session()
    return thread_local.session

def download_with_retry(file_info, retries=3):
    """带重试的文件下载"""
    local_path = LOCAL_RESOURCE / file_info["path"]
    os.makedirs(local_path.parent, exist_ok=True)
    
    for attempt in range(retries):
        session = get_session()
        try:
            with session.get(file_info["download_url"], stream=True, timeout=10) as response:
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return True
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            log(f"下载重试 ({attempt+1}/{retries}) {file_info['path']}: {str(e)}", "warn")
    return False

def process_downloads_concurrently(need_update, manifest):
    """控制并发下载"""
    total = len(need_update)
    success = 0
    lock = threading.Lock()
    counter = {'val': 0}

    def update_progress(file_path, is_success):
        with lock:
            nonlocal success
            counter['val'] += 1
            idx = counter['val']
            if is_success:
                success += 1
                log(f"成功下载 {file_path} | {idx}/{total}", "info")
            else:
                log(f"下载失败 {file_path} | {idx}/{total}", "error")
                log("请检查网络连接", "error")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(download_with_retry, file): (file["path"], file)
            for file in need_update
        }

        for future in as_completed(futures):
            file_path, file = futures[future]
            try:
                if future.result():
                    with lock:
                            manifest["files"][file["path"]] = {
                            "sha1": file["sha"],
                            "size": file["size"],
                            "modified": datetime.now().timestamp()
                        }
                    update_progress(file_path, True)
                else:
                    update_progress(file_path, False)

            except Exception as e:
                log(f"任务异常 {file_path}: {str(e)}", "error")
                update_progress(file_path, False)
    
    return success, manifest

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
    
    manifest_before = load_local_manifest()
    success, maniest_after = process_downloads_concurrently(need_update, manifest_before)
    
    # 保存最新记录
    save_local_manifest(maniest_after)
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
