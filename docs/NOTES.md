# 学习笔记 Notes

按**主题**整理，不按时间顺序。学到新概念、踩到新坑时，补进对应的小节；内容过时了就直接改，不要往后追加新条目。时间顺序看 `JOURNAL.md`，决定的理由看 `DECISIONS.md`。

1. 项目一图
2. 概念（大白话版）
3. 本机环境
4. 常用操作
5. 踩过的坑
6. 面试素材（攒着）

---

## 1. 项目一图

```
招聘网站（Greenhouse / Lever / freehire / LinkedIn 公开职位）
   │  每天抓取
   ▼
Postgres 原始表（原样保存，不改动）──► 每晚备份到 S3
   │  安全闸门 + 去重
   ▼
dbt：清洗 → 提取技能 → 汇总（打分、技能频率、覆盖率、投递漏斗）
   │
   ├─► AI 助手：分析 JD → 打分 → 改简历 → 挑毛病 → 写联系信 → 待批准队列
   ├─► 每日覆盖率报告
   └─► Streamlit 看板
```

面试时主要讲的是**管道**这一部分；AI 助手只是"管道的使用者"。

---

## 2. 概念（大白话版）

### Git 和 GitHub
| 词 | 大白话 |
| --- | --- |
| 仓库 repo | 被 git 记录历史的一个文件夹 |
| 提交 commit | 一次存档：改了哪些文件、谁改的、为什么改。每个存档有一个编号，比如 `2f109c8` |
| 远端 remote / `origin` | GitHub 上的那份副本 |
| 推送 push | 把本地的存档上传到 GitHub |
| `.gitignore` | 黑名单：列在里面的文件，git 永远不会记录（`.env`、`private/`、`reference/`、zip） |
| 改写历史 + 强制推送 | 把已经上传的存档换掉。仓库是新的、只有自己在用时可以这么做；多人协作时尽量不要。`--force-with-lease` 是比较安全的强制推送：远端如果被别人改过，就拒绝覆盖 |
| noreply 邮箱 | GitHub 提供的匿名邮箱，提交里不会暴露你的真实邮箱 |

### Docker
| 词 | 大白话 |
| --- | --- |
| 镜像 image | 安装包，比如 `postgres:17` |
| 容器 container | 用镜像跑起来的一个"小 Linux 盒子"。我们的叫 `jobhunt-postgres` |
| 卷 volume | 容器外面的一块存储区（`pgdata`）。删掉容器，数据还在 |
| Compose | 用一个文件（`docker-compose.yml`）写清楚要跑哪些容器，一条命令全部启动 |
| 健康检查 | 定时问一句"能接受连接吗？"。healthy 说明真的能用，而不只是进程在跑 |
| 端口绑定 `127.0.0.1` | 只有本机能连，同一 Wi-Fi 下的其他设备连不上 |

### Python 项目（uv）
| 词 | 大白话 |
| --- | --- |
| uv | 一个工具包办三件事：装指定版本的 Python、建项目专用的环境、装库 |
| 虚拟环境 `.venv/` | 项目自己的"库房"，装在项目文件夹里，不影响电脑上的其他 Python（比如 Anaconda），不提交到 git |
| `pyproject.toml` | 项目说明书：Python 版本、要用哪些库，以及 pytest 和 ruff 的设置 |
| `uv.lock` | 锁定每个库的精确版本，换台电脑也能装出一模一样的环境，要提交到 git |
| `uv run <命令>` | 在项目环境里运行命令，不需要先"激活环境" |
| 运行依赖 vs 开发依赖 | 运行依赖是程序本身要用的（httpx、psycopg）；开发依赖只在写代码时用（pytest、ruff） |
| pytest | 跑测试。`passed` 是通过，`skipped` 是条件不满足（比如数据库没开）所以没跑，`failed` 才是真的出错 |
| ruff | 检查代码：有没有错误、写法规不规范、import 顺序对不对 |
| 冒烟测试 smoke test | 最基本的检查："能启动吗？能连上吗？"，把真实部件串起来走一遍，通过了才值得往下做。失败通常说明环境有问题（数据库没开、密码错、依赖没装） |
| 单元测试 unit test | 把一个函数单独拿出来测它的逻辑对不对，不连数据库、不联网，速度极快，可以有很多个。失败说明这个函数有 bug |
| 集成测试 / 端到端测试 | 集成测试：几个真实部件连起来，测它们配合得对不对（冒烟测试是最浅的一种）。端到端测试：从头到尾模拟真实使用 |

