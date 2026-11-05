# Design Document — source-parsing

## Overview

A 线只做一件事：**把非结构化的输入（目录 / diff）变成结构化的 `DiffUnit` 流**。

三个设计约束决定了实现形态：

1. **不落地**：块按流产出，不攒全量再返回，否则 200 文件会一次性占满内存（NFR-A-03）
2. **不改源文件**：只读，任何写操作都在下游（NFR-A-04）
3. **单点失败不扩散**：每个文件是独立事务，异常只影响自己（Requirement 4）

```
        ┌──────────────┐      ┌────────────┐      ┌──────────────┐
路径 ──→│ SourceScanner│─files→│   Reader   │─text→│ BlockSplitter│──→ DiffUnit[]
        └──────────────┘      └────────────┘      └──────────────┘
               ↑                     ↑                    ↑
          .gitignore 过滤        编码识别/降级        语言→注释前缀
                                                          ↑
diff ──→  ┌────────────┐                                  │
          │ DiffParser │──hunk(新行区间)──────────────────┘
          └────────────┘
```

## Architecture

### 分层与依赖方向

| 层 | 职责 | 允许依赖 |
|---|---|---|
| `scanner` | 遍历目录、应用忽略规则、产出文件路径 | 标准库 |
| `reader` | 打开文件、编码识别与降级、大文件/二进制判定 | 标准库 |
| `diff` | 解析 unified diff，产出 hunk 及其新文件区间 | 标准库 |
| `splitter` | 按语言注释前缀把行切成块，标记注释/空行 | `contract`（DiffUnit 定义） |
| `pipeline` | 串起上述组件，产出流与统计 | 以上全部 + `contract` |

依赖只向下，`contract` 无出边——与全项目「contract 是叶子包」的规则一致。

### 数据结构

```python
@dataclass(frozen=True)
class DiffUnit:
    file_path: str
    line_start: int      # 新文件坐标，1 起
    line_end: int
    text: str
    lang: str            # py / js
    is_comment: bool
    is_blank: bool
    source: str          # "scan" | "diff"
```

`frozen=True` 是有意为之：块一旦产出就是只读的，规则引擎只能读不能改，避免"规则顺手改了 text 导致去重指纹漂移"。

### 工厂而不是 if 链

语言差异只体现在两处：注释前缀、扩展名映射。用一张表表达：

```python
LANG_BY_SUFFIX = {".py": ("py", "#"), ".js": ("js", "//"),
                  ".ts": ("js", "//"), ".tsx": ("js", "//")}
```

加语言即加一行，不改逻辑。这与 C 线渲染器的策略注册表是同一思路。

## Components and Interfaces

### SourceScanner

```python
def scan(root: Path, *, respect_gitignore: bool = True) -> Iterator[Path]
```

- 按路径字典序产出（替换为有序遍历而非 `os.walk` 的自然顺序），满足 Requirement 6.2
- `.gitignore` 只做一级模式匹配（目录名、`*.ext`），不实现完整 gitignore 语法——**这是刻意的取舍**：完整语法需要引入 `pathspec` 依赖，而本阶段只需覆盖九成场景；不足处列入任务 T-11

### Reader

```python
def read_text(path: Path) -> tuple[str, str]        # (text, encoding)
def classify(path: Path, raw: bytes) -> str | None  # None 表示可解析，否则返回跳过原因
```

编码尝试顺序：`utf-8-sig` → `gbk` → `utf-8(errors="replace")`。顺序不能颠倒：先 UTF-8 是因为它是主流且能识别 BOM；GBK 放第二是因为中文环境常见；最后才是替换降级。

### DiffParser

```python
def parse(unified_diff: str) -> Iterator[Hunk]      # Hunk: path, new_start, new_len, lines
```

只解析 `@@ -a,b +c,d @@` 与紧随其后的 `+`/` ` 行；`-` 行丢弃（旧文件内容不参与审查）。

### BlockSplitter

```python
def split(hunk_or_file, lang: str, source: str) -> list[DiffUnit]
```

切块规则：连续非空行合并为一块；空行断开但不单独成块；跨过空行后行号继续累加，不回退。

## Data Models

| 实体 | 字段 | 说明 |
|---|---|---|
| `DiffUnit` | 8 字段（见上） | 冻结契约，B/C 线消费 |
| `Hunk` | path / new_start / new_len / lines | diff 中间结构，不外传 |
| `ScanStats` | files_scanned / skipped_count / skipped_reasons / blocks_total | 供 C 线写 `counts` 附注 |
| `Skipped` | path / reason | reason ∈ {binary, too_large, unsupported_lang, decode_error} |

## Error Handling

| 场景 | 处理 | 对外表现 |
|---|---|---|
| 路径不存在 | 立即失败 | 退出码 2，`path_not_found` |
| `--diff` 的 ref 无效 | 立即失败 | 退出码 2，`git_ref_invalid` |
| 单文件读失败 | 跳过该文件 | 进 skipped，整体继续 |
| 编码非法 | 替换符降级 | 进 skipped 附注 `decode_warning` |
| 二进制 / 超大 | 跳过 | 进 skipped，原因明确 |

原则：**能降级的降级，不能降级的立刻失败**。参数错误（路径不存在）属于后者——继续跑只会产出一份空报告，比直接报错更难排查。

## Correctness Properties

供属性测试使用（输入随机化，断言恒成立）：

1. **行号单调**：同一文件内任意两个块，先产出的 `line_start` 不大于后产出的
2. **块内连续**：`line_end - line_start + 1 == text.count("\n") + 1`
3. **不重叠**：同一文件内任意两块的行区间不相交
4. **覆盖率**：全量扫描时，所有可解析行的并集覆盖文件全部非空行
5. **幂等**：同一输入两次运行，输出序列逐元素相等（对应 Requirement 6.2）

## Testing Strategy

| 层级 | 内容 | 数量（目标） |
|---|---|---|
| 单元 | 后缀映射、编码回退、hunk 解析、切块边界（全空行/单行/跨空行） | 12 |
| 属性 | 上述 5 条正确性属性，随机生成文本与 diff | 5 |
| 集成 | 目录树样例（含二进制、超大、GBK、损坏文件）跑通 pipeline | 4 |
| 性能 | 200 文件基准，取 P95 与峰值内存 | 2 |

## Dependencies

- 仅标准库（`pathlib`、`re`、`codecs`、`hashlib`）
- 契约定义来自 `codereview.contract`（`DiffUnit` 的 Python 镜像）

不引入第三方解析库的理由：本阶段只做行级切块，`tokenize` 与 AST 属于实验四的增强项；引入依赖会拖慢 CI 且增加环境不确定性。
