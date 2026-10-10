## MODIFIED Requirements

### Requirement: Custom-key Ark calls have correlated lifecycle records

仅当应用处于开发模式且“记录 API 调用详情”开关启用时，系统 SHALL 为自定义 Key 的 Ark 图片生成以及视频创建、查询、列表和删除调用记录本地审计事件。每次调用 MUST 使用独立关联 ID，记录请求前意图、收到响应或失败，以及适用的本地处理阶段；图片调用关联批次与候选，视频调用在本地任务存在时关联该任务。条件不成立时 MUST 不新增任何此类日志。

#### Scenario: Image generation completes and downloads
- **WHEN** 开发模式审计开关已开启，自定义 Key 图片生成返回有效响应并完成下载
- **THEN** 审计记录标识该图片候选，包含调用开始时间、响应时间、耗时、响应状态、可用的服务端请求 ID、图片用量、URL 是否存在及本地保存或下载结果

#### Scenario: Video task is created and polled
- **WHEN** 开发模式审计开关已开启，自定义 Key 视频创建返回远端任务 ID，后续查询更新任务
- **THEN** 审计事件关联本地及远端任务 ID，记录各调用耗时及观察到的远端状态

#### Scenario: Connection check or cancellation call
- **WHEN** 开发模式审计开关已开启，客户端调用自定义 Key 的 Ark 列表或删除接口
- **THEN** 记录调用方法、接口类别、耗时、HTTP 结果或失败及可用关联 ID

#### Scenario: Recording is disabled
- **WHEN** 应用不处于开发模式，或审计开关关闭
- **THEN** 图片与视频调用、下载处理和任务恢复均不新增此类审计日志

### Requirement: Audit records survive interruption without overstating remote outcome

在开发模式审计开关启用时，系统 SHALL 在付费自定义 Key 生成 POST 发出前持久化请求意图，区分传输失败、HTTP 错误、响应格式错误、解析成功、持久化成功及下载结果。审计启用的启动恢复 MUST 将有意图而无观察到终止事件的调用标记为中断或未决，不断言 Ark 已接受或计费。审计关闭时 MUST 不依赖日志写入或日志恢复作为生成、下载、轮询及任务恢复的前提，已有任务与响应持久化机制保持有效。

#### Scenario: Client exits while image POST is pending
- **WHEN** 开关启用时已持久化付费图片请求意图，客户端退出前没有记录响应，随后在启用审计的开发模式重启
- **THEN** 审计保留调用尝试并标记为未决，不虚构图片 URL 或计费结果

#### Scenario: Response received before download fails
- **WHEN** 开发模式审计开启，系统观察到生成响应，但本地媒体下载失败
- **THEN** 审计区分成功的生成响应与失败的下载，并标明响应是否已持久化以供恢复

#### Scenario: Audit storage fails before paid submission
- **WHEN** 开发模式审计开启，付费图片或视频 POST 发出前无法持久化意图事件
- **THEN** 系统不发送该 POST，向调用方报告本地日志错误

#### Scenario: Disabled audit does not block generation
- **WHEN** 审计关闭且日志路径不可写，系统准备发起有效生成或恢复任务
- **THEN** 系统继续既有生成与任务处理，不尝试写审计日志，不因审计存储错误阻断操作

## ADDED Requirements

### Requirement: API 调用详情日志由开发模式开关控制

开发模式设置页 SHALL 提供“记录 API 调用详情”开关，缺省值 MUST 为关闭。切换成功后 MUST 立即控制后续事件写入，无需重启，也不等待其他设置统一保存；保存失败时反馈错误并恢复此前有效状态。普通运行和安装版 MUST 隐藏该开关并在后端强制关闭日志，即使持久化配置残留开启值。该开关 MUST 仅控制 `ark-custom-key.jsonl`，不改变错误日志、前端请求诊断面板及账号生成逻辑。关闭 MUST 保留已有日志文件，不追溯补写关闭期间的事件。

#### Scenario: Default and old configuration
- **WHEN** 应用首次运行或加载缺少该配置字段的旧配置
- **THEN** API 调用详情日志关闭；仅开发模式显示开关

#### Scenario: Immediate toggle
- **WHEN** 用户在开发模式切换开关并保存成功
- **THEN** 后续日志事件立即按新状态处理，无需重启或点击设置页的统一保存按钮
- **AND** 关闭前已写事件保留，关闭期间事件不在再次开启后补写

#### Scenario: Toggle fails to save
- **WHEN** 用户切换开关但配置保存失败
- **THEN** 界面反馈失败并恢复此前有效开关值，实际日志行为与该值一致

#### Scenario: Installed or ordinary run with stale enabled value
- **WHEN** 安装版或普通运行读取到开启的残留配置
- **THEN** 开关不可见且后端不新增调用详情日志，生成与任务处理仍正常
