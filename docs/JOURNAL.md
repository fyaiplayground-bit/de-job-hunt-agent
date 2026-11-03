# 工作日志 Journal

每完成一个**步骤**写一条，和这一步的代码放在**同一个提交**里。按里程碑分组，组内按时间排序。

- 想知道"为什么这么选" → `DECISIONS.md`（这里只写编号）
- 想知道"现在在哪、下一步" → `STATUS.md`
- 想学概念、查操作、查踩过的坑 → `NOTES.md`

每条的固定格式：**做了什么 · 为什么 · 文件 · 提交 · 怎么验证的 · 怎么撤回 · 备注**。

---

## Milestone 0 · 准备

### 0.1 · 2026-10-28 · 项目文件放到正确位置
- **做了什么：** 初始文件原来都在 `de-job-hunt-agent.zip` 里，根目录只有两份放错位置的 `STATUS.md` 和 `DECISIONS.md`。解压后按 `CLAUDE.md` 的结构放好，删掉了这两份重复的文件（和 `docs/` 里的版本逐字相同）。
- **为什么：** `CLAUDE.md` 和 `docs/` 必须在固定位置，每次开工才能被读到。
- **文件：** 全部初始文件。`.gitignore` 加了 `*.zip` 和 `.claude/settings.local.json`。
- **提交：** 包含在 `554d4be` 里。
- **验证：** 解压前比对过，根目录两份和 zip 里 `docs/` 下的版本完全一致。
- **撤回：** zip 原件还在项目文件夹里（已被 git 忽略），随时可以重新解压。
- **备注：** zip 不提交，否则仓库里同样的内容会有两份。

### 0.2 · 2026-10-28 · git 初始化、首次提交、推到 GitHub
- **做了什么：** 在 `main` 分支上 `git init`，提交 14 个文件，连接 `origin` 并推送。
- **为什么：** 版本管理，同时公开展示作品集（DECISIONS #2）。
- **提交：** `554d4be`（初始文件）、`7a5a5e3`（更新 STATUS）。
- **验证：** 提交前用 `git status` 和关键词扫描确认：没有 `.env`、没有密钥、`private/` 下只有 README。推送后 `main...origin/main` 同步。
- **撤回：** 撤回已推送的提交需要强制推送，见 `NOTES.md` 第 5 节。
- **备注：** 仓库是公开的。提交前检查是真正的安全关，不是走过场。

### 0.3 · 2026-10-28 · 公开文件去掉名字和雇主
- **做了什么：** 在 `CLAUDE.md`、两个技能文件和 `DESIGN.md` 里，把名字和雇主换成了泛化说法（"a large tech company" / "FL's current employer"）。指技术的 AWS（S3、Glue）保留不动。
- **为什么：** 仓库的历史是永久公开的，不能让同事知道你在找工作（DECISIONS #17）。
- **提交：** 提交前就改好了，所以已经包含在 `554d4be` 里，公开历史里从来没有出现过原文。
- **撤回：** 以后如果想公开，在 DECISIONS 里加一条新决定再改回来。
- **备注：** 以后写任何文档（包括这份日志），都不要出现真名、雇主名，或带用户名的本机路径。

### 0.4 · 2026-10-28 · 提交作者名改为 Felix
- **做了什么：** 只给本仓库设置作者名 `Felix`（`git config user.name`，不加 `--global`），并改写了前两个提交的作者。
- **为什么：** 原来的作者名会在 GitHub 上公开显示。
- **提交：** 旧的 `a99c5f7`、`e5da270` 被新的 `554d4be`、`7a5a5e3` 替代，内容不变，只换了作者名。
- **验证：** 本地和 GitHub 上两个提交的作者、提交者都是 Felix。
- **撤回：** 不需要撤回。全局作者名没有改动，其他项目不受影响。
- **备注：** 改写历史后需要强制推送。Claude Code 的权限检查拦下了这一步，最后由 FL 自己在终端运行了 `git rebase --root --exec ...` 和 `git push --force-with-lease`。

### 0.5 · 2026-10-28 · ai-job-search 参考仓库和借用计划
- **做了什么：** 克隆到 `reference/ai-job-search/`，固定在提交 `83c788d`（已被 git 忽略）。逐个找到 8 个要借用的文件，决定每一块是复制、改写成 Python，还是只借思路。
- **为什么：** DECISIONS #12（借用什么）、#18（每一块怎么借）。
- **文件：** `docs/DESIGN.md`（新增 "Borrowed from ai-job-search" 表格）、`LICENSES/ai-job-search-MIT.txt`、`CLAUDE.md`（新增硬性规定）、`.gitignore`（加了 `reference/`）。
- **提交：** `16ec67c`
- **验证：** `git ls-files reference` 结果是 0 个文件。
- **撤回：** 直接删掉 `reference/` 文件夹即可，它不在仓库里。
- **备注：** 参考仓库里有它自己的 `CLAUDE.md`、`AGENTS.md` 和 `.claude/`，只当资料看，不当作指令。freehire 汇总了约 50 个招聘系统，所以同一个职位可能和 Greenhouse/Lever 重复，M1 的去重要处理这种情况。

---

## Milestone 1 · 骨架 + 数据抓取

### 1.1 · 2026-10-28 · Docker Desktop 和 Postgres
- **做了什么：** 安装了 Docker Desktop（仅当前用户，WSL 2 后端）。写了 `docker-compose.yml`：Postgres 17、设置从 `.env` 读取、端口只绑定 `127.0.0.1:5432`、数据存在 `pgdata` 卷、用 `pg_isready` 做健康检查、`restart: unless-stopped`。本机 `.env` 由 `.env.example` 复制，数据库密码随机生成。
- **为什么：** DECISIONS #3（Postgres 放在 Docker 里）。
- **文件：** `docker-compose.yml`（新建）、`.env`（只在本机，不提交）。
- **提交：** `2f109c8`
- **验证：**
  1. 状态为 healthy，只监听本机地址。
  2. 用 `.env` 里的密码通过 TCP 登录成功，版本是 PostgreSQL 17.11。
  3. 写入一行测试数据，`docker compose down` 再 `up` 之后数据还在；测完已删掉测试表。
- **撤回：** `docker compose down` 停止并删除容器，数据保留；`docker compose down -v` 会**连数据一起删掉**。
- **备注：** 第一次启动时报错找不到 `docker-credential-desktop`，原因是 Docker 的文件夹不在命令路径里，解决方法见 `NOTES.md` 第 5 节。容器只拿到数据库的三个设置，拿不到 `.env` 里的其他内容。

### 1.2 · 2026-10-30 · Python 项目搭建（uv、ruff、pytest）
- **做了什么：** 安装 uv 0.13.6，由它为本项目下载 Python 3.12.16（本机原有的 Anaconda 3.9 保持不动）。新建 `pyproject.toml`，只加 M1 需要的依赖：运行时用 httpx、psycopg、python-dotenv，开发时用 pytest、ruff。同时新建配置模块 `pipeline/config.py`、`ingestion/` 和 `pipeline/` 两个包，以及冒烟测试 `tests/test_smoke.py`。
- **为什么：** DECISIONS #19（选 uv，不用 Anaconda）。
- **文件：** `pyproject.toml`、`.python-version`、`uv.lock`、`pipeline/__init__.py`、`pipeline/config.py`、`ingestion/__init__.py`、`tests/test_smoke.py`
- **提交：** 见本条所在的提交（`git log -- pyproject.toml`）
- **验证：**
  1. `uv run python --version` 输出 3.12.16
  2. `uv run ruff check .` 和 `ruff format --check .` 都通过
  3. `uv run pytest`：数据库开着时 4 个测试全部通过（真正连上了数据库）；数据库停掉时 3 个通过、1 个跳过，没有报错
