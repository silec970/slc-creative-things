# 内置函数参考

本参考覆盖超级计算器 0.1.0 中全部可调用的内置函数、函数别名、常量、单位和运算符。
表格中的方括号表示可选参数。函数名、运算符和表达式关键字使用 ASCII，以便脚本复现。

## 使用约定

- 函数名区分大小写；示例使用小写。
- 精确输入优先保持精确结果；出现近似输入时结果标记为近似。
- 三角函数受工具栏“角度”设置影响，默认为弧度。
- 错误会返回诊断码和源码位置，不会静默替换为错误结果。
- `x`、`y` 等未赋值名称会作为符号变量，而不是同名函数。

## 常量

| 名称 | 含义 | 示例 |
|---|---|---|
| `pi` | 圆周率 | `sin(pi/2)` |
| `e` | 自然常数 | `ln(e)` |
| `i` | 虚数单位 | `(1 + i)^2` |
| `oo` | 正无穷符号 | `limit(1/x, x, oo)` |
| `nan` | 非数近似值 | `f64(0/0)` 会先产生除零错误 |
| `true` / `false` | 布尔常量 | `true and not false` |

## 单位

内置单位包括 `m`、`km`、`cm`、`mm`、`s`、`ms`、`min`、`h`、`kg`、`g`、
`A`、`K`、`mol`、`cd`、`N`、`J`、`W`、`Pa`、`Hz`。

```supercalc
3 m + 20 cm
to(3 m + 20 cm, cm)
(2 J) / (4 s)
```

同维度数值可以加减；乘除会组合量纲；不可把不同维度直接相加。

## 数值与精度

| 函数 | 说明 |
|---|---|
| `approx(expr)` | 将精确数或数值表达式转换为当前精度近似值。 |
| `n(expr[, digits])` | 指定有效十进制位数进行数值化；默认使用工作区精度。 |
| `f64(expr)` | 转为 IEEE 754 双精度值，并保留位域元数据。 |
| `ieee64(expr)` | 返回双精度值及可检查的位域信息。 |
| `bits(value)` | 显示双精度符号位、指数位、尾数位、十六进制和分类。 |
| `to(value, unit)` | 将带单位数值转换成目标单位，例如 `to(1 km, m)`。 |
| `convert(value, unit)` | `to` 的别名。 |

示例：

```supercalc
n(pi, 50)
f64(0.1)
bits(f64(0.1))
to(90 min, h)
```

## 基础数学

| 函数 | 说明 |
|---|---|
| `abs(x)` | 绝对值；符号值保持为符号绝对值。 |
| `sign(x)` | 返回 -1、0 或 1；符号输入保留符号形式。 |
| `floor(x)` | 向下取整。 |
| `ceil(x)` | 向上取整。 |
| `round(x[, digits])` | 按指定小数位数舍入。当前实现可能返回近似值。 |
| `factorial(n)` | 非负整数阶乘，参数上限为 100000。 |
| `gamma(x)` | 伽马函数。 |
| `sqrt(x)` | 平方根；精确平方会化简，其他情况保持符号表达式。 |
| `cbrt(x)` | 实数立方根。 |
| `sin(x)` | 正弦。 |
| `cos(x)` | 余弦。 |
| `tan(x)` | 正切。 |
| `asin(x)` | 反正弦。 |
| `acos(x)` | 反余弦。 |
| `atan(x)` | 反正切。 |
| `ln(x)` | 自然对数。 |
| `log(x[, base])` | 单参数时为自然对数；双参数时为指定底数对数。 |
| `exp(x)` | 指数函数。 |

```supercalc
sqrt(4)
sqrt(2)
sin(pi/6)
log(1000, 10)
```

## 化简与代数

| 函数 | 说明 |
|---|---|
| `simplify(expr)` | 使用当前变量假设做符号化简。 |
| `expand(expr)` | 展开乘积和幂。 |
| `factor(expr)` | 因式分解。 |
| `together(expr)` | 合并为单个分式。 |
| `apart(expr, variable)` | 对指定变量做部分分式分解。 |
| `assume(variable, property, ...)` | 为变量添加实数、正数、整数等假设。 |

