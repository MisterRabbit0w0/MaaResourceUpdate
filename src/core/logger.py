from colorama import Fore, Style, init
from datetime import datetime

class Logger:
    _error_occurred = False
    
    def __init__(self):
        init(autoreset=True)
    
    def log(self, message: str, level: str = "info") -> None:
        """记录日志到文件并输出到控制台"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}][{level.upper()}] {message}"
        
        # 写入日志文件
        with open("update.log", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
        
        # 控制台彩色输出
        if level.lower() == "error":
            self._error_occurred = True
            print(f"{Fore.RED}[{level}]{Style.RESET_ALL} {message}")
        elif level.lower() == "warn":
            print(f"{Fore.YELLOW}[{level}]{Style.RESET_ALL} {message}")
        else:
            print(f"{Fore.GREEN}[{level}]{Style.RESET_ALL} {message}")
    
    @property
    def error_occurred(self):
        return self._error_occurred