- **撤回：** 删除上面列出的文件和 `.venv/` 文件夹即可。如果连 uv 也不要了，执行 `uv self uninstall`。
- **备注：** dbt、FastAPI、Streamlit 等到用的时候再加；Airflow 第 4 周放在 Docker 里，不装进这个环境。这一步踩了 3 个坑：uv 不在命令路径里、Python 链接损坏、Docker Desktop 被暂停，详见 `NOTES.md` 第 5 节。

### 1.3 · 2026-10-30 · JD 安全闸门
- **做了什么：** 从 ai-job-search 复制检测逻辑到 `pipeline/posting_guard.py`，只去掉了命令行入口和读文件的部分，开头加了 MIT 版权声明；新写了我们的外壳 `pipeline/safety_gate.py`：`run_gate(text, mode)` 返回 `GateResult`，包括清理后的正文、检测明细、结论、`alarmed`、`gate_version`。他们的测试也搬了过来（`tests/test_posting_guard.py`），测试正文不改，只把辅助函数改成直接调用 `guard()`，删掉了 5 个只测命令行功能的测试。另外加了 13 个测外壳的测试。顺便把原来的 `test_smoke.py` 拆成单元测试 `test_config.py` 和冒烟测试 `test_db_smoke.py`。
- **为什么：** DECISIONS #12、#18、#20。
- **文件：** `pipeline/posting_guard.py`、`pipeline/safety_gate.py`、`tests/test_posting_guard.py`、`tests/test_safety_gate.py`、`tests/test_config.py`（由 `test_smoke.py` 改名）、`tests/test_db_smoke.py`、`pyproject.toml`（复制来的两个文件不受我们的行宽限制，ruff 也不重新排版它们）、`docs/DESIGN.md`（更新表格这一行）。
- **提交：** 见本条所在的提交（`git log -- pipeline/safety_gate.py`）
- **验证：**
  1. 复制的 389 行检测逻辑和原文逐行比对，完全一致
  2. 他们的 59 个测试（含 54 个子测试）全部通过，说明我们的版本行为和原版一样
  3. 我们的 13 个外壳测试通过：干净的 DE 职位不报警；隐藏的注入句子被删掉并报警；只有隐藏导航栏不报警；`alarmed` 和结论里的 ⚠ 始终一致；版本号正确；不认识的 mode 会报错
  4. 一共 76 个测试全部通过（数据库开着），`ruff check` 和 `ruff format --check` 都通过
- **撤回：** 删除上面新增的文件，把 `test_config.py` 改回 `test_smoke.py`（`git revert` 这个提交即可）。
- **备注：** 已知误报：`ssh`、`curl`、`.env` 出现在正常的技能描述里也会报警，专门写了一个测试把这个行为记录下来。规则先不改，等有了真实数据再调（#20）。生成复制文件和改写测试用的是一次性脚本，没有放进仓库。

### 1.4 · 2026-10-30 · Greenhouse + Lever 抓取进原始层
- **做了什么：** 抓取 19 家公司的公开招聘页（14 家 Greenhouse、5 家 Lever），原样存进 Postgres，再全部过一遍安全闸门。共建了 4 张表：`raw.ingest_runs`（每次运行一行）、`raw.job_postings`（每个职位的每个内容版本一行，原始 JSON 不改）、`raw.job_sightings`（每个职位每天被看到一次就记一行）、`gate.results`（闸门结果，带版本号）。建表用编了号的 SQL 文件，只会执行一次。手动运行命令：`uv run python -m pipeline.ingest`。
- **为什么：** DECISIONS #21。
- **文件：** `config/companies.toml`、`db/migrations/001_raw.sql`、`db/migrations/002_gate.sql`、`pipeline/db.py`、`pipeline/load.py`、`pipeline/gate_step.py`、`pipeline/ingest.py`、`ingestion/http.py`、`ingestion/greenhouse.py`、`ingestion/lever.py`、`ingestion/sources.py`、`pipeline/config.py`（新增 `is_source_enabled`，默认地址改为 127.0.0.1）、`.env.example`；测试：`tests/conftest.py`、`tests/fixtures/*.json`、`tests/test_sources.py`、`tests/test_http.py`、`tests/test_ingest_db.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/ingest.py`）
- **验证：**
  1. 97 个测试全部通过，用时 2 秒，ruff 也通过。新增 21 个测试：8 个测解析和内容指纹（`updated_at` 变化不算改版；内容改了才算；部门顺序不影响），5 个测网络请求（遵守 `Retry-After`；遇到 5xx 按 1/2/4 秒退避，3 次后放弃；404 不重试；连接错误会重试），8 个数据库测试，在单独的 `jobhunt_test` 库里跑（重复加载新增为 0；内容改一处只多 1 个版本；隔一天只多看到记录；一家公司失败不影响其他公司；闸门每个版本只检查一次）
  2. 真实运行第 1 次：19 家全部成功，共 2300 个职位、2300 个版本，闸门检查 2300 个、报警 14 个，用时 62 秒
  3. 马上运行第 2 次：新增版本 0，闸门检查 0。**幂等得到证明**
- **真实数据观察：** 2300 个职位里，标题像 DE 的有 58 个。14 个报警**全部是误报**：10 个是同一句 "You are an AI pragmatist"（Samsara 销售岗），3 个是 SSH 出现在 JumpCloud 的技能描述里，1 个是 "as an AI/Tech evangelist"（JumpCloud；原规则只放过 "As an AI Engineer" 这类职位名称，豁免名单里没有 evangelist）。58 个 DE 类职位都没有报警。没有发现真正的攻击。这组数据就是以后调规则的依据（#20）。
- **怎么判断是误报的（每一条都核对过）：** ① 读完整的触发句：是在描述候选人或技能，还是在命令 AI 做事；② 检查其他信号：隐藏内容、隐形字符、隐形文字、隐藏网址、混用字母，14 条全部为 0，句子都是明面上所有人可见的，而攻击通常要藏起来；③ 合不合常理：都在公司官方招聘页上，10 条是同一个招聘模板。这是有依据的人工判断，不是证明。（更正：第一次汇总时只看了每句前 110 个字符，误把 "as an AI" 那条归进了 SSH，已改正。）
- **撤回：** `git revert` 这个提交；要清空数据库里的数据，执行 `drop schema raw cascade; drop schema gate cascade; drop table public.schema_migrations;`（会删掉所有已抓到的职位）。
- **备注：** 这一步的坑：默认地址 `localhost` 每次连接要慢好几秒（Windows 先尝试 IPv6），已改为 `127.0.0.1`，见 `NOTES.md` 第 5 节。起步清单里大多是中大型公司，只用来跑通管道；小公司为主的目标清单在 M5。跨来源去重和每日运行脚本还没做。

