# MaaResourceUpdate

供有网络条件的人调用 GitHub API 以更新 `MAA/resource` 下文件，半自动解放双手

## 安装与使用

在一切开始之前，请在仓库根目录下创建 `GITHUB_TOKEN.env`，在文件中输入以下字段

```env
GITHUB_TOKEN={your_github_token_here}
```

### 编译

请先检查电脑中是否存在 Python 3.11 及以上版本。

下载项目源代码后，先运行

```shell
pip install -r requirements.txt
```

其中，{your_github_token_here} 填入你自己的 token

随后每次启动时，请在仓库根目录下运行

```shell
python -m src.main
```

以执行更新命令

### 直接使用

在 Actions 最新的 workflow 找到 Artifacts 中的压缩包下载即可

## 更新方式

目前采用与仓库同步的方式，即直接获取仓库下所有文件信息并与本地比对，有差异则更新。

## Github TOKEN 获取

在 `Settings/Developer Settings/Personal access tokens/Tokens(classic)` 中选择 `Generate new token`

## 随MAA运行

在 MAA/设置/运行设置/开始前脚本中输入 `python -m src.main` 或 `maaupdater.exe`

## TODO

- [] 调用系统对话框输入 token 而非去创建文件

- [] 加入 api 调用速率限制

- [] 加入无 token 或 调用 git 方法
