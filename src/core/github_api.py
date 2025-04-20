import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
import queue
import os
from core.logger import Logger
from core.utils import Timer

logger = Logger()

class GitHubAPI:
    def __init__(self, config):
        self.config = config
        self._session = None
        self._thread_local = threading.local()
    
    def validate_token(self, token):
        """验证 GitHub token 是否有效"""
        if not token:
            logger.log("没有有效token，访问可能受到限制", "warn")
            return False
            
        headers = {
            'Authorization': f'token {token}',
            'User-Agent': 'GitHubAPIHelper/1.0'
        }
        
        try:
            response = requests.get(
                'http://api.github.com/user',
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                logger.log("Token验证成功", "info")
                return True
            
            elif response.status_code == 401:
                logger.log("Token验证失败，请检查token文件", "warn")
            else:
                logger.log(f"Token异常，原因{response.status_code}", "error")
            
            return False

        except requests.exceptions.RequestException as e:
            logger.log(f"网络连接异常：{str(e)}", "warn")
            return False
    
    def _get_session(self):
        """创建带自定义适配器的会话"""
        if not hasattr(self._thread_local, "session"):
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=50,
                pool_maxsize=100,
                max_retries=3,
                pool_block=False
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            self._thread_local.session = session
        return self._thread_local.session
    
    def fetch_directory_sync(self, headers, path):
        """获取目录内容"""
        files = []
        subdirs = []
        base_url = f"{self.config.GITHUB_REPO_API}{path}?ref=dev&per_page=100"
        page_urls = [base_url]
        session = self._get_session()
        
        try:
            first_res = session.get(base_url, headers=headers)
            first_res.raise_for_status()
            if "last" in first_res.links:
                total_pages = int(first_res.links["last"]["url"].split("&page=")[-1])
                page_urls = [f"{base_url}&page={i}" for i in range(1, total_pages+1)]
        except Exception as e:
            logger.log(f"预获取分页失败 {path}: {str(e)}", "warn")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_page = {
                executor.submit(session.get, url, headers=headers): url
                for url in page_urls
            }
            
            for future in as_completed(future_to_page):
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
                    logger.log(f"处理分页失败 {path}: {str(e)}", "error")
        
        return files, subdirs
    
    def get_remote_files_recursive(self, headers, initial_path="resource"):
        """递归获取远程文件列表"""
        files = []
        dir_queue = queue.Queue()
        dir_queue.put(initial_path)
        lock = threading.Lock()
        
        max_workers = min(20, (os.cpu_count() or 4) * 8)
        session = self._get_session()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            while True:
                while not dir_queue.empty() and len(futures) < max_workers * 2:
                    path = dir_queue.get()
                    future = executor.submit(
                        self._process_directory,
                        headers, path, dir_queue, files, lock
                    )
                    futures[future] = path
                    
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
    
    def _process_directory(self, headers, path, dir_queue, files, lock):
        """处理单个目录"""
        try:
            with Timer() as t:
                current_files, subdirs = self.fetch_directory_sync(headers, path)
            
            logger.log(f"Processed {path} in {t.elapsed_s:.3f}s, got {len(current_files)} files")
            
            with lock:
                files.extend(current_files)
            
            for subdir in subdirs:
                dir_queue.put(subdir)
            
        except Exception as e:
            logger.log(f"处理目录失败 {path}: {str(e)}", "error")