### 1.5 · 2026-10-30 · 报警分档：把人工判断写成确定的规则（规则循环第 A 步）
- **做了什么：** 把 1.4 里判断误报的标准写成了代码。每个闸门结果自动分到四档之一：clean（干净）/ benign（放行）/ review（人工看）/ block（拦截），并附上原因。规则放在数据文件 `config/triage_rules.toml` 里，包括哪些是"弱规则"、哪些是"指挥 AI 的信号词"，以及版本号。上游的每条指令规则都起了一个固定的名字（`RULE_SIGNATURES`），规则文件按名字引用。闸门版本改成"检测版本 + 规则版本"，也就是 `d1-t1`。新增报告命令 `pipeline.alarm_report`，以及只重算、不抓取的 `pipeline.ingest --gate-only`。"代码在运行时判断、AI 只提建议、规则只能通过循环修改"这条原则写进了 `CLAUDE.md` 的硬性规定。
- **为什么：** DECISIONS #22。
- **文件：** `config/triage_rules.toml`、`pipeline/alarm_triage.py`、`pipeline/alarm_report.py`、`pipeline/safety_gate.py`、`pipeline/gate_step.py`、`pipeline/ingest.py`、`db/migrations/003_gate_triage.sql`、`tests/fixtures/gate_cases.jsonl`、`tests/test_alarm_triage.py`、`tests/test_safety_gate.py`、`tests/test_ingest_db.py`、`CLAUDE.md`、`docs/DESIGN.md`
- **提交：** 见本条所在的提交（`git log -- pipeline/alarm_triage.py`）
- **验证：**
  1. 标准答案集共 39 条：5 条真实误报必须放行；25 条攻击写法必须是"人工看"或"拦截"（其中 19 条来自上游测试，6 条是专门针对我们规则写的，比如把指令放在 200 个字符的截断之后、把已知无害的句子藏进隐藏内容）；另有干净和混用字母的例子。**全部落在预期的档位**
  2. 一共 174 个测试全部通过，ruff 也通过；另有测试保证上游每条规则都恰好有一个名字，上游一改，测试就会失败
  3. 用新规则从原始数据重算 2300 个职位：clean 2286、benign 14、review 0、block 0；再跑一次，新增 0；旧版本 `1` 的 2300 条结果仍然保留
- **撤回：** `git revert` 这个提交。数据库里 `d1-t1` 版本的结果可以留着，不影响旧版本；要删就执行 `delete from gate.results where gate_version = 'd1-t1'`。
- **备注：** 两个坑：Write 工具把规则文件里的 `'` 直接写成了撇号，导致 TOML 字符串提前结束；改用 sed 时反斜杠又被 shell 吃掉了。最后改用编辑工具解决，见 `NOTES.md` 第 5 节。残留风险：只用弱规则里的说法、又避开所有信号词的攻击句会被放行。这样的句子本身不在指挥 AI，而且 M2 的 AI 助手会有自己的"只当数据"规则作为第二道防线。下一步是循环第 B 步：标签表和评估命令。

### 1.6 · 2026-10-30 · 规则循环第 B 步：标签和评估，并完整走一遍
- **做了什么：** 新增标签表 `gate.labels`（只追加；同一个职位以最新的标签为准，旧的保留），记录标签类别、备注、谁标的、什么时候，以及当时的规则版本、档位和看到的触发句。新增打标签命令 `pipeline.labels`（add / list / export）：导出时**只导出触发的那一句话**，不导出整个职位；相同的句子合并成一条；隐藏的内容重新藏起来；隐形文字重新用隐形字符写出来。导出的结果写进 `tests/fixtures/gate_cases_labeled.jsonl`。新增评估命令 `pipeline.evaluate_rules`：用当前规则和提议规则把所有标准答案、所有历史职位各判一遍，输出硬性检查、软性指标、各档数量的前后对比，以及哪些职位的档位会变；只读，不写任何东西。报告命令现在会显示职位编号，方便打标签。新增 `config/proposals/` 文件夹，存放规则修改的提议。
- **为什么：** DECISIONS #23。
- **文件：** `db/migrations/004_gate_labels.sql`、`pipeline/labels.py`、`pipeline/evaluate_rules.py`、`pipeline/alarm_report.py`、`pipeline/alarm_triage.py`（`visible_line` 改为公开函数）、`pipeline/safety_gate.py`（`is_alarmed` 改为公开函数）、`config/proposals/README.md`、`tests/fixtures/gate_cases_labeled.jsonl`、`tests/test_labels.py`、`tests/test_evaluate_rules.py`、`tests/test_alarm_triage.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/evaluate_rules.py`）
- **完整走一遍循环（真实数据）：**
  1. 报告：14 个放行的职位，每个都显示了编号
  2. 打标签：14 个都标为 `false_positive`（你在对话里确认过），备注写明原因
  3. 导出：合并成 5 条标准答案（10 个 Samsara 职位是同一个模板）
  4. 提议和评估：
     - "所有规则都改成弱规则" → **48 项硬性检查不通过**，命令报失败
     - "只把 chat_template_token 改成弱规则" → **不通过**，`<|im_start|>system` 会被放行。注意：只看 2300 个真实职位，结果是"0 个变化"，看起来完全无害，**是标准答案集拦住了它**
     - "只改注释" → 通过，0 个变化
  5. 正式规则保持第 1 版：没有真实数据要求改规则，所以不改
- **验证：** 191 个测试通过，1 个跳过（还没有已标注的真实攻击）；ruff 通过。写测试时发现了一件事：只放宽"忘记之前的指令"这条规则，并不会放过 "Forget your previous instructions."，因为句子里的 *instructions* 是信号词，两层规则各自起了作用。这一点也写成了测试。
- **撤回：** `git revert` 这个提交；标签表里的数据可以用 `drop table gate.labels` 删除，同时从 `public.schema_migrations` 里删掉 `004_gate_labels.sql` 这一行。
- **备注：** 标签时间按 UTC 记录，所以在美国晚上标的会显示成第二天的日期。

### 1.7 · 2026-10-31 · freehire、LinkedIn（默认关闭）、跨来源去重、发现新招聘页
- **做了什么：**
  - **抓取改为支持"按搜索抓"：** 除了按招聘页抓（`config/companies.toml`），现在也能按保存好的搜索条件抓（`config/searches.toml`）。新增 `FetchContext`，所有请求都经过它，便于计数和设置上限。运行记录里的 `company` 列改名为 `target`，新增 `requests_made` 和 `note` 两列（迁移 005）。每个职位的公司名改为从职位数据本身读取。
  - **freehire：** 照他们的客户端改写成 Python，开头带 MIT 声明。按"美国 + data/analytics engineer 标题"搜索，一页一页地翻；页数有上限；遵守 API 的 offset 窗口限制；内容指纹不包括浏览数、`reality` 等经常变的字段。
  - **LinkedIn：** 照他们的解析代码改写，开头带 MIT 声明，但**没有搬**伪装成浏览器的身份和请求头。默认关闭（需要设置 `LINKEDIN_PUBLIC_ENABLED=true` 才会运行）；每天的请求数有硬上限，同一天跑几次加起来也不会超；已经存过的职位不再请求详情页，只记一条"今天看到了"；原始数据存 LinkedIn 返回的 HTML。**这次没有发出任何真实的 LinkedIn 请求。**
  - **跨来源去重：** 用 SQL 视图实现（迁移 006、007），按"招聘系统/招聘页/职位 id"确定身份，优先采用直接从招聘系统抓到的那一份。
  - **发现新招聘页：** 新增 `pipeline.discover_boards`，只读，列出 freehire 里出现过、但我们还没有的 Greenhouse/Lever 招聘页。
