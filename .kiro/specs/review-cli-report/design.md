# Design Document

## Overview

C 线在数据流末端，职责是**装配与出口**：把 A 线的 `DiffUnit`、B 线的 `RuleHit` 装配成一份报告，再从三个出口（CLI 终端、REST 接口、CI 退出码）把它交出去。

核心设计约束只有一条：**报告是单一数据源**。三个出口消费的是同一个对象，不是三次各自查询。否则 CLI 看到的和页面看到的会不一致，而那种不一致极难排查。

## Architecture

### 分层与依赖方向

```
        ┌──────────┐      ┌──────────┐
        │   cli    │      │   api    │      ← 两张脸
        └────┬─────┘      └────┬─────┘
             │                 │
             └────────┬────────┘
                      ▼
                 ┌─────────┐
                 │  infra  │                  ← 真干活
                 └────┬────┘
                      ▼
                 ┌──────────┐
                 │ contract │                 ← 唯一的叶子包
                 └──────────┘
```

**依赖规则（R-01 ~ R-06）**

| 编号 | 规则 | 性质 |
|---|---|---|
| R-01 | CLI 不依赖 api，反之亦然 | 禁止性 |
| R-02 | 只有 api 对外暴露 HTTP | 禁止性 |
| R-03 | web 只依赖 contract 的 TS 类型定义 | 落在具体依赖上 |
| R-04 | ruleset 只经 aigateway 调模型，不直连 | 落在具体依赖上 |
| R-05 | aigateway 不反向依赖 ruleset | 禁止性 |
| R-06 | contract 不依赖任何内层包 | 禁止性 |

R-03 与 R-04 能画到图上；R-01/02/05/06 是"不许存在这条箭头"，画出来反而误导，按编号人工评审。

### 三个设计模式及各自防的错

| 模式 | 位置 | 防什么 |
|---|---|---|
| **策略** | `cli/render.py`，text/json/sarif 三实现 + 注册表 | 换格式要改调用方；加了第四种格式得在五处加 `if` |
| **工厂** | `cli/parser.py`，按后缀查表返回解析器 | 加语言变成改主干逻辑；`if/elif` 链条无限增长 |
| **模板方法** | `infra/ruleset.py`，基类定四步，子类只写 `check` | 有人新加规则时忘写去重，导致 `total` 与明细不一致（Q-05 真实故障） |

模板方法的实现要点：`run()` 里写死 **归一化 → 逐块检查 → 分级 → 去重** 四步，`dedupe` 与 `counts_of` 都在基类。子类没有机会漏写去重，因为**它拿不到那一步的控制权**。

## Components and Interfaces

### contract（叶子包）

```python
class Report(BaseModel):
    schema_version: Literal["2.0"]
    run_id: str
    repo: str
    git_ref: str
    commit_sha: str          # 40 位
    status: Status           # done / partial / failed
    status_reason: StatusReason | None
    started_at: datetime
    counts: Counts           # blocking / warning / info / total
    kinds: list[str]
    findings: list[Finding]
```

三条 `model_validator(mode="after")` 在构造时强制生效：V-01 数字自洽、V-02 标签与明细一致、V-03 状态必须交代原因。

**为什么放在构造时而不是事后检查**：事后检查靠人记得调用；构造时校验，不合格的对象**根本创建不出来**。

### infra（真干活）

```python
class RuleSetBase(ABC):
    def run(self, units):        # 四步固定，子类不可改
        ...

    @abstractmethod
    def check(self, unit): ...   # 子类唯一入口

    @staticmethod
    def counts_of(findings) -> Counts:
        ...                      # 从明细反推，保证与 findings 同源
```

`counts_of` 从明细反推而非独立统计，是 V-01 那类故障的结构性解法：数字和明细不可能不同源。

### cli / api（两张脸）

- `cli/main.py` 的 `run()` 是主流程，七步：收集 → 选解析器 → 判定 → 计数 → 构造报告 → 渲染 → 定退出码
- `api/app.py` 只做装配：注册 13 个路由、统一异常出口、`/healthz` 探活。业务逻辑全在 infra，路由层不写 `try/except`

## Data Models

### 存储（SQLite 本地 / PostgreSQL 生产，同接口双后端）

| 表 | 用途 | 设计要点 |
|---|---|---|
| `review_run` | 一次审查 | `counts` 用 jsonb，加字段不改表；代价是不能建普通索引，补 GIN |
| `finding` | 单条命中 | `rule` **不加外键**——规则会下线改名，历史报告不能被牵连；靠 `enabled=false` + 每日对账兜底 |
| `rule_def` | 规则元信息 | 供 `kinds` 校验与幻觉检测 |
| `audit_log` | 操作审计 | 按月 RANGE 分区，归档 = 一条 `DETACH PARTITION` |

### 分页

| 场景 | 方式 | 理由 |
|---|---|---|
| `page <= 100` | OFFSET | 写法直观，前端好接 |
| 深页 / 无限滚动 | `(started_at, run_id)` 行值比较 | OFFSET 要读掉前序全部行；实测 20 万行时 27.32 ms → 0.024 ms |

用两个字段而非一个时间戳：同一毫秒的多条记录，单字段比较会漏或重。

## Error Handling

8 个错误码，两段编码：4xxx 调用方问题，5xxx 我方问题。

| 码 | HTTP | 场景 |
|---|---|---|
| `CR-4000` | 400 | 参数不合法（如 cursor 无法解析） |
| `CR-4001` | 401 | 未带 token |
| `CR-4004` | 404 | run_id / rule 不存在 |
| `CR-4009` | 409 | 同 diff 的任务正在跑 |
| `CR-4013` | 413 | 上传过大 |
| `CR-4015` | 415 | 不支持的文件后缀 |
| `CR-4029` | 429 | 触发限流 |
| `CR-5000` | 500 | 未预期异常，不泄露堆栈 |

**翻译只在边界发生一次**：业务代码抛 `ApiError`，`app.py` 的 `exception_handler` 统一转成 `{code, message, data:null, traceId, timestamp}`。路由函数里不写 `try/except`。

## Testing Strategy

三层，23 条：

| 层 | 文件 | 数量 | 打什么 |
|---|---|---|---|
| 契约 | `test_contract.py` | 5 | 三条校验能否拦住非法报告 |
| 模式 | `test_patterns.py` | 5 | 工厂按后缀分发、策略三格式一致、模板方法去重 |
| 接口 | `test_api.py` | 13 | 13 个路由的状态码与返回结构 |

**不测什么**：解析器切块的正误（A 线职责）、规则判定的准确性（B 线职责）。本层只保证"装配正确、出口一致、错误可读"。

## Correctness Properties

1. 对任意报告实例，`counts.total == len(findings)` 恒成立（构造时校验，不满足则对象不存在）
2. 对任意审查结果，三种格式输出的命中条数恒相等
3. 对任意 `--fail-on` 配置，退出码只可能是 0、1、2 之一
4. 对任意翻页序列，按 `cursor` 遍历全量记录时不重不漏
5. 对任意接口响应，响应体必定含 `code`/`message`/`data`/`traceId`/`timestamp` 五个键
