# MaaResourceUpdate

供有网络条件的人调用 GitHub API 以更新 `MAA/resource` 下文件，半自动解放双手

## 安装与使用

下载本项目源代码，或在 `releases` 中找封装的exe下载，解压至MAA主目录下

初次使用时，请运行 `upgrade.exe` 以初始化 `reource/.manifest.json`

本项目通过使用 Github Token 防止调用次数限制，请勿在同一时间多次运行程序

首次运行 `AutoUpdateResource.py` 前，请在同目录下创建 `GITHUB_TOKEN.env`，在文件中输入以下字段

```env
GITHUB_TOKEN={your_github_token_here}
```

其中，{your_github_token_here} 填入你自己的 token

## Github TOKEN 获取

在 `Settings/Developer Settings/Personal access tokens/Tokens(classic)` 中选择 `Generate new token`

## 随MAA运行

在 MAA/设置/运行设置/开始前脚本中输入 `"C:/Program Files/Python313/python.exe"(替换为你的python位置) AutoUpdateResource.py` 或 `AUMR.exe`

## TODO

- [] 调用系统对话框输入 token 而非去创建文件

- [] 加入 api 调用速率限制

- [] 加入无 token 或 调用 git 方法