- **为什么：** DECISIONS #24。
- **文件：** `ingestion/context.py`、`ingestion/freehire.py`、`ingestion/linkedin.py`、`ingestion/http.py`（新增 `get_text`）、`ingestion/greenhouse.py`、`ingestion/lever.py`、`ingestion/sources.py`、`config/searches.toml`、`pipeline/ingest.py`、`pipeline/load.py`、`pipeline/config.py`、`pipeline/discover_boards.py`、`db/migrations/005_search_sources.sql`、`006_dedupe_views.sql`、`007_dedupe_jobs_group_once.sql`；测试 `tests/test_freehire.py`、`tests/test_linkedin.py`、`tests/test_search_sources_db.py`，以及 `tests/fixtures/` 里的 3 个样例文件（都是我手写的，不含真实职位文字）
- **提交：** 见本条所在的提交（`git log -- ingestion/freehire.py`）
- **验证：**
  1. 211 个测试通过，ruff 通过。新增的测试覆盖：freehire 翻页、参数、页数上限、API 窗口；LinkedIn 解析、隐藏内容会被闸门拦下、关闭横幅、请求预算是硬上限、已存过的职位不重复请求、**默认关闭**；数据库测试覆盖每日上限跨运行生效，以及同一个职位从 Greenhouse 和 freehire 进来只算一个
  2. 真实运行：freehire 回填 7 天，抓到 5000 个职位（达到页数上限，**回填不完整**），其中 4592 个是不重复的，用时 256 秒；再跑一遍全部来源，freehire 新增 224 个，**全是第一次被漏掉的新职位**，没有一个是旧职位改版
  3. 去重：7118 条原始记录 → 7073 个职位，有 45 个同时来自 Greenhouse 和 freehire
- **真实数据观察：**
  - freehire 按相关度排序，翻页的几分钟里排序一直在变，所以同一个职位可能出现在两页上（408 个重复，已被幂等加载吸收），也可能被漏掉。每天只抓 2 天（约 1300 个、14 页）不会碰到上限
  - freehire 自己判定 **22% 的职位是陈旧职位**（1065 个）；职位来源主要是 Greenhouse 1117、Manatal 874、Workday 755、Oracle 339
  - 闸门：review 4、block 5，**全部像是误报**。4 个 review 中，3 个是 Axon 的防诈骗提示（"please ignore the message"），1 个是没有换行的长段落里提到 SSH；5 个 block 都是复制粘贴留下的零宽空格，比如 `stor|y`、`|h|eadquarters`。这些标签和可能的规则调整，要先等你确认（规则循环）
- **一个性能问题（已修复）：** 去重视图第一版用了"每行一次子查询"，到 7000 行时 20 秒都跑不完。改成先分组、再连接（迁移 007），同样的数据只用 0.59 秒。没有修改已经执行过的迁移 006，而是新加一个迁移，保证改动有记录。
- **撤回：** `git revert` 这个提交；数据库里的视图用 `drop schema dedupe cascade` 删除；freehire 的数据可以用 `delete from gate.results where posting_version_id in (select posting_version_id from raw.job_postings where source='freehire')`，再加上对 `raw.job_sightings`、`raw.job_postings` 做同样条件的删除。
- **备注：** 运行慢查询之前应该先设 `statement_timeout`，这次是靠后台任务超时才发现的。

### 1.8 · 2026-10-31 · 规则循环第一次真正跑一圈（规则 v2），以及 HTTP 身份调整
- **做了什么：**
  - **打标签：** 你确认 freehire 带来的 9 个报警都是误报（3 个 Axon 防诈骗提示、1 个 Schneider 的 SSH、5 个零宽空格残留），全部标成 `false_positive`。导出后共有 13 条标准答案。
  - **导出改进：** 超过 300 字符的行（比如整篇描述都没有换行的 Schneider）只导出触发词附近的片段，整篇描述不会进入公开仓库；含零宽字符的单词从职位原文里复现，先去掉 HTML 标签，这样 BOM 那条也能找到。
  - **规则 v2：** 新增一个开关：单词里只有零宽字符、没有任何其他可疑信号时，按"编辑残留"放行，不再拦截。先写成 `config/proposals/triage_rules.v2.toml` 提议，评估通过后你批准，才复制成正式规则。新增手写标准答案：零宽残留 → 放行；双向控制符 → 拦截。
  - **HTTP 身份（#25）：** User-Agent 改用爬虫标准格式（和 Googlebot 一样），加上 Accept 和 Accept-Language、退避时的随机抖动，LinkedIn 详情页 404 时只跳过该职位。**没有采用** `X-Requested-With`，因为它会让请求冒充成 LinkedIn 自己的网页。
- **为什么：** DECISIONS #25、#26。
- **文件：** `config/triage_rules.toml`（v2）、`config/proposals/triage_rules.v2.toml`、`pipeline/alarm_triage.py`（开关和 `is_editing_artifact`）、`pipeline/labels.py`、`ingestion/http.py`、`ingestion/linkedin.py`、`tests/fixtures/gate_cases.jsonl`、`tests/fixtures/gate_cases_labeled.jsonl`、`tests/test_alarm_triage.py`、`tests/test_labels.py`、`tests/test_evaluate_rules.py`、`tests/test_http.py`、`tests/test_linkedin.py`、`tests/test_safety_gate.py`
- **提交：** 见本条所在的提交（`git log -- config/proposals/triage_rules.v2.toml`）
- **验证：**
  1. 打完标签后，v1 下有 6 条标准答案测试失败（v1 拦截了你确认过的误报）。这是**有意为之的信号**：现行规则和已确认的事实矛盾了
  2. 评估 v2：硬性检查全部通过；被放行的误报从 6/13 升到 12/13；只有那 5 个被标注的职位从拦截变为放行，其他不变
  3. 采用 v2 后，233 个测试全部通过；从原始数据重算 7118 个职位（`d1-t2`）：clean 7089、benign 25、review 4、block 0；再跑一次新增 0；v1 的结果仍然保留
- **撤回：** 把 `config/triage_rules.toml` 改回 version 1、去掉那个开关，然后运行 `ingest --gate-only`。v1 的结果还在数据库里，所以不会丢任何历史。
- **备注：** 找到了"转义序列变成真字符"的真正原因：我传给工具的 `​` 这类文字会在写入前被解码，用 sed 写时反斜杠又会被 shell 吃掉。现在含不可见字符的地方，一律用脚本以 `chr()` 生成，写完再扫描一遍确认没有残留的不可见字符。

### 1.9 · 2026-10-31 · 每日运行脚本
- **做了什么：** 新增 `pipeline/daily.py`，一条命令 `uv run python -m pipeline.daily` 完成每天的全部工作：
  1. 连数据库；连不上就启动一次 Docker Desktop，最多等 3 分钟
  2. 加锁（Postgres advisory lock），同一时间只允许一个 daily 在跑
  3. 抓取所有已开启的来源
  4. 过安全闸门
  5. 写报告 `output/daily/<日期>.md` 和 `latest.md`，并在 `ops.daily_runs` 记一行（迁移 008）

  搜索窗口按上次成功运行的时间自动计算（2–7 天）；"今天新增"按本次运行的 run id 判断，不看时钟。`scripts/daily.cmd` 给 Windows 任务计划程序调用。CLAUDE.md 新增一条：每次开工先汇报最近一次 daily 的结果。`.env.example` 新增 `REPORT_TIMEZONE`。`tzdata` 改为显式依赖。
- **为什么：** DECISIONS #27。
- **文件：** `pipeline/daily.py`、`db/migrations/008_daily_runs.sql`、`scripts/daily.cmd`、`tests/test_daily.py`、`tests/conftest.py`（测试库也清理 `ops` 和 `dedupe`）、`CLAUDE.md`、`.env.example`、`pyproject.toml`、`uv.lock`
- **提交：** 见本条所在的提交（`git log -- pipeline/daily.py`）
- **验证：**
  1. 244 个测试通过，覆盖：窗口计算（第一次 2 天、隔天 2 天、隔 4 天 5 天、最多 7 天、失败的运行不算）、跨来源去重后的"新增"、同一天第二次运行新增为 0、锁、报告内容确定、数据库连不上时只启动一次 Docker 然后放弃并给出提示
  2. 真实运行两次都 ok，用时约 80 秒；第二次运行进行中时启动的第三次，被锁挡住并直接退出
  3. 排查了一个疑点：Coinbase 每次运行都"新增 1 个"，查证后发现是 3 个**不同**的新职位（Coinbase 正在发布新岗位），没有任何职位出现重复版本，幂等没有问题
