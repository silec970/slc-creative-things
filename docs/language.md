# 语言、类型与精度

## 值类型

公开 JSON 类型包括：

| 类型 | 含义 |
|---|---|
| `Int` | 任意精度整数 |
| `Rational` | 规范化 fraction，保持精确 |
| `ComplexExact` | 实部/虚部均为有理数的精确复数 |
| `Symbolic` | 精确符号表达式 |
| `ApproxReal` / `ApproxComplex` | mpmath 高精度近似数 |
| `FixedInt` | 8/16/32/64 位有符号或无符号定宽整数 |
| `Float64` | IEEE 754 binary64 位级值 |
| `Matrix` / `Vector` / `Set` | 结构值 |
| `Quantity` / `Unit` | 标量、维度和 SI 单位 |
| `Bool` / `String` / `Function` / `Table` / `Null` | 程序员与数据值 |

精确值只能由精确输入和精确性保持操作产生。任何近似输入都会使结果标记为
`exact: false`，并在界面使用 `≈`。

## 语法

```supercalc
x := 1/3
f(x) := x^2 + 1
solve(x^2 = 9, x, real)
assume(x, real, positive)
```

- 赋值使用 `:=`，方程使用 `=`。
- 支持隐式乘法：`2x`、`3 sin(x)`、`2(pi + 1)`。
- 运算符：`+ - * / % ^`、`&& || not`、`& | xor ~ << >>`、比较和 `? :`。
- 列表/向量 `[1, 2]`，矩阵 `[[1, 2], [3, 4]]`，集合 `{1, 2}`，范围 `1..10`。
- 数字：`0xFF`、`0b1010`、`0o755`、`1_000_000`、`1e-3`。
- 字符串：单引号或双引号，支持转义。
- `#` 或 `//` 开始行注释。

## 模式与精度

- 默认精确模式，50 位有效数字。
- 精确模式下 `0.1` 解析为 `1/10`。
- 近似模式下十进制字面量显式转换为当前精度的二进制近似，并产生 `SC3001`。
- `n(expr, digits)` 或 `approx(expr)` 显式数值化。
- `f64(expr)` 创建 IEEE binary64；`bits(f64(0.1))` 显示符号、指数、尾数和分类。
- 舍入选项：`half_even`、`half_up`、`floor`、`ceiling`、`down`、`up`。
- 角度单位：`radians` 或 `degrees`。

## 误差说明

MVP 显示近似标记、二进制精度位数、舍入模式和至少 1 ULP 的提示。它不是严格区间
算术，也不会把启发式误差提示称为证明。严格误差界和区间类型位于后续路线图。

## 假设系统

```supercalc
assume(x, real, positive)
simplify(sqrt(x^2))
```

可用性质包括 real、complex、positive、negative、integer、rational、irrational、
nonzero、zero、even、odd、finite 和 infinite。互斥性质会返回诊断。求解时不会在无
定义域信息时承诺所有解；用户应明确给出 `real`、`integer` 等定义域。

## 常用函数

- 化简：`simplify`、`expand`、`factor`、`together`、`apart`
- 微积分：`diff`、`integrate`、`nintegrate`、`limit`、`series`、`summation`、
  `product`、`findroot`
- 方程：`solve(equation, variable[, domain])`
- 矩阵：`det`、`inv`、`rank`、`transpose`、`eigenvalues`、`eigenvectors`、`lu`、`qr`
- 程序员：`i64`、`u64`、`bitand`、`bitor`、`bitxor`、`rotl`、`rotr`、`popcount`、
  `base`、`gcd`、`lcm`、`isprime`、`modpow`、`comb`
- 编码：`b64encode`、`b64decode`、`urlencode`、`hexencode`、`sha256` 等
- 数据：`json_parse`、`json_stringify`、`csv_parse`、`regex_test`、`timestamp`

## 脚本 DSL

```supercalc
fn square_sum(n) {
    total := 0
    for k in 1..n {
        total := total + k^2
    }
    return total
}

assert square_sum(10) == 385 : "square sum mismatch"
```

支持递归纯函数、`if/else`、`while`、`for`、`return`、`assert` 和插件目录内的
`.scscript` 模块。解释器不暴露 Python 对象、反射、文件、网络或进程接口，并按
步数、递归深度、集合长度和执行时间限额运行。

## LaTeX

LaTeX 导入支持 `\frac`、`\sqrt`、上下标、常用希腊字母、三角函数、括号和
`bmatrix`。不支持的宏会作为明确错误处理。导出使用当前值的 LaTeX 表示；WYSIWYG
预览使用 MathText 子集，无法显示时会保留可复制源码。

