# 营销沙盘可视化网站运行指引

这个网站不是一个可以直接双击 `index.html` 就完整运行的静态页面。

当前前端基于 Vite 和 Three.js。页面内容由 `src/main.js` 挂载到 `#app`，所以要先启动本地网页服务，再用浏览器打开服务地址。

## 快速启动

最省事的方式是在项目根目录双击：

```text
start_marketing_sandbox.bat
```

它会自动启动 Python 后端、Vite 前端，并打开网站。

如果只看示例回放，在项目根目录执行：

```powershell
cd visualization_site
npm.cmd install
npm.cmd run dev
```

然后打开终端显示的本地地址。默认通常是：

```text
http://127.0.0.1:5173/
```

如果 `5173` 已被占用，以 Vite 在终端打印出来的地址为准。

## 真实搜索启动方式

如果要点 `真实运行`，需要同时启动 Python 本地后端。建议开两个终端。

终端 1：启动后端。

```powershell
python -m marketing_sandbox.web_server --host 127.0.0.1 --port 8765
```

终端 2：启动前端。

```powershell
cd visualization_site
npm.cmd run dev
```

前端的 `/api/sandbox/*` 已通过 Vite proxy 转发到 `http://127.0.0.1:8765`。
如果 `8765` 端口被占用，可以换一个端口，但也要同步修改
`visualization_site/vite.config.js` 里的 proxy target。

后端可选读取环境默认 API 配置：

```powershell
$env:MARKETING_SANDBOX_BASE_URL="https://your-provider.example/v1"
$env:MARKETING_SANDBOX_API_KEY="你的临时 Key"
python -m marketing_sandbox.web_server
```

也可以直接在网页里填写 Base URL、API Key 和模型名。本地后端会用这些信息
调用真实模型，但不会把 API Key 写入事件、存档或导出。

注意：`provider-check` 会先访问 `/models`，再发一次极短的 chat completion，
用来确认模型名真的可调用；它会消耗很少量 token。

## 真实 API 烟测

项目提供了一个命令行烟测入口，不需要先打开网页：

```powershell
python -m marketing_sandbox.api_smoke
```

这个命令默认只跑本地失败场景，不会调用外部模型。它会检查：

- 错 Key 的报错是否安全。
- 错模型名是否能被识别。
- 错 Base URL 是否会在本地被拒绝。
- 运行中 provider 报错是否会变成安全的 run failure。
- 用户停止、停止后存档、存档后返回续跑计划是否能走通。

如果要真的调用一个低成本 OpenAI-compatible provider，可以用环境变量显式开启。
推荐先用 Groq 的 OpenAI-compatible 入口做烟测：

- 官方 OpenAI-compatible 文档：https://console.groq.com/docs/openai
- 官方模型列表：https://console.groq.com/docs/models

示例：

```powershell
$env:MARKETING_SANDBOX_SMOKE_RUN_REAL="1"
$env:MARKETING_SANDBOX_SMOKE_BASE_URL="https://api.groq.com/openai/v1"
$env:MARKETING_SANDBOX_SMOKE_MODEL="llama-3.1-8b-instant"
$env:MARKETING_SANDBOX_SMOKE_API_KEY="你的临时 Key"
python -m marketing_sandbox.api_smoke --real
```

真实烟测会依次做：

1. provider-check。
2. 单轮真实 live event stream。
3. 检查角色发言、reward 和 UCB 事件是否出现。
4. 保存后端存档。
5. 请求存档续跑计划。

烟测报告只会显示 `apiKeyPresent: true/false`，不会打印 API Key 明文。

## 能直接演示什么

只启动前端服务时，网站已经可以：

- 播放示例事件流。
- 载入课堂数据包。
- 看三维沙盘、策略对比、内部 reward / UCB 搜索轨迹说明。
- 导出当前事件流的 Markdown 摘要。

打开页面后，可以先点：

1. `载入课堂数据包`
2. `播放` 或 `单步`

## 课堂演示建议路径

建议课堂演示按这个顺序走，先保证观众看懂沙盘，再展示真实接线：