假设性质：`real`、`complex`、`positive`、`negative`、`integer`、`rational`、
`irrational`、`nonzero`、`zero`、`even`、`odd`、`finite`、`infinite`。

```supercalc
assume(x, real, positive)
simplify(sqrt(x^2))
expand((x + 1)^3)
apart((x + 1)/(x^2 - 1), x)
```

## 微积分

| 函数 | 说明 |
|---|---|
| `diff(expr, variable[, order])` | 对变量求导；默认一阶。 |
| `integrate(expr, variable)` | 不定积分。 |
| `integrate(expr, variable, lower, upper)` | 定积分；无法求出精确结果时返回诊断。 |
| `nintegrate(expr, variable, lower, upper)` | 高精度自适应数值积分。 |
| `findroot(expr, variable[, guess])` | 从初值开始进行数值求根。 |
| `limit(expr, variable, point[, direction])` | 求极限；方向可传 `+`、`-` 或 `both`。 |
| `series(expr, variable, point[, order])` | 泰勒/洛朗级数，默认展开到 6 阶。 |
| `summation(expr, variable, lower, upper)` | 符号求和。 |
| `product(expr, variable, lower, upper)` | 符号连乘。 |

```supercalc
diff(sin(x)*x^2, x)
integrate(x^2, x)
nintegrate(sin(x), x, 0, pi)
limit(sin(x)/x, x, 0)
series(exp(x), x, 0, 8)
summation(k, k, 1, n)
```

## 方程求解

| 函数 | 说明 |
|---|---|
| `solve(equation, variable[, domain])` | 求解方程并返回集合；默认复数域。 |

定义域可传 `real`、`complex`、`integer` 或 `positive`。

```supercalc
solve(x^2 = 9, x, real)
solve(x^2 + 1 = 0, x)
```

求解失败或结果需要额外条件时会给出诊断；未返回的解不能被自动假定不存在。

## 矩阵与向量

| 函数 | 说明 |
|---|---|
| `matrix(rows...)` | 由行向量构造矩阵。 |
| `identity(n)` | n 阶单位矩阵。 |
| `eye(n)` | `identity` 的别名。 |
| `det(matrix)` | 方阵行列式。 |
| `inv(matrix)` | 非奇异方阵的逆；奇异时返回错误。 |
| `rank(matrix)` | 矩阵秩。 |
| `transpose(matrix)` | 转置。 |
| `eigenvalues(matrix)` | 特征值向量，包含重数。 |
| `eigenvectors(matrix)` | 特征值、重数标签和特征向量。 |
| `lu(matrix)` | 返回下三角矩阵、上三角矩阵和置换矩阵。 |
| `qr(matrix)` | 返回正交矩阵和上三角矩阵。 |

```supercalc
A := [[1, 2], [3, 4]]
det(A)
inv(A)
eigenvalues(A)
matrix([1, 2], [3, 4])
identity(3)
```

## 定宽整数与位运算

| 函数 | 说明 |
|---|---|
| `fixed(value, width, signed)` | 通用定宽转换；位宽为 8、16、32、64，第三个参数为布尔值。 |
| `i8(x)` `i16(x)` `i32(x)` `i64(x)` | 有符号定宽整数。 |
| `u8(x)` `u16(x)` `u32(x)` `u64(x)` | 无符号定宽整数。 |
| `bitand(a, b)` | 按位与。 |
| `bitor(a, b)` | 按位或。 |
| `bitxor(a, b)` | 按位异或。 |
| `bitnot(a)` | 按位取反。 |
| `shl(a, n)` | 左移。 |
| `shr(a, n)` | 右移。 |
| `rotl(a, n)` | 循环左移；定宽整数按自身位宽旋转。 |
| `rotr(a, n)` | 循环右移。 |
| `popcount(a)` | 统计 1 的位数；有符号定宽值按其位模式统计。 |