- **撤回：** `git revert` 这个提交；`drop schema ops cascade`；删掉 `output/daily/`。
- **备注：** 第一版用时间戳判断"今天新增"，在测试里因为模拟时间和真实时间不一致而失败，改用 run id 之后就不依赖时钟了。

### 1.10 · 2026-10-31 · 创建定时任务和桌面快捷方式（你同意后）
- **做了什么：**
  - Windows 计划任务 "de-job-hunt-agent daily"：每天本地时间 8:30（电脑本身就是太平洋时区），通过 `conhost --headless` 运行 `scripts\daily.cmd`，不会弹出窗口
  - 设置：错过后补跑、用电池也运行、不唤醒电脑、只在你登录时运行、普通权限、最长 1 小时、不同时运行两个
  - 桌面快捷方式"每日职位报告"：用记事本打开 `output\daily\latest.md`
- **验证：** 手动触发一次，结果代码 0（成功），日志里有当天的报告；下次自动运行时间显示为 11/01 08:30。
- **撤回：** 让 Claude 运行 `Unregister-ScheduledTask -TaskName "de-job-hunt-agent daily" -Confirm:$false`，然后删掉桌面上的快捷方式。
- **两个坑（已记入 NOTES）：**
  1. 创建时触发时间被存成了 `08:30-07:00`（固定的夏令时偏移），而 11/01 夏令时结束，下次运行就变成了 7:30。改成不带偏移的本地时间 `08:30` 后，全年都是 8:30。
  2. 快捷方式名和桌面路径里有中文，在 PowerShell 命令里变成了 `??`；Windows 创建快捷方式用的老组件也存不了这种路径。解决办法是先存到英文路径，再用 PowerShell 移到桌面。

### 1.11 · 2026-10-31 · 假样本档案和档案检查（M1 最后一项）
- **做了什么：**
  - `data/sample/` 放了一个虚构的候选人 Alex Sample（BI 工程师转 DE），三个文件就是以后你真文件的格式：`evidence_bank.toml`（事实库：工作经历、项目、学历、13 条经历、19 个技能及别名）、`applicant_profile.toml`（申请表资料和硬性条件）、`resume.md`（未定制的主简历）。另有 `README.md`，声明全部虚构，并列出给 M2 准备的测试场景（换个说法、只碰过一点、在学、从没碰过、模糊处理的数字、硬性条件）
  - `agents/profile.py`：读取并检查三个文件，命令是 `uv run python -m agents.profile check [文件夹]`。检查内容：字段齐全、类型正确；id 不重复；每条经历指向存在的工作或项目；技能用标准名；每个技能至少有一条证据；别名不撞车；简历的标题、日期、技能、数字都能在事实库里找到
  - `pipeline/config.py` 新增 `profile_dir()`，`.env.example` 新增 `PROFILE_DIR=data/sample`。M5 时把它改成 `private` 就切换到真档案
  - `private/README.md` 和四个 skill 文件改为指向 `<profile>/evidence_bank.toml` 这类路径；`DESIGN.md` 同步
  - 新建 `docs/INTERVIEW_NOTES.md`，写好 M1 的面试笔记（英文）
  - 顺手修了本文件 1.4 条的"撤回 / 备注"两行，它们之前跑到了文件末尾
- **为什么：** DECISIONS #16、#28。
- **文件：** `data/sample/README.md`、`data/sample/evidence_bank.toml`、`data/sample/applicant_profile.toml`、`data/sample/resume.md`、`agents/__init__.py`、`agents/profile.py`、`pipeline/config.py`、`.env.example`、`tests/test_profile.py`、`private/README.md`、`.claude/skills/{coverage-report,fit-scoring,resume-tailoring}/SKILL.md`、`docs/DESIGN.md`、`docs/INTERVIEW_NOTES.md`
- **提交：** 见本条所在的提交（`git log -- data/sample/evidence_bank.toml`）
- **验证：**
  1. `agents.profile check` 对样本输出 OK（2 份工作、2 个项目、13 条经历、19 个技能，其中 1 个在学）
  2. 新增 25 个测试：样本通过全部检查；**隐私护栏**（邮箱只能是 example.com，网址只能是 example.com，电话只能是 555-01xx，公司和学校只能是那三个虚构名字）；README 承诺的测试场景都在；每条检查都能抓到它要抓的错误（简历写了没证据的 Kafka、简历出现事实库里没有的数字、日期和工作经历对不上、标题不标准、经历指向不存在的工作、技能没用标准名、技能没有证据、别名撞车、级别或日期写错、缺字段、薪资下限高于目标）；命令行在样本上返回 0，在改坏的副本和空文件夹上返回 1
  3. 全部 269 个测试通过（1 个跳过），ruff 通过
- **撤回：** `git revert` 这个提交。不涉及数据库。
- **备注：** 简历上的数字检查会跳过粘在字母上的数字（S3、EC2 不算声称"3""2"）。日期只看格式为 "Mar 2021 – Present" 的那一种。

### 1.12 · 2026-11-01 · 第一次定时运行被错过；改到 9:30
- **做了什么：** 第一次定时运行（11/01 8:30）没有发生。查了任务设置和系统日志：电脑从 10/31 晚上 9:21 一直睡到 11/01 早上 9:03，任务设置的是"不唤醒电脑"，所以 8:30 没跑。Windows 记下了这次错过（`NumberOfMissedRuns = 1`）。9:04 手动跑了一次（run 4：ok，用时 61 秒，新增 163 个职位，其中 DE 类 30 个，没有报警）。然后按你的要求，把触发时间改成每天 9:30，存的是不带偏移的本地时间，其他设置不变。
- **为什么：** DECISIONS #29。
- **文件：** 只改了 Windows 计划任务（不在仓库里）；文档：`docs/DECISIONS.md`、`docs/STATUS.md`、`docs/NOTES.md`
- **提交：** 见本条所在的提交（`git log -- docs/JOURNAL.md`）
- **验证：** `StartBoundary` 是 `2026-11-02T09:30:00`（没有偏移），下次运行显示 11/02 9:30，补跑、用电池也运行、不唤醒电脑、限时 1 小时这些设置都还在。
- **没能验证：** "错过后补跑"到底会不会自己触发。电脑 9:03 醒来，Windows 要先等大约 10 分钟才补跑；9:10 改触发时间时还没到这 10 分钟，而改触发时间又把错过次数清零了（`NumberOfMissedRuns` 变回 0），所以这次看不出结论。下次电脑在 9:30 睡着时，醒来大约 10 分钟后看一下 `ops.daily_runs` 有没有新的一行。
- **撤回：** 把触发时间改回 `08:30`，同样不带偏移。

