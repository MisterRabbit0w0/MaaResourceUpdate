from datetime import datetime
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from core.logger import Logger

logger = Logger()

class DownloadManager:
    def __init__(self, config):
        self.config = config
        self._thread_local = threading.local()
    
    def _get_session(self):
        """获取线程局部会话"""
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
    
    def download_with_retry(self, file_info, retries=3):
        """带重试的文件下载"""
        local_path = self.config.LOCAL_RESOURCE / file_info["path"]
        os.makedirs(local_path.parent, exist_ok=True)
        
        for attempt in range(retries):
            session = self._get_session()
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
                logger.log(f"下载重试 ({attempt+1}/{retries}) {file_info['path']}: {str(e)}", "warn")
        return False
    
    def process_downloads(self, need_update, manifest_handler):
        """并发下载文件"""
        total = len(need_update)
        success = 0
        lock = threading.Lock()
        counter = {'val': 0}
        manifest = manifest_handler.load()

        def update_progress(file_path, is_success):
            with lock:
                nonlocal success
                counter['val'] += 1
                idx = counter['val']
                if is_success:
                    success += 1
                    logger.log(f"成功下载 {file_path} | {idx}/{total}", "info")
                else:
                    logger.log(f"下载失败 {file_path} | {idx}/{total}", "error")
                    logger.log("请检查网络连接", "error")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.download_with_retry, file): (file["path"], file)
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
                    logger.log(f"任务异常 {file_path}: {str(e)}", "error")
                    update_progress(file_path, False)
        
        # 保存更新后的清单
        manifest_handler.save(manifest)
        return success