1. 启动前端：`cd visualization_site`，然后 `npm.cmd run dev`。
2. 打开 `http://127.0.0.1:5173/`。
3. 点击 `载入课堂数据包`，确认人群卡为 `10 selected`。
4. 点击 `单步` 或 `播放`，讲清楚 Decision、Consumer、Feedback、Critic 的说话顺序。
5. 看右侧 `Family 轨迹`，说明 reward / UCB 是内部搜索指标，不是购买率或市场预测。
6. 在 `停止与存档` 里导入课堂存档，点击 `导入回看`，展示刷新后也能回看。
7. 点击 `安全续跑`，说明续跑需要重新填写 API Key，并且只能从完整轮次的安全边界继续。
8. 如果要真实跑模型，先启动后端，再切到 `真实搜索`，填写 Base URL、API Key 和模型名，点击 `配置预检`。
9. `配置预检` 通过后再点 `真实运行`；运行中点 `停止`，等后端停在安全边界后再选择是否存档。

课堂现场最稳的讲法是：

- 先用课堂数据包演示界面和搜索逻辑。
- 再切真实搜索演示 provider-check。
- 最后用短轮次真实运行证明 Python 沙盘和网页事件流已经接通。

## 真实搜索还需要什么

如果要点 `真实运行`，前端会调用本地后端的这些 live 接口：

- `/api/sandbox/live-events`
- `/api/sandbox/runs/stop`
- `/api/sandbox/archives`
- `/api/sandbox/provider-check`
- `/api/sandbox/archives/{archive_id}/resume`

当前 Python 项目已经有 Web 会话、事件流、生命周期桥接类和标准库 HTTP 服务；
前端示例回放不依赖真实模型接口。

## 真实运行和示例回放的区别

`示例回放` 只播放内置事件和课堂数据包，不调用外部模型，也不需要 API Key。

`真实搜索` 会把网页配置交给本地 Python 后端，由后端调用真实模型并推送 live event stream。真实搜索必须先通过 `配置预检`，否则 `真实运行` 会保持禁用。

`停止` 不是暂停动画。暂停只影响页面播放；停止会请求后端在安全轮次边界结束搜索。只有完整轮次之前的事件会进入可续跑存档。

存档规则：

- 前端本地存档用于课堂回看和演示。
- 后端真实存档用于真实搜索恢复。
- 存档不会保存明文 API Key。
- 续跑必须重新提供可用凭据。

## 常见失败提示和排查顺序

1. 页面停在启动指引：不要双击 `index.html`，要用 `npm.cmd run dev` 打开 Vite 地址。
2. `配置预检` 提示配置没齐：检查运行来源是否为 `真实搜索`，Base URL、API Key、模型名、产品事实、人群卡、动作集和 family 是否填写完整。
3. `provider.baseUrl must be an HTTP(S) URL`：Base URL 格式不合法，不能只写模型名或裸域名。
4. `Provider check failed with HTTP 502`：通常是本地后端没启动，或 Vite proxy 找不到 `127.0.0.1:8765`。
5. 模型不可调用：确认模型名在 provider 里存在，并且当前 Key 有权限。
6. 真实运行失败但页面没有泄露 Key：这是正常安全边界；换 Key、Base URL 或模型名后重新做 `配置预检`。
7. 看不到课堂存档：先点击 `载入课堂数据包`；页面会同时显示后端真实存档和本地演示存档。

## 本轮网页验收记录

2026-05-23 已完成一轮本地网页验收：

- Vite 前端可从 `http://127.0.0.1:5173/` 正常加载。
- 后端 `/api/sandbox/archives` 可通过 Vite proxy 访问。
- 默认页面显示 `10 selected` 人群卡。
- 示例回放 `单步` 可以推进到事件状态。
- `载入课堂数据包` 后，本地课堂存档会出现在存档下拉框。
- `导入回看` 可以恢复课堂存档事件流。
- `安全续跑` 会进入需要重新 provider-check 的续跑准备态。
- 空真实配置、半填配置、错误 Base URL 都会阻止真实运行。
- 后端未启动时，provider-check 会失败并保持 `真实运行` 禁用。
- 错误路径不会把测试用 API Key 明文显示在页面上。

当前环境没有可用真实 API Key，所以还没有在本机完成外部 provider 的真实模型调用。拿到临时 Key 后，按上面的“真实 API 烟测”和课堂演示路径即可验证真实端到端运行。

## 常见空白页原因

### 直接双击 `index.html`

直接用 `file://` 打开时，Vite 的模块入口和依赖加载路径不成立。页面会显示启动指引，不会进入三维沙盘。

### 没装依赖

第一次运行要先执行：

```powershell
npm.cmd install
```

### 前端服务没开

每次想打开工作台时，都要保证这个命令仍在运行：

```powershell
npm.cmd run dev
```

终端停掉后，本地网址也会失效。
