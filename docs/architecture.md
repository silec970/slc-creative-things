# 架构说明

## 选型结论

| 方案 | 结果 | 原因 |
|---|---|---|
| PySide6 / Qt Widgets + Python 3.13 | 采用 | 原生窗口、文件对话框、打印、剪贴板和进程集成成熟；可直接使用 SymPy、mpmath、NumPy，正确性验证成本最低。 |
| Tauri 2 + TypeScript/Rust | 未采用 | 当前构建机无 Rust 工具链，CAS 仍需 Python sidecar，会引入两套运行时。 |
| C++/Qt + SymEngine | 未采用 | 性能和包体有优势，但求解、打印、多平台发行及首版交付风险更高。 |

固定依赖：PySide6 6.11.2、SymPy 1.14.0、mpmath 1.3.0、NumPy 2.5.3、
Matplotlib 3.11.2、PyInstaller 6.21.0。`uv.lock` 锁定完整依赖图。

## 运行结构

```text
PySide6 GUI
  └─ QProcess + JSONL（标准输入输出，仅本机子进程）
       └─ SuperCalc CLI worker
            └─ supercalc_core
                 ├─ Lexer / Pratt parser / AST
                 ├─ 精确数、近似数与单位类型
                 ├─ 求值器与自定义脚本解释器
                 ├─ SymPy CAS 适配
                 ├─ NumPy / mpmath 数值路径
                 ├─ 程序员工具与 IEEE 754
                 └─ 工作区、插件、导出
```

核心包不导入 PySide6。CLI 直接调用核心，GUI 通过长期存活的 worker 子进程调用同一核心。
worker 只使用 stdin/stdout，不绑定端口。GUI 可取消任务；超时会终止并重启 worker，
避免 SymPy 的长时间运算冻结界面。

## 模块边界

```text
src/supercalc_core/
  api.py          Engine、内建函数、工作区重放
  lexer.py        Unicode 与数字词法、源码位置
  parser.py       表达式和脚本块语法
  ast.py          带起止位置的 AST、源码与树格式化
  numeric.py      精确/近似算术、单位、矩阵、IEEE
  units.py        SI 单位与量纲
  latex.py        安全 LaTeX 子集导入、AST LaTeX 输出
  workspace.py    版本化工作区、原子保存、恢复、最近文件
  plugins.py      本地插件清单、哈希和 DSL 执行
  plotting.py     函数采样；GUI 负责原生 Qt/Matplotlib 显示
  exporting.py    Markdown、LaTeX、JSON、CSV 导出

src/supercalc_cli/  eval/run/test/ieee/ast/export/worker
src/supercalc_gui/  MainWindow、Notebook、FormulaEditor、PlotView、CommandPalette
```

## 数据流

1. 公式单元保存线性源码；WYSIWYG 控件用模板和 MathText 预览呈现核心结构。
2. 运行时将工作区单元序列化为版本化请求，通过 JSONL 发给 worker。
3. worker 建立全新 `Engine`，按顺序执行单元，维护变量、函数和假设环境。
4. 每个单元返回 `EvaluationResult`：值、类型、精确性、精度、舍入、单位、假设、
   算法、步骤和诊断。
5. GUI 更新结果卡片、变量/函数/历史面板和诊断定位器；高风险运算可由用户取消。
6. 保存时写临时文件、执行 `fsync`、原子替换，并保留 `.bak`；编辑期间自动写恢复副本。

## 错误处理

所有面向用户的失败都转换为 `Diagnostic`，而不是泄漏 Python 异常。诊断包含稳定代码、
严重级别、消息、修复建议、源码区间、行列号和片段。只有未预料的内部异常使用
`SC9000` 边界诊断。

## 测试层次

- 核心单元：精确/近似算术、CAS、矩阵、单位、IEEE、解析、工作区、插件。
- 属性测试：有理数运算、进制往返、IEEE 位域往返。
- GUI：pytest-qt 离屏启动、运行、近似警告、公式预览、绘图和保存。
- 端到端：CLI JSON、验收示例、socket 拦截离线测试。
- 打包：PyInstaller 产物执行 CLI 精确计算和无窗口 GUI 启动。