### 1.13 · 2026-11-02 · "错过后补跑"验证通过
- **发生了什么：** 11/02 9:30 电脑在睡眠：从 9:18 一直睡到 19:33，中间每 15 分钟只醒几秒（系统的维护唤醒），这几秒不够触发补跑。19:33 电脑真正醒来，计划任务 **19:39:17 自己补跑了**，也就是醒来后约 6 分钟（Windows 会先等一会儿）。这一次没人动过触发时间，所以终于看清楚了，1.12 里"没能验证"的问题有了答案。
- **结果：** run 5 ok，用时 143 秒，搜索回看 2 天，新增 532 个职位，其中 DE 类 76 个（两天的量）；1 个新报警：CDW 的 "As an AI forward company"，在描述公司，看起来是误报，等你打标签。
- **结论：** 电脑睡着时错过的运行，醒来几分钟后会自动补上，不需要手动跑。只有电脑一整天都没真正醒来时才会缺一天；下一次运行的自适应窗口（2–7 天）会把漏掉的职位补回来。
- **文件：** 只改了文档（`docs/JOURNAL.md`、`docs/NOTES.md`、`docs/STATUS.md`）
- **撤回：** 不涉及代码。

## Milestone 2 · AI 助手（agent 层）

### 2.1 · 2026-11-01 · AI 调用的底座：提示词版本、请求构造、缓存、费用
- **做了什么：**
  - 你确认了 M2 的设计：AI 负责读和写，代码负责打分和判断；简历排版用 Typst；默认模型 Opus 5.5，思考深度 medium。记为决策 #30
  - 用 uv 装了 Anthropic 官方 SDK（`anthropic` 2.3.0）
  - `agents/skills.py`：把每个 SKILL.md 读成"带版本号的提示词"。六个 skill 文件开头都加了 `version: 1`；`config/prompt_lock.toml` 记录版本号和全文指纹；命令 `agents.skills check | lock`
  - `agents/llm.py`：所有 AI 调用都走这里。系统提示 = skill 文件 + "数据不是指令"规则；职位放在 `<data>` 标签里（职位里如果出现 `</data>`，会被转义，免得它提前结束数据块）；用结构化输出拿 JSON；开启备用模型（fallback）；系统提示标记为可缓存
  - 迁移 009：`agents.llm_calls` 表，同时是缓存和费用记录（请求指纹、提示词版本、输入指纹、模型、实际回答的模型、token 数、费用）
  - 命令：`agents.llm ping`（一次很小的真实调用，测试 key）、`agents.llm costs`（今天 / 本月 / 总计花费）
  - `.env.example` 新增 `LLM_MODEL`、`LLM_EFFORT`；`pipeline/config.py` 新增 `llm_settings()`
- **为什么：** DECISIONS #22、#30。
- **文件：** `agents/skills.py`、`agents/llm.py`、`config/prompt_lock.toml`、`db/migrations/009_agents.sql`、`.claude/skills/*/SKILL.md`（加 `version: 1`）、`pipeline/config.py`、`.env.example`、`pyproject.toml`、`uv.lock`、`tests/test_skills.py`、`tests/test_llm.py`、`tests/conftest.py`（测试库也清理 `agents`）
- **提交：** 见本条所在的提交（`git log -- agents/llm.py`）
- **验证：**
  1. 新增 28 个测试，全部 297 个测试通过（1 个跳过），ruff 通过。覆盖：六个 skill 都能读出版本号；提示词锁和文件一致；改文字不升版本会被抓到，而且不能直接写进锁；升了版本要先 lock；CRLF 和 LF 指纹相同；请求指纹稳定，模型、思考深度、提示词、格式、内容任何一个变了指纹都会变；职位关不掉 `<data>` 块；发给 SDK 的参数正确（fallback、结构化输出、提示缓存）；第二次同样的请求从缓存取、不再调用；回答被拒、被截断、缺字段时报错且不存；备用模型回答时按它的价格记账；按今天 / 本月 / 总计统计花费
  2. 真实命令：`agents.skills check` 输出 OK；`agents.llm costs` 显示 0 次、$0.00；没有 key 时，`agents.llm ping` 会给出一句清楚的提示，而不是一大段报错
  3. **还没做真实的 AI 调用**：`.env` 里还没有 API key
- **撤回：** `git revert` 这个提交；数据库执行 `drop schema agents cascade`，再从 `public.schema_migrations` 删掉 `009_agents.sql` 这一行。
- **备注：** 一个坑：`ping` 第一版先创建 SDK 客户端，后读 `.env`，这样就算 `.env` 里有 key，SDK 也看不到。已改成先读 `.env`。另外，没有 key 时 SDK 抛的是 `TypeError`，不是它自己的错误类型，所以要单独处理。

### 2.2a · 2026-11-01 · 拆解 JD：范围规则、简报格式、试点 20 个
- **做了什么：**
  - `config/analysis_scope.toml`（版本 1）：代码先筛。标题像 DE（和每日报告是同一条规则，有测试保证两者一致）；排除 Staff/Principal/Lead/Manager/Director/Head/VP/Intern；最近 3 天还在招；闸门档位 clean 或 benign；跳过 freehire 标为 stale 的职位
  - `agents/jd_analysis.py`：简报格式 `BRIEF_SCHEMA`（每个字段必填、不许多字段）；选职位的 SQL；给 AI 的数据是"公司、职位、招聘页上的地点 + 闸门清理后的正文"；公司名、职位名、链接由代码从原始数据填进简报；命令 `run [--limit N] [--dry-run]` 和 `show <编号>`；某个职位失败（被拒、被截断）就记下来，继续跑其他的
  - `jd-analysis/SKILL.md` 升到 **版本 2**：输出格式和 schema 一致，加了技能命名、原文照抄、工作方式、薪资、签证担保的规则，删掉"公司分段"（交给代码）。提示词锁已更新
  - 迁移 010：`agents.jd_briefs`（职位版本 × 提示词版本 × 模型，一行一份简报，记录范围规则版本和对应的 AI 调用）
- **为什么：** DECISIONS #31。
- **文件：** `agents/jd_analysis.py`、`config/analysis_scope.toml`、`.claude/skills/jd-analysis/SKILL.md`、`config/prompt_lock.toml`、`db/migrations/010_jd_briefs.sql`、`tests/test_jd_analysis.py`、`tests/test_skills.py`（改成读取当前版本号，以后升版本不会误报）
- **提交：** 见本条所在的提交（`git log -- agents/jd_analysis.py`）
- **验证：**
  1. 新增 11 个测试，全部 308 个通过，ruff 通过。覆盖：范围规则和每日报告一致；schema 处处严格；三个来源的公司、地点、链接取法；只选还在招、通过闸门的 DE 职位；**测试数据里那个藏了"忽略之前的指令"的攻击职位被闸门拦下，永远到不了 AI**；陈旧职位被跳过；拆过的不再拆；dry-run 不调用 AI；`--limit` 生效；被拒的职位记为失败、不存
  2. dry-run：879 个 DE 标题 → 442 个在范围内，预估全部 $26
  3. **真实试点 20 个：** 20 个全部成功，没有被拒，共 **$0.76**（每篇约 $0.038，比预估便宜：平均输入 1,225、输出 1,589 个 token，提示缓存命中了 51,889 个输入 token），约 4 分钟。岗位类型：pipeline_de 11、analytics_engineer 6、infra_de 3；级别：senior 17；工作方式：hybrid 9、unclear 5、onsite 4、remote 2；写了薪资的 5 个；平均必备技能 11 个
- **试点中发现的问题（留给 2.2b、2.3）：**
  1. 经验年限规则写的是"取最小的数字"，结果一个标题写着 "Minimum 07+ Yrs" 的职位被记成 3 年。应该改成"整体经验要求"，走规则循环升到 v3
  2. AI 给的技能名有 "ETL pipelines"、"Data pipelines" 这类写法，2.3 对接事实库时要做名称映射
  3. 20 个里 17 个是 senior。要不要把级别也作为硬性条件，到 2.3 时由你决定
  4. 一个 Java 后端岗位因为标题里有 "Data Platforms" 混了进来，打分时会被筛掉
  5. 有一个职位末尾多了一串奇怪的字符 `xhmxlyz`，AI 把它记进了 `safety_flags` 并忽略了，这正是我们希望的处理方式
