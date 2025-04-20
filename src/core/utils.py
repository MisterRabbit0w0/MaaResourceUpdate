import time
import hashlib

class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.elapsed_s = self.end - self.start 

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
        raise Exception(f"计算 {filepath} 哈希失败: {str(e)}")