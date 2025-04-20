import json
import os
from datetime import datetime
from pathlib import Path
from core.utils import calculate_git_sha1
from core.logger import Logger

logger = Logger()

class ManifestHandler:
    def __init__(self, config):
        self.config = config
    
    def generate(self):
        """生成初始清单文件"""
        if not self.config.LOCAL_RESOURCE.exists():
            logger.log(f"资源目录 {self.config.LOCAL_RESOURCE} 不存在", 'error')
            return False

        manifest = {
            "version": "1.0",
            "generated_at": None,
            "files": {}
        }

        file_count = 0
        for filepath in self.config.LOCAL_RESOURCE.rglob("*"):
            if filepath.is_file() and filepath != self.config.MANIFEST_FILE:
                relative_path = str(filepath.relative_to(self.config.LOCAL_RESOURCE)).replace("\\", "/")
                try:
                    file_hash = calculate_git_sha1(filepath)
                    if file_hash:
                        manifest["files"][relative_path] = {
                            "sha1": file_hash,
                            "size": filepath.stat().st_size,
                            "modified": filepath.stat().st_mtime
                        }
                        file_count += 1
                except Exception as e:
                    logger.log(str(e), 'error')

        if file_count == 0:
            logger.log("未找到可记录的文件", 'warn')
            return False

        manifest["generated_at"] = datetime.now().isoformat()
        
        try:
            with open(self.config.MANIFEST_FILE, "w") as f:
                json.dump(manifest, f, indent=2)
            logger.log(f"清单文件已生成 | 路径: {self.config.MANIFEST_FILE}")
            logger.log(f"统计: 记录了 {file_count} 个文件")
            return True
        except IOError as e:
            logger.log(f"写入清单文件失败: {str(e)}", 'error')
            return False
    
    def load(self):
        """加载本地清单文件"""
        if not os.path.exists(self.config.MANIFEST_FILE):
            logger.log("未找到清单文件，开始生成")
            self.generate()

        try:
            with open(self.config.MANIFEST_FILE, "r") as f:
                data = json.load(f)
                if "files" not in data:
                    return {"files": {}}
                return data
        except FileNotFoundError:
            return {"version": "1.0", "generated_at": datetime.now().isoformat(), "files": {}}
        except json.JSONDecodeError as e:
            logger.log(f"清单文件解析失败: {str(e)}", 'error')
            return {"version": "1.0", "generated_at": datetime.now().isoformat(), "files": {}}
    
    def save(self, manifest):
        """保存清单文件"""
        manifest["generated_at"] = datetime.now().isoformat()
        try:
            with open(self.config.MANIFEST_FILE, "w") as f:
                json.dump(manifest, f, indent=2)
            return True
        except IOError as e:
            logger.log(f"保存清单文件失败: {str(e)}", 'error')
            return False
    
    def check_updates(self, remote_files):
        """检查需要更新的文件"""
        manifest = self.load()
        need_update = []
        
        for file in remote_files:
            local_record = manifest["files"].get(file["path"])
            if not local_record or local_record.get("sha1") != file["sha"]:
                need_update.append(file)
        
        return need_update