- **撤回：** `git revert` 这个提交；数据库执行 `drop table agents.jd_briefs`，再从 `public.schema_migrations` 删掉 `010_jd_briefs.sql`。AI 的回答留在 `agents.llm_calls` 里也没关系。

### 2.2b · 2026-11-01 · 标准答案集和评估命令（提议待你批准）
- **做了什么：**
  - `tests/fixtures/jd_golden.toml`：10 个真实职位的标准答案（我起草，等你核对）。挑选时覆盖了各种情况：Anthropic（年限只出现在"加分项"里）、Bold Penguin（典型 analytics engineer）、ASSYST（每条要求都写 8+ 年）、Voto（年限自相矛盾的假 DE 岗）、SMBC（freehire 只给了一段被截断的公司简介）、Rosen's（Azure Databricks，正文没写工作方式）、Metabase（必备很少，"加分"工具很多）、Samsara（10+ 年、偏软件工程）、Reddit（标题是 AE，要求像 pipeline DE）、Sigma（必备很少，坐班）。**文件里只有职位编号和期望结果，没有职位原文**；评估时从本地数据库按（来源、职位 id、内容指纹）读原文
  - `agents/evaluate_prompt.py`：用现行提示词和提议的提示词分别拆解这 10 个职位，比较必备技能找到了几个、岗位类型、工作方式、经验年限；新版本找到的必备技能最多只能少 1 个（模型的随机误差），其他几项都不能变差。结果有缓存，重跑免费；不写入 `agents.jd_briefs`
  - 两份提议：`config/proposals/jd-analysis.v3.md`（只改经验年限规则：取"整体经验要求"，不取某个工具的年限；范围取下限；只写在加分项里也算；标题和正文矛盾时取较大的整体数字）；`config/proposals/analysis_scope.v2.toml`（新增 `min_text_chars = 1000`，跳过被截断的片段：442 个里有 56 个，全是 freehire）
  - 代码改动：给 AI 的数据里**去掉了招聘页上的地点**，改由代码写进简报的 `board_location`。这样同一个职位在多个城市发布（例如 Samsara 一个职位发了 8 个城市）时，请求完全相同，只付一次钱
- **为什么：** DECISIONS #22、#30、#31；批准后记为 #32。
- **文件：** `agents/evaluate_prompt.py`（含 `--review` 核对页面）、`agents/jd_analysis.py`（数据格式、`board_location`、`min_text_chars`）、`tests/fixtures/jd_golden.toml`、`config/proposals/jd-analysis.v3.md`、`config/proposals/analysis_scope.v2.toml`、`tests/test_evaluate_prompt.py`、`tests/test_jd_analysis.py`
- **提交：** 见本条所在的提交（`git log -- agents/evaluate_prompt.py`）
- **验证：**
  1. 全部 317 个测试通过，ruff 通过
  2. **真实评估**（10 个职位，Opus 5.5，共花 $1.14）：

     | | v2 medium | v3 medium | v3 low |
     | --- | --- | --- | --- |
     | 必备技能找到 | 72/75 | 73/75 | 73/75 |
     | 岗位类型对 | 9/9 | 9/9 | 9/9 |
     | 工作方式对 | 9/10 | 9/10 | 10/10 |
     | **经验年限对** | **7/10** | **10/10** | **10/10** |
     | 每篇费用 | $0.043 | $0.038 | $0.033 |

     v3 修好了年限：Voto 3 → 7、Samsara 3 → 10、Anthropic 空 → 5。判定 PASS
  3. 剩下的差异都很小：v3 在 Anthropic 漏了 "Orchestration"、在 Reddit 漏了 "Dashboards"；v2 在 Bold Penguin 漏了 LLM、在 Rosen's 漏了 Data warehousing、在 Samsara 漏了 PySpark。这些属于模型每次回答的正常波动，10 个样本看不出谁更好
- **你核对后的补充（11/02）：** 你在核对页面上指出，ASSYST 的 HL7/FHIR/SNOMED、Rosen's 的 Unity Catalog、Samsara 的 MCP 都没有标。它们写在 Preferred、Additional 或职责里，所以不算必备；AI 其实都把它们放进了加分项，只是标准答案没检查加分项。于是：
  - 标准答案加了 `nice_to_haves`（7 个职位共 28 个），评估多了两项检查："加分技能有没有被保留"（不能少于现行版本减 1）、"有没有被错放进必备"（不能多于现行版本加 1）
  - 核对时发现 Bold Penguin 的 JIRA 其实写在要求列表里（没写 "a plus"），AI 把它放进必备是对的，错的是我的标签，已改为必备
  - 核对页面做成了正式功能：`agents.evaluate_prompt <提议> --review` 生成 `output/golden_review.html`（不提交），原文里必备标黄、加分标蓝
  - "root cause / troubleshooting" 这类所有工程岗位都有的通用说法不标：ATS 不搜它，简历上也不能当关键词
  - 重新打分（全部来自缓存，$0）：v3 必备 74/76（v2 73/76），加分保留 28/28，错放进必备 0，年限 10/10（v2 7/10），PASS
- **11/02 你批准了：** 采用 v3、采用范围规则 v2、思考深度保持 medium（DECISIONS #32）。提议文件复制到 `.claude/skills/jd-analysis/SKILL.md` 和 `config/analysis_scope.toml`，提示词锁更新到 `jd-analysis@3`；提议文件留在 `config/proposals/` 作为历史。测试库里的样例职位都很短，所以相关测试关掉了 1,000 字符下限，另有一个测试专门检查这个下限。dry-run：范围内 425 个职位，v3 还一个都没拆，粗估 $25（按试点的实际费用约 $16）。320 个测试通过
- **撤回：** `git revert` 这个提交。提议文件不影响正在运行的系统。

### 2.2c · 2026-11-02 · 每日运行加上 AI 拆解（只拆当天的新职位）
- **做了什么：**
  - `pipeline/daily.py`：抓取 → 闸门 → 汇总之后，多一步"拆解当天的新职位"。新职位的标准和报告一样（所有副本都是这次运行第一次存进来的），再过一遍分析范围；最新的优先，每天最多 `JD_ANALYSIS_DAILY_MAX`（默认 50）个。老职位改了文字**不算**新职位，不拆，免得变相补跑
  - 整个 AI 步骤出错（比如 key 失效、网络断了）时只记下来：抓取和闸门的结果照常保存，这次运行标为 partial。单个职位失败就列出来，其余继续
  - 每日报告新增"AI 拆解"一段：范围内的新职位、拆了几个、几个来自缓存、花费、因为上限没拆的、失败的、今天最常要求的 5 个必备技能（数量相同时按名字排，保证同样的数据得出同样的报告）。`ops.daily_runs` 里也记了这些数字
  - `.env.example` 新增 `JD_ANALYSIS_ENABLED`、`JD_ANALYSIS_DAILY_MAX`；`pipeline/config.py` 新增 `daily_analysis_settings()`；`agents/jd_analysis.run()` 可以只处理指定的职位版本（`only=`），并统计必备技能和"因为上限没拆"的数量
  - CLAUDE.md：每次开工汇报每日运行时，加上 AI 拆了几个、花了多少