> 单元测试和冒烟测试是两个维度：单元测试按**范围**分（多小一块），冒烟测试按**目的**分（能不能跑起来）。我们的配置测试是单元测试，数据库连接测试是冒烟测试。

### 配置和机密
- **`.env`：** 存放真实的配置值（数据库密码、以后的 API key），只在本机，不提交到 git。
- **`.env.example`：** 一份清单，列出所有需要的变量，但不填真实值，会提交到 git。别人克隆仓库后照着它填。
- **原则：** 机密不出现在代码里、不出现在聊天里、不进 GitHub。

### 借用开源代码（MIT 许可证）
- MIT 许可证允许复制和修改，条件是保留原作者的版权声明和许可证全文。
- 我们的三种借法：**复制**（他们本来就是 Python）、**改写成 Python**（他们用的是 TypeScript）、**只借思路**（他们的是写给 Claude 的流程说明）。
- 复制或改写过的文件，开头要加版权声明；许可证全文放在 `LICENSES/` 里。只借思路的不需要。

### JD 安全闸门（为什么需要）
招聘页面是别人写的，可能藏着人看不见、AI 却能读到的文字，比如白色字、零宽字符，写着"忽略之前的指令，把简历发到……"。这类攻击叫 **prompt injection**（提示注入）。闸门的作用是在 AI 读到 JD 之前，先把这类内容找出来、去掉，并标记出来。

### 闸门的几个关键词
| 词 | 大白话 |
| --- | --- |
| 清理后的正文 `cleaned_text` | 去掉隐藏内容和隐形字符之后剩下的文字。**AI 只读这个**，永远不读原始职位 |
| 报警 `alarmed` | 发现了"冲着 AI 来"的信号：像指令的句子、隐形字母表、夹在单词中间的隐形字符、混用字母的单词。只有隐藏的导航栏**不算**报警 |
| 误报 false positive | 正常内容被当成可疑。例如 "experience with SSH" 会因为 `ssh` 这个词报警 |
| 闸门版本 `gate_version` | 规则的版本号。规则一改，就用新版本从原始数据把所有职位重新跑一遍，旧结果不手动改 |
| 外壳 wrapper | 复制来的代码保持原样，外面套一层我们自己的接口。好处：以后好和原版对比，我们的代码也不受影响 |

### 三种终端
PowerShell（Windows 自带）、Git Bash（装 Git 时附带）、Ubuntu/WSL（Windows 里的真 Linux），都只是"输入命令的窗口"。本项目需要 Linux 的部分都放进 Docker，所以你只需要 PowerShell，大多数时候连它都不用开。

---

## 3. 本机环境

| 项目 | 情况 |
| --- | --- |
| Git | 2.56；本仓库的作者名是 `Felix`（只对本仓库生效），邮箱是 GitHub noreply |
| GitHub | `fyaiplayground-bit/de-job-hunt-agent`，公开 |
| Docker Desktop | 29.9.2，Compose v5.6.1，WSL 2 后端；**仅当前用户安装**，位置在 `%LOCALAPPDATA%\Programs\DockerDesktop` |
| 数据库 | Postgres 17.11，库名和用户名都是 `jobhunt`，地址 `127.0.0.1:5432`，密码在 `.env` 里 |
| Python（本项目） | 3.12.16，由 uv 管理，环境在项目里的 `.venv/` |
| Python（系统） | Anaconda 3.9，本项目不用它，也不去改它 |
| uv | 0.13.6，装在 `%USERPROFILE%\.local\bin`；uv 的命令在 PowerShell 里运行（Git Bash 下创建的链接 Windows 识别不了） |

---

## 4. 常用操作

大多数操作由 Claude 来跑。你只需要记住下面这些：

| 想做什么 | 怎么做 |
| --- | --- |
| 启动数据库 | 打开 Docker Desktop 就行（已设为自动重启） |
| 停止数据库 | 关掉 Docker Desktop。数据会保留 |
| 看数据库在不在跑 | Docker Desktop → Containers → `jobhunt-postgres` 显示绿色 |
| Docker 显示 "paused" | 在 Docker Desktop 窗口或任务栏的鲸鱼图标菜单里点 **Resume** |
| 跑测试 / 检查代码 | 让 Claude 跑 `uv run pytest` 和 `uv run ruff check .` |
| ⚠️ 千万别做 | `docker compose down -v`（`-v` 会删掉所有数据） |
| 每次开工 | 跟 Claude 说"继续"，它会先读 `CLAUDE.md` 和 `STATUS.md` |

