import os
from pathlib import Path

# 基础配置
class Config:
    REMOTE_BASE = "https://github.com/MaaAssistantArknights/MaaAssistantArknights/raw/dev/resource/"
    GITHUB_REPO_API = "https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/contents/"
    LOCAL_RESOURCE = Path("resource")
    VERSION_FILE = LOCAL_RESOURCE / "version.json"
    MANIFEST_FILE = LOCAL_RESOURCE / ".manifest.json"
    
    # 从环境变量加载GitHub Token
    @staticmethod
    def load_github_token():
        from dotenv import load_dotenv
        load_dotenv(dotenv_path="GITHUB_TOKEN.env")
        return os.environ.get("GITHUB_TOKEN")