- **为什么：** DECISIONS #33。
- **文件：** `pipeline/daily.py`、`pipeline/config.py`、`agents/jd_analysis.py`、`.env.example`、`CLAUDE.md`、`tests/test_daily.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/daily.py`）
- **验证：**
  1. 新增 7 个测试，全部 327 个通过，ruff 通过。用假 AI 跑完整的每日流程：只拆当天新的、在范围内的职位（测试数据里 4 个新职位：藏攻击的那个被闸门拦下，一个陈旧的被跳过，所以拆了 2 个）；同一天再跑一次，不再拆，也不再调用 AI；上限生效；改过文字的老职位不拆；AI 整步出错时抓取照常保存，状态为 partial；单个职位被拒时，其余继续；关掉开关时报告写"已关闭"
  2. **真实运行两次：** run 6 是 partial，因为 freehire 读取超时（他们那边偶尔会这样），AI 步骤正常执行，拆了 0 个；run 7 ok，新增 4 个职位，但都不是 DE，所以拆了 0 个。离上一次运行只隔了几个小时，没有新的 DE 职位，属于正常情况
  3. **还没有在真实的新 DE 职位上跑过 AI 步骤**：第一次是下一次定时运行（11/03 9:30）。AI 调用本身在试点和评估里已经真实跑过很多次
- **撤回：** `git revert` 这个提交；或者只在 `.env` 里设 `JD_ANALYSIS_ENABLED=false`。

### 2.2d · 2026-11-02 · 给 CDW 的报警打标签
- **做了什么：** 你确认 CDW "Sales Goals Analytics Lead" 的报警（"As an AI forward company, we see AI not just as a tool…"）是误报：这句话在描述公司，没有任何隐藏内容，而且不是 DE 岗位。标为 `false_positive`（标签 24），导出后标准答案共 14 条。规则不变，它继续留在"人工看"这一档，不会送给 AI。
- **文件：** `tests/fixtures/gate_cases_labeled.jsonl`
- **验证：** 规则相关测试 113 个通过（标签和现行规则不矛盾）。
- **撤回：** 从 jsonl 删掉这一行；数据库里的标签可以用一条新的 `unsure` 标签覆盖（标签只追加，以最新一条为准）。

### 2.2e · 2026-11-02 · 覆盖率检查：你在 LinkedIn 上看到的职位，我们有没有
- **做了什么：**
  - `pipeline/find_job.py`：`uv run python -m pipeline.find_job "公司" "职位名关键词"`。在所有已存的职位里查：公司名忽略大小写、标点和 LLC/Inc 这类后缀，匹配招聘页代号、slug 或公司全名的开头；职位名按"连续的词组"匹配（"data engineer" 不会匹配到 "Data Center Engineer"）。找到了就说明哪个来源、哪天到哪天看到过、闸门档位、有没有拆解；没拆解的话，说明是被分析范围的哪条规则排除的
  - 没找到时，在线查一次 freehire（公司名 + 职位名，美国，最近 60 天，最多 3 页），判断最可能的原因：标题不在我们的搜索词里 / freehire 有、标题也对得上（多半是在我们的抓取窗口之前发布的）/ 是我们直接抓的招聘页但没存到 / 我们的来源都没有 / 说不准（检查失败，或者结果太多没看完）
  - 每次检查都记进 `ops.coverage_checks`（迁移 011）；`--stats` 给出覆盖率（找到 / 查过）和各个原因的数量
  - 两个坑：freehire 的搜索没有按公司筛选的功能；而且一加公司名，它就不再按标题筛选（返回了 Snowflake 的所有职位，包括 "Revenue Manager"）。所以公司和标题都在我们这边再筛一遍；结果没看完时，如实说"说不准"，不硬下结论
- **为什么：** DECISIONS #34。
- **文件：** `pipeline/find_job.py`、`db/migrations/011_coverage_checks.sql`、`tests/test_find_job.py`
- **提交：** 见本条所在的提交（`git log -- pipeline/find_job.py`）
- **验证：**
  1. 新增 13 个测试，全部 341 个通过，ruff 通过。覆盖：公司名的各种写法、职位名按词组匹配、找到的职位说明为什么没被拆解（测试数据里的攻击职位显示 "gate triage block"）、五种没找到的原因、freehire 检查失败时问题照样记下、覆盖率统计
  2. **我自己试了 4 个真实例子（试完已从记录里删掉，不算进你的覆盖率）：** Anthropic Data Engineer：找到，已拆解；Sigma Computing Data Engineer：找到（在分析范围内，但早于每日 AI 拆解，所以没拆）；Netflix Analytics Engineer：**没抓到**，freehire 上有，但发布于 10/20 和 9/09，早于我们第一次回填 freehire 的时间（10/31 往回 7 天）；Snowflake Data Engineer：说不准（freehire 结果太多没看完）
- **发现：** 我们是从 10/31 开始、往回 7 天抓 freehire 的，所以**更早发布、但现在还在招的职位一个都没有**。如果要补，一次性把 freehire 往回抓 30 天就行，不花 AI 的钱（只是多一些请求），等你决定。
- **撤回：** `git revert` 这个提交；数据库执行 `drop table ops.coverage_checks`，再从 `public.schema_migrations` 删掉 `011_coverage_checks.sql`。

### 2.2f · 2026-11-02 · 修 freehire 翻页的 bug，回填 30 天
- **做了什么：**
  - **发现一个真 bug：** 回填时，"data engineer" 只抓到 899 个就停了。查了 API 返回才发现：freehire 说一共有 11,298 个结果，但在第 850 条那一页只给了 49 条（应该 50 条）。我们的代码把"这一页不满"当成"没有更多了"，于是停下，后面的一万多条全丢了。**每天的运行也可能因此提前停下，漏掉职位。** 已经改成按 API 返回的总数 `meta.total` 来判断有没有翻完；只有 API 没给总数时，才把不满的一页当成最后一页
  - **回填 30 天**（你批准的，只抓取、过闸门，不调用 AI）：按标题分成两组搜索。"data engineer" 30 天内有 11,298 个，超过 API 最多能翻的 10,000 个，所以又按工作方式（远程 / 混合 / 坐班）各搜了一遍，补上窗口之外的部分。重复的职位只存一份
  - 第一次回填时 freehire 读取超时，加上上面这个 bug，结果不完整；修好之后重跑了一遍完整的
- **文件：** `ingestion/freehire.py`（翻页逻辑）、`tests/test_freehire.py`（新增"中间有一页不满时不能停"的测试）
- **提交：** 见本条所在的提交（`git log -- ingestion/freehire.py`）
- **验证：**
  1. 全部 342 个测试通过，ruff 通过
  2. 回填结果：analytics engineer 看到 3,062 个；data engineer 看到 9,995 个（API 窗口上限），新增 4,326 个；按工作方式补的三遍又新增 613 个（远程 357、混合 144、坐班 112）。闸门新检查了 4,939 个：clean 4,915、benign 19、review 5、block 0。库里现在一共 15,434 个职位（原来约 7,200 个）
  3. **再查 Netflix：** 10/20 发布的 "Analytics Engineer 5 - Ads Identity & Signals" 现在找到了。9/09 的那个超过 30 天，不在这次回填范围内，符合预期
  4. **还剩的缺口（如实记下）：** 按工作方式补的三遍加起来是 5,301 个，而 data engineer 总共 11,298 个，说明很多职位没标工作方式，所以窗口之外那大约 1,300 个只补回了一部分。每天的运行只看 2 天，大约 1,300 个结果，远低于 10,000 的上限，不受影响
- **撤回：** `git revert` 这个提交。回填进来的职位不用删：它们和其他职位一样，是原样存下来的原始数据。
- **备注：** 新增 5 个 review 报警（目前没打标签的一共 11 个），等你有空时一起看；review 档的职位本来就不会送给 AI。
