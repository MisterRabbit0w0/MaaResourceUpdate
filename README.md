# MaaResourceUpdate

供有网络条件的人调用 GitHub API 以更新 `MAA/resource` 下文件，半自动解放双手

### 编译

请先检查电脑中是否存在 Python 3.11 及以上版本。

下载项目源代码后，先运行

```shell
pip install -r requirements.txt
```

随后每次启动时，运行

```shell
python github_sync.py
```

以执行更新

### 直接使用

在 Actions 最新的 workflow 中找到 Artifacts 中的附件下载即可

## 更新方式

使用对比 `version.json` 文件的方式，如果版本文件更新则下拉所有列表中文件比较后更新

## Github TOKEN 获取

在 `Settings/Developer Settings/Personal access tokens/Tokens(classic)` 中选择 `Generate new token`

## 随MAA运行

将你需要的文件拖入 MAA 根目录下

在 MAA/设置/运行设置/开始前脚本中输入 `python github_sync.py` 或 `updater.exe`
