import platform
import ctypes
from src.config import Config
from src.core.github_api import GitHubAPI
from src.core.manifest import ManifestHandler
from src.core.downloader import DownloadManager
from src.core.logger import Logger
from src.core.utils import Timer

logger = Logger()

class AutoUpdater:
    def __init__(self):
        self.config = Config()
        self.github_api = GitHubAPI(self.config)
        self.manifest_handler = ManifestHandler(self.config)
        self.download_manager = DownloadManager(self.config)
    
    def safe_update(self):
        """安全增量更新"""
        logger.log("启动安全增量更新", "info")
        
        # 获取远程文件信息
        logger.log("正在获取远程文件清单...", "info")
        
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHubAPIHelper/1.0"
        }
        token = self.config.load_github_token()

        if self.github_api.validate_token(token):
            headers["Authorization"] = f"token {token}"

        with Timer() as t:
            remote_files = self.github_api.get_remote_files_recursive(headers=headers)

        logger.log(f"消耗时间：{t.elapsed_s:.3f}s", "info")

        if not remote_files:
            logger.log("无法获取远程文件列表", "error")
            return
        
        # 校验文件差异
        need_update = self.manifest_handler.check_updates(remote_files)
        if not need_update:
            logger.log("所有文件均为最新状态", "info")
            return
        
        # 执行增量更新
        total = len(need_update)
        logger.log(f"需要更新 {total} 个文件", "info")
        
        success = self.download_manager.process_downloads(need_update, self.manifest_handler)
        
        if success == total:
            logger.log(f"更新完成！成功 {success}/{total}", "info")
        else:
            logger.log(f"更新异常！成功 {success}/{total}", "error")

        ManifestHandler.generate

def main():
    updater = AutoUpdater()
    updater.safe_update()
    
    # 错误弹窗提示（仅Windows）
    if logger.error_occurred and platform.system() == "Windows":
        ctypes.windll.user32.MessageBoxW(
            0,
            "更新过程中发生错误，请查看 update.log 文件。",
            "自动更新错误",
            0x30  # MB_ICONWARNING
        )

if __name__ == "__main__":
    main()