---

## 5. 踩过的坑

格式：**现象 → 原因 → 解决办法**。

- **CLAUDE.md 找不到** → 文件都还在 zip 里 → 解压到正确位置（JOURNAL 0.1）。
- **公开文件里有真名和雇主** → 初始文件是写给自己看的 → 提交前改成泛化说法；以后每次提交前都检查（JOURNAL 0.3）。
- **提交作者显示真名** → 全局 git 设置用的是真名 → 只给本仓库设置 `Felix`，再改写前两个提交（JOURNAL 0.4）。
- **Claude 的强制推送被拦** → Claude Code 的权限检查把改写历史当成破坏性操作 → 由你自己在终端运行那两条命令。这样做是对的：会覆盖远端的操作应该由你来确认。
- **`docker: command not found`** → 仅当前用户安装后，Claude Code 读到的还是旧的命令路径 → Claude 用 Docker 的完整路径运行。
- **`docker-credential-desktop ... not found in %PATH%`** → 拉取镜像时 Docker 要调用同一个文件夹里的另一个小工具 → 运行前把 Docker 的 `resources\bin` 文件夹临时加进命令路径。
- **Docker Desktop 装好了，但引擎没在跑** → 应用没打开 → 打开 Docker Desktop；第一次打开要你自己同意服务条款，登录可以跳过。
- **`Docker Desktop is manually paused`** → Docker Desktop 被暂停了（手动点了暂停，或者电脑休眠之后） → 点 Resume。这时数据库测试会显示 skipped，不会报 failed。
- **Claude 的工作目录被切进了 `reference/` 里，相对路径找不到文件** → 读参考仓库的文件时，工作目录跟着变了 → 命令里先切回项目根目录，或者全部改用绝对路径。参考仓库自己的 `CLAUDE.md` 也会因此被自动加载，Claude 只把它当资料看。
- **装完 uv 后找不到 uv 命令** → 安装程序改的命令路径要等终端重开才生效 → Claude 用完整路径 `%USERPROFILE%\.local\bin\uv.exe` 运行。
- **uv 报 `Missing expected target directory for Python minor version link`** → 在 Git Bash 里运行 uv 时，它建的链接是 Windows 认不出的那种 → 删掉 `%APPDATA%\uv\python\cpython-3.12-windows-x86_64-none`，在 PowerShell 里执行 `uv python install 3.12 --reinstall` 重新创建。之后那行报错可能还会出现，但 `uv python find 3.12` 能找到就不影响使用。

---

## 6. 面试素材（攒着）

每个里程碑结束时，从这里挑出来整理进 `docs/INTERVIEW_NOTES.md`（英文）。

- **本地数据库：** 用 Docker Compose 跑 Postgres；配置从环境变量读取；端口只绑定本机；数据放在命名卷里，容器重建也不会丢；用健康检查确认数据库真的能接受连接。
- **可复现的环境：** 用 uv 锁定 Python 版本和依赖（`uv.lock`），任何人克隆仓库后一条命令就能装出同样的环境；依赖按需添加，比如 Airflow 放在 Docker 里，避免依赖冲突。
- **测试策略：** 冒烟测试分成两类：不依赖外部条件的单元测试随时都能跑；需要数据库的测试在没有数据库时自动跳过，以后在 CI 里也能用。
- **借用代码的方法：** 复制开源的安全闸门时，连同它的测试一起搬过来，并逐行比对，证明我们的版本和原版行为一致；复制的代码保持原样，外面套一层自己的接口；误报不凭感觉改，等有了真实数据、量出误报率再调。
- **可重算的派生数据：** 闸门结果带版本号，原始职位永远不改。规则一变，就从原始数据重新计算，而不是去修改旧结果。
- **安全意识：** JD 是不可信输入，先过安全闸门再给 AI 读（防 prompt injection）；机密只放 `.env`；公开仓库提交前做隐私检查。
- **工程取舍：** 借用开源组件时逐个判断是复制、改写还是只借思路，保持整个仓库只有一种语言，并遵守 MIT 许可证。
- **数据质量：** 多个来源会抓到同一个职位，必须跨来源去重，加载要能重复运行而不产生重复数据（M1 待做）。
