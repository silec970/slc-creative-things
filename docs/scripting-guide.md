# 脚本编写指南

超级计算器脚本使用专用数学脚本语言，不是 Python，也不是通用操作系统脚本。它适合
可复现计算、循环、递归、断言和工作区测试。脚本在受限解释器中运行，不提供文件、
网络、进程、反射或宿主语言对象。

## 一、脚本单元

1. 在笔记本中点击“+ 脚本”添加脚本单元。
2. 输入脚本，点击“运行”或按控制键加回车。
3. 运行全部时，脚本按单元顺序执行，定义的变量和函数会留给后续单元。
4. 断言失败会显示失败信息和源码位置，并使该脚本单元标记为失败。

CLI 可直接测试脚本文件：

```powershell
SuperCalcCLI.exe test examples/assertions.scscript
```

## 二、基本语法

### 注释

```supercalc
# 整行注释
x := 1  # 行尾注释
// 另一种注释形式
```

### 赋值

```supercalc
x := 1/3
name := "超级计算器"
```

赋值使用 `:=`。单个 `=` 表示方程，例如 `x = 3`，不能在脚本中当作赋值。

### 表达式语句

```supercalc
1/3 + 1/6
diff(sin(x), x)
```

表达式可以单独成行；脚本单元最终显示执行状态和断言数量，变量面板显示持久变量。

## 三、函数

### 表达式函数

```supercalc
square(x) := x^2
factorial(n) := n <= 1 ? 1 : n * factorial(n - 1)
```

表达式函数适合纯公式和递归。函数参数只在函数调用内有效。

### 块函数

```supercalc
fn square_sum(n) {
    total := 0
    for k in 1..n {
        total := total + k^2
    }
    return total
}
```

块函数适合循环、条件分支和显式 `return`。

### 调用

```supercalc
square(5)
factorial(10)
square_sum(20)
```

函数调用参数数量不匹配会返回类型诊断。递归默认最多 128 层。

## 四、条件

```supercalc
fn absolute_value(x) {
    if x < 0 {
        return -x
    } else {
        return x
    }
}
```

条件表达式也可以使用三元形式：

```supercalc
label := x >= 0 ? "非负" : "负数"
```

条件必须求值为布尔值或可明确判定的数值零/非零；类型不清时会产生诊断。

## 五、循环

### 范围循环

```supercalc
total := 0
for k in 1..100 {
    total := total + k
}
assert total == 5050
```

`1..100` 包含起点和终点。起点大于终点时按倒序迭代。

### 向量和集合循环

```supercalc
for value in [1, 4, 9, 16] {
    assert value >= 0
}
```

### 条件循环

```supercalc
n := 1
while n < 100 {
    n := n * 2
}
assert n == 128
```

脚本支持循环，但当前没有 `break` 和 `continue`。需要提前退出时应改写条件，或把循环
放入函数并通过 `return` 返回。

## 六、断言

```supercalc
assert 1/3 + 1/6 == 1/2
assert square_sum(10) == 385 : "平方和计算结果不正确"
```

- 断言条件必须能被确定为真，否则失败。
- 冒号后的文本是失败说明，可选。
- 断言失败不会静默跳过，会使脚本失败并返回 `SC6001`。
- 工作区测试会统计脚本断言数量。

## 七、作用域与持久化

- 顶层赋值的变量在当前引擎环境中持久存在。
- 函数参数和块内局部变量不自动泄漏为全局变量。
- 函数可以访问调用者环境中的已有变量；显式参数更利于复现。
- 递归调用使用独立局部参数表。
- 工作区重新打开时会按单元顺序重放脚本，恢复变量和函数。

## 八、设置计算环境

脚本中可以使用设置语句：

```supercalc
set precision 80
set mode exact
set rounding half_even
set angle radians
set seed 42
```

这些设置影响后续计算并写入工作区环境。需要近似结果时，可显式使用 `n(...)` 或
`approx(...)`，比整体切换模式更清晰。

## 九、模块与插件

在已确认权限的本地插件目录中，可加载同目录的 `.scscript` 模块：

```supercalc
use "helpers.scscript"
```

规则：

- 只能使用本地插件目录内的相对路径。
- 禁止绝对路径和 `..` 越界。
- 模块只允许 `.scscript`。
- 同一路径在一次引擎会话中只执行一次。
- 模块中的函数定义可在后续脚本中调用。

普通工作区脚本不能任意读取本地文件；这是有意设计的安全边界。

## 十、可用函数与运算符

脚本可直接使用全部内置数学函数，包括：

- 微积分与代数：`simplify`、`expand`、`factor`、`diff`、`integrate`、`solve`
- 矩阵：`matrix`、`det`、`inv`、`eigenvalues`、`qr`
- 程序员工具：`i64`、`bitand`、`rotl`、`popcount`、`base`、`modpow`
- 编码与数据：`sha256`、`b64encode`、`json_parse`、`csv_parse`
- 集合与调试：`set`、`range`、`len`、`truth_table`

完整清单和示例见“帮助 → 内置函数参考”。

运算符：

- 算术：`+`、`-`、`*`、`/`、`%`、`^`
- 比较：`==`、`!=`、`<`、`<=`、`>`、`>=`
- 逻辑：`&&`、`||`、`not`
- 位运算：`&`、`|`、`xor`、`~`、`<<`、`>>`
- 条件：`condition ? true_value : false_value`
- 范围：`start..end`

## 十一、可复现脚本模式

### 阶乘与断言

```supercalc
factorial(n) := n <= 1 ? 1 : n * factorial(n - 1)
assert factorial(20) == 2432902008176640000 : "阶乘错误"
```

### 迭代平方和

```supercalc
fn square_sum(n) {
    total := 0
    for k in 1..n {
        total := total + k^2
    }
    return total
}
assert square_sum(100) == 338350
```

### 牛顿迭代

```supercalc
fn newton_root(a) {
    x := a / 2
    for k in 1..20 {
        x := (x + a / x) / 2
    }
    return x
}
assert abs(newton_root(2)^2 - 2) < 10^(-12)
```

### 素数检查

```supercalc
for n in 2..50 {
    result := isprime(n) ? 1 : 0
    assert result == 0 || result == 1
}
```

## 十二、安全限制

- 默认最大执行步数：1000000。
- 默认最大递归深度：128。
- 长脚本会接受运行时间检查，默认阈值约 30 秒。
- 不提供 Python 导入、文件读写、网络、进程或环境变量接口。
- 插件权限在加载时显示并要求确认。
- 计算进程可被“取消计算”终止。

## 十三、调试建议

1. 点击单元顶部的“语法树”确认解析结构。
2. 把复杂脚本拆成多个小函数和断言。
3. 优先使用精确分数，避免无意引入近似标记。
4. 检查右侧“诊断”中的源码行列号和修复建议。
5. 用 CLI 测试脚本，便于纳入持续测试。

示例文件：

- `examples/assertions.scscript`
- `examples/acceptance.scws`
- `examples/plugins/sequence_tools/main.scscript`

