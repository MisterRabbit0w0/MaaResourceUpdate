import os
import sys
import json
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from typing import Dict, List, Optional, Set
import hashlib
import base64
from concurrent.futures import ThreadPoolExecutor
import logging
from datetime import datetime
from dotenv import load_dotenv, set_key

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GitHubFolderSync:
    def __init__(self, token: str, local_path: str = "./resource"):
        """
        初始化GitHub文件夹同步器
        
        Args:
            token: GitHub个人访问令牌
            local_path: 本地存储路径
        """
        self.token = token
        self.local_path = Path(local_path)
        self.api_base = "https://api.github.com"
        self.repo_owner = "MaaAssistantArknights"
        self.repo_name = "MaaAssistantArknights"
        self.branch = "dev"
        self.target_folder = "resource"
        
        # 创建本地目录
        self.local_path.mkdir(parents=True, exist_ok=True)
        
        # 文件状态缓存文件
        self.cache_file = self.local_path / ".sync_cache.json"
        
        # API请求头
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Folder-Sync"
        }
        
        # 统计信息
        self.stats = {
            "downloaded": 0,
            "skipped": 0,
            "deleted": 0,
            "total_files": 0
        }
    
    async def load_cache(self) -> Dict:
        """加载本地文件缓存"""
        if not self.cache_file.exists():
            return {}
        
        try:
            async with aiofiles.open(self.cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return {}
    
    async def save_cache(self, cache: Dict):
        """保存文件缓存"""
        try:
            cache["last_sync"] = datetime.now().isoformat()
            async with aiofiles.open(self.cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(cache, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def get_file_hash(self, file_path: Path) -> Optional[str]:
        """获取本地文件的SHA1哈希值"""
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            
            # 构造 git blob 对象
            header = f"blob {len(content)}\0".encode()
            git_object = header + content

            sha = hashlib.sha1(git_object).hexdigest()
            return sha
        
        except Exception as e:
            raise Exception(f"计算 {file_path} 哈希失败：{str(e)}")
    
    async def get_file_content(self, session: aiohttp.ClientSession, path: str) -> Optional[str]:
        """获取文件内容"""
        url = f"{self.api_base}/repos/{self.repo_owner}/{self.repo_name}/contents/{path}"
        params = {"ref": self.branch}
        
        try:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("type") == "file":
                        content = base64.b64decode(data["content"]).decode('utf-8')
                        return content
                elif response.status == 404:
                    logger.warning(f"文件不存在: {path}")
                else:
                    logger.error(f"获取文件失败 {path}: {response.status}")
        except Exception as e:
            logger.error(f"获取文件内容出错 {path}: {e}")
        
        return None
    
    async def check_version_difference(self) -> bool:
        """检查版本是否不同"""
        version_path = f"{self.target_folder}/version.json"
        local_version_file = self.local_path / "version.json"
        
        async with aiohttp.ClientSession() as session:
            remote_content = await self.get_file_content(session, version_path)
            
            if not remote_content:
                logger.error("无法获取远程version.json")
                return True  # 如果无法获取远程版本，假设需要更新
            
            # 检查本地版本文件
            if not local_version_file.exists():
                logger.info("本地version.json不存在，需要更新")
                return True
            
            try:
                async with aiofiles.open(local_version_file, 'r', encoding='utf-8') as f:
                    local_content = await f.read()
                
                # 比较JSON内容
                remote_json = json.loads(remote_content)
                local_json = json.loads(local_content)
                
                if remote_json != local_json:
                    logger.info("版本不同，需要更新")
                    return True
                else:
                    logger.info("版本相同，无需更新")
                    return False
                    
            except Exception as e:
                logger.error(f"比较版本时出错: {e}")
                return True
    
    async def get_directory_contents(self, session: aiohttp.ClientSession, path: str) -> List[Dict]:
        """获取目录内容"""
        url = f"{self.api_base}/repos/{self.repo_owner}/{self.repo_name}/contents/{path}"
        params = {"ref": self.branch}
        
        try:
            async with session.get(url, headers=self.headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"获取目录内容失败 {path}: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"获取目录内容出错 {path}: {e}")
            return []
    
    def should_download_file(self, file_info: Dict, local_file_path: Path, cache: Dict) -> bool:
        """判断是否需要下载文件"""
        file_path = file_info["path"]
        remote_sha = file_info.get("sha")
        
        # 如果文件不存在，必须下载
        if not local_file_path.exists():
            logger.debug(f"文件不存在，需要下载: {file_path}")
            return True
        
        # 检查缓存中的SHA值
        # git 的 sha 值计算逻辑不太一样
        cached_info = cache.get(file_path, {})
        cached_sha = cached_info.get("sha")
        
        # 如果远程SHA与缓存SHA相同，跳过
        if remote_sha and cached_sha == remote_sha:
            logger.debug(f"SHA值未变化，跳过: {file_path}")
            return False
        
        # 如果有远程SHA，计算本地文件SHA进行比较
        if remote_sha:
            local_sha = self.get_file_hash(local_file_path)
            if local_sha == remote_sha:
                # 更新缓存中的SHA值
                cache[file_path] = {
                    "sha": remote_sha,
                    "size": file_info.get("size", 0),
                    "last_modified": datetime.now().isoformat()
                }
                logger.debug(f"文件SHA值相同，跳过: {file_path}")
                return False
        
        # 其他情况都需要下载
        logger.debug(f"需要下载: {file_path}")
        return True
    
    async def download_file(self, session: aiohttp.ClientSession, file_info: Dict, 
                          local_file_path: Path, cache: Dict):
        """下载单个文件"""
        try:
            # 创建父目录
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 使用download_url直接下载文件内容
            download_url = file_info.get("download_url")
            if not download_url:
                logger.error(f"无法获取下载链接: {file_info['path']}")
                return
            
            async with session.get(download_url) as response:
                if response.status == 200:
                    content = await response.read()
                    async with aiofiles.open(local_file_path, 'wb') as f:
                        await f.write(content)
                    
                    # 更新缓存
                    cache[file_info["path"]] = {
                        "sha": file_info.get("sha"),
                        "size": file_info.get("size", 0),
                        "last_modified": datetime.now().isoformat()
                    }
                    
                    self.stats["downloaded"] += 1
                    logger.info(f"下载完成: {file_info['path']}")
                else:
                    logger.error(f"下载失败 {file_info['path']}: {response.status}")
        except Exception as e:
            logger.error(f"下载文件出错 {file_info['path']}: {e}")
    
    async def collect_all_remote_files(self, session: aiohttp.ClientSession, 
                                     remote_path: str) -> Dict[str, Dict]:
        """收集所有远程文件信息（带进度显示和并发优化）"""
        all_files = {}
        pending_dirs = [remote_path]
        processed_dirs = 0
        total_dirs = 1
        
        # 使用信号量限制并发请求数
        semaphore = asyncio.Semaphore(8)
        
        async def collect_directory_with_progress(path: str):
            nonlocal processed_dirs, total_dirs
            
            async with semaphore:
                try:
                    contents = await self.get_directory_contents(session, path)
                    processed_dirs += 1
                    
                    files_in_dir = 0
                    dirs_in_dir = 0
                    
                    for item in contents:
                        if item["type"] == "file":
                            all_files[item["path"]] = item
                            files_in_dir += 1
                        elif item["type"] == "dir":
                            pending_dirs.append(item["path"])
                            dirs_in_dir += 1
                    
                    total_dirs += dirs_in_dir
                    
                    # 动态进度显示
                    progress = (processed_dirs / total_dirs) * 100
                    logger.info(f"扫描进度: {processed_dirs}/{total_dirs} 目录 ({progress:.1f}%) | "
                              f"当前目录: {path.split('/')[-1]} ({files_in_dir}文件, {dirs_in_dir}子目录)")
                    
                except Exception as e:
                    logger.error(f"扫描目录失败 {path}: {e}")
                    processed_dirs += 1
        
        # 批量并发处理
        batch_size = 5  # 每批处理的目录数
        
        while pending_dirs:
            # 取出当前批次的目录
            current_batch = pending_dirs[:batch_size]
            pending_dirs = pending_dirs[batch_size:]
            
            if not current_batch:
                break
            
            # 并发处理当前批次
            tasks = [collect_directory_with_progress(path) for path in current_batch]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"扫描完成! 共找到 {len(all_files)} 个文件，扫描了 {processed_dirs} 个目录")
        return all_files
    
    async def cleanup_deleted_files(self, remote_files: Dict[str, Dict], cache: Dict):
        """清理远程已删除的本地文件"""
        remote_paths = set(remote_files.keys())
        cached_paths = set(cache.keys())
        
        # 找出本地有但远程没有的文件
        deleted_paths = cached_paths - remote_paths
        
        for deleted_path in deleted_paths:
            # 计算本地文件路径
            relative_path = deleted_path.replace(f"{self.target_folder}/", "", 1)
            local_file_path = self.local_path / relative_path
            
            if local_file_path.exists():
                try:
                    local_file_path.unlink()
                    logger.info(f"删除本地文件: {deleted_path}")
                    self.stats["deleted"] += 1
                except Exception as e:
                    logger.error(f"删除文件失败 {deleted_path}: {e}")
            
            # 从缓存中移除
            cache.pop(deleted_path, None)
    
    async def sync_folder(self):
        """同步整个文件夹"""
        logger.info("开始检查版本...")
        
        # 检查版本是否需要更新
        if not await self.check_version_difference():
            logger.info("版本已是最新，无需同步")
            return
        
        logger.info("版本已更新，开始增量同步...")
        
        # 加载缓存
        cache = await self.load_cache()
        
        # 创建会话
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=20)
        timeout = aiohttp.ClientTimeout(total=300)
        
        async with aiohttp.ClientSession(
            connector=connector, 
            timeout=timeout,
            headers=self.headers
        ) as session:
            
            # 收集所有远程文件信息
            logger.info("收集远程文件信息...")
            remote_files = await self.collect_all_remote_files(session, self.target_folder)
            self.stats["total_files"] = len(remote_files)
            
            # 清理已删除的文件
            await self.cleanup_deleted_files(remote_files, cache)
            
            # 准备下载任务
            download_tasks = []
            semaphore = asyncio.Semaphore(10)  # 限制并发数
            
            for file_path, file_info in remote_files.items():
                # 计算本地文件路径
                relative_path = file_path.replace(f"{self.target_folder}/", "", 1)
                local_file_path = self.local_path / relative_path
                
                # 检查是否需要下载
                if self.should_download_file(file_info, local_file_path, cache):
                    async def bounded_download(fi=file_info, lfp=local_file_path):
                        async with semaphore:
                            await self.download_file(session, fi, lfp, cache)
                    
                    download_tasks.append(bounded_download())
                else:
                    self.stats["skipped"] += 1
            
            # 执行所有下载任务
            if download_tasks:
                logger.info(f"开始下载 {len(download_tasks)} 个文件...")
                await asyncio.gather(*download_tasks, return_exceptions=True)
            else:
                logger.info("所有文件均为最新，无需下载")
        
        # 保存缓存
        await self.save_cache(cache)
        
        # 输出统计信息
        logger.info("=" * 50)
        logger.info("同步完成! 统计信息:")
        logger.info(f"总文件数: {self.stats['total_files']}")
        logger.info(f"下载文件: {self.stats['downloaded']}")
        logger.info(f"跳过文件: {self.stats['skipped']}")
        logger.info(f"删除文件: {self.stats['deleted']}")
        logger.info("=" * 50)
    
    def run_sync(self):
        """运行同步（同步接口）"""
        asyncio.run(self.sync_folder())

    async def validate_token(self, session: aiohttp.ClientSession, token: str) -> bool:
        """验证GitHub token是否有效"""
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Folder-Sync"
        }
        
        try:
            # 使用简单的API调用测试token
            url = f"{self.api_base}/user"
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    logger.info(f"Token验证成功! 用户: {user_data.get('login', 'Unknown')}")
                    return True
                elif response.status == 401:
                    logger.error("Token无效或已过期")
                    return False
                else:
                    logger.error(f"Token验证失败，状态码: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Token验证过程中出错: {e}")
            return False

def load_env_file():
    """加载.env文件"""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    return env_path

def save_token_to_env(token: str, env_path: Path):
    """保存token到.env文件"""
    try:
        # 如果.env文件不存在，创建它
        if not env_path.exists():
            env_path.touch()
            logger.info("创建了新的.env文件")
        
        # 使用python-dotenv的set_key函数安全地设置环境变量
        set_key(env_path, "GITHUB_TOKEN", token)
        logger.info("Token已保存到.env文件")
        
        # 同时设置到当前环境中
        os.environ["GITHUB_TOKEN"] = token
        
    except Exception as e:
        logger.error(f"保存token到.env文件失败: {e}")

def get_valid_token() -> str:
    """获取有效的GitHub token"""
    # 加载.env文件
    env_path = load_env_file()
    
    # 首先尝试从环境变量获取
    token = os.getenv("GITHUB_TOKEN")
    
    async def validate_token_async(token: str) -> bool:
        """异步验证token的包装函数"""
        syncer_temp = GitHubFolderSync(token)
        async with aiohttp.ClientSession() as session:
            return await syncer_temp.validate_token(session, token)
    
    # 如果有token，验证其有效性
    if token:
        print("发现现有token，正在验证...")
        try:
            is_valid = asyncio.run(validate_token_async(token))
            if is_valid:
                return token
            else:
                print("现有token无效，需要输入新的token")
        except Exception as e:
            print(f"验证token时出错: {e}")
    
    # 循环直到获得有效token
    while True:
        token = input("请输入您的GitHub Personal Access Token: ").strip()
        
        if not token:
            print("错误: Token不能为空")
            continue
        
        print("正在验证token...")
        try:
            is_valid = asyncio.run(validate_token_async(token))
            if is_valid:
                # 询问是否保存到.env文件
                save_choice = input("是否将token保存到.env文件？(y/n，默认为y): ").strip().lower()
                if save_choice != 'n':
                    save_token_to_env(token, env_path)
                return token
            else:
                print("Token无效，请检查并重新输入")
        except Exception as e:
            print(f"验证token时出错: {e}")
            print("请重新输入token")

def main():
    """主函数"""
    print("MAA Resource Updater")
    print("=" * 40)
    
    # 获取有效token
    try:
        token = get_valid_token()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        return
    except Exception as e:
        print(f"获取token时发生错误: {e}")
        return
    
    # 设置本地存储路径
    # local_path = input("请输入本地存储路径 (默认: ./resource): ").strip()
    # if not local_path:
        # local_path = "./resource"
    local_path = "./resource"

    # 创建同步器并运行
    syncer = GitHubFolderSync(token, local_path)
    
    try:
        syncer.run_sync()
    except KeyboardInterrupt:
        print("\n同步被用户中断")
    except Exception as e:
        print(f"同步过程中发生错误: {e}")
        logger.exception("详细错误信息:")

if __name__ == "__main__":
    main()