```supercalc
i64(9223372036854775807) + 1
u8(0b10000001)
rotl(u8(0b10000001), 1)
popcount(i8(-1))
```

定宽溢出会回绕并显示 `SC3002` 警告，原始值和回绕值都保留在元数据中。

## 进制与数论

| 函数 | 说明 |
|---|---|
| `base(value, radix)` | 将整数转换为 2–36 进制文本。 |
| `hex(value)` | 十六进制文本。 |
| `bin(value)` | 二进制文本。 |
| `oct(value)` | 八进制文本。 |
| `gcd(a, b, ...)` | 最大公约数，可传多个参数。 |
| `lcm(a, b, ...)` | 最小公倍数，可传多个参数。 |
| `isprime(n)` | 判断质数。 |
| `nextprime(n)` | 返回下一个质数。 |
| `modpow(base, exponent, modulus)` | 模幂。 |
| `comb(n, k)` | 组合数。 |
| `binom(n, k)` | `comb` 的别名。 |

```supercalc
base(255, 16)
gcd(48, 18)
modpow(2, 10, 1000)
comb(10, 3)
```

## 编码与哈希

| 函数 | 说明 |
|---|---|
| `b64encode(text)` | 文本的 Base64 编码。 |
| `b64decode(text)` | Base64 解码为文本。 |
| `urlencode(text)` | URL 百分号编码。 |
| `urldecode(text)` | URL 解码。 |
| `hexencode(text)` | 文本 UTF-8 字节的十六进制。 |
| `hexdecode(text)` | 十六进制转回文本。 |
| `md5(text)` | MD5 摘要；不应用于安全认证。 |
| `sha1(text)` | SHA-1 摘要；不应用于新安全协议。 |
| `sha256(text)` | SHA-256 摘要。 |
| `sha512(text)` | SHA-512 摘要。 |

```supercalc
sha256("abc")
b64encode("超级计算器")
hexencode("A")
```

## 数据、正则与时间

| 函数 | 说明 |
|---|---|
| `json_parse(text)` | 解析结构化文本为可显示数据。 |
| `json_stringify(value)` | 将值序列化为结构化文本。 |
| `csv_parse(text)` | 解析逗号分隔数据并返回表格。 |
| `regex_test(pattern, text)` | 判断正则是否匹配；复杂表达式由计算超时保护。 |
| `timestamp()` | 当前 Unix 时间戳。 |
| `timestamp(text)` | 将 ISO 8601 时间转换为 Unix 时间戳。 |
| `datetime(timestamp)` | 将 Unix 时间戳转换为 UTC ISO 时间。 |

```supercalc
json_parse("[1, 2, 3]")
regex_test("^[A-Z]+$", "ABC")
datetime(0)
```

## 集合、范围与真值表

| 函数 | 说明 |
|---|---|
| `set(items...)` | 构造集合；单向量参数会展开。 |
| `range(start, end)` | 构造包含端点的整数范围。 |
| `len(value)` | 向量、集合、字符串或矩阵元素数。 |
| `truth_table("expression")` | 自动枚举表达式中的布尔变量并输出真值表。 |

```supercalc
truth_table("x and y")
range(1, 5)
len({1, 2, 3})
```

## 诊断与调试

| 函数 | 说明 |
|---|---|
| `ast(expr)` | 将参数表达式重新序列化为标准源码形式。 |
| `ast_dump(expr)` | 返回表达式对象的内部结构表示，用于开发调试。 |
| `random()` | 使用工作区随机种子生成 [0,1) 高精度近似值。 |
| `version()` | 返回程序版本和接口版本。 |

## 别名总表

- `convert` 等同于 `to`。
- `eye` 等同于 `identity`。
- `binom` 等同于 `comb`。

全部固定宽度类型：`i8`、`i16`、`i32`、`i64`、`u8`、`u16`、`u32`、`u64`。

