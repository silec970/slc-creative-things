# 0.1.0 测试报告

测试日期：2026-10-20  
平台：Windows 10.0.26300 x64  
Python：3.13.14  
Qt：PySide6 6.11.2

## 自动测试范围

- 精确有理数与十进制语义
- 近似模式警告、精度和舍入元数据
- 8/16/32/64 位定宽整数与溢出回绕
- IEEE 754 binary64 位域、NaN/Inf/次正规分类
- 表达式解析、源码区间和结构化错误
- 方程、导数、积分、极限、级数、假设、矩阵特征值
- 多进制、位运算、数论、编码、哈希、JSON 和数据工具
- 脚本递归、循环、断言、步数配额和逃逸尝试
- 单位与量纲转换
- LaTeX 子集导入、公式导出
- 2D 直角/极坐标采样
- 工作区保存/重开、历史/变量恢复、未来 schema 只读
- 本地插件哈希、路径越界和二进制文件拒绝
- CLI JSON envelope 和错误退出码
- PySide6 离屏启动、运行、近似徽标、公式预览、绘图和保存
- 计算进程异常时的本地兼容回退、单元错误不被误报为进程失败
- 绘图工具栏放大、缩小与复位，应用内界面说明文档
- 中文类型、舍入、算法、假设与计算状态显示
- 104 个可调用内建函数与帮助文档清单一致性
- 脚本编写指南的操作、作用域、循环、断言、模块和安全边界
- socket 拦截下的离线计算和保存

## 当前结果

```text
57 passed
Ruff: All checks passed
Mypy: Success: no issues found in 28 source files
```

完整 JUnit 结果在构建后写入 `artifacts/test-results.xml`。打包后的 CLI 精确计算和
无窗口 GUI 启动由 `scripts/build_windows.ps1` / `scripts/smoke_packaged.ps1` 验证。

## 打包验证

```text
GUI smoke: PASS
Native Windows GUI smoke: PASS (exit code 0, result 1/2)
GUI compatibility fallback smoke: PASS (result 1/2)
CLI smoke: 1/3 + 1/6 => 1/2 (exact)
Portable ZIP: dist/SuperCalc-0.1.0-win64.zip
The build script prints the SHA-256 of the final ZIP.
```

构建机未安装 Inno Setup，因此本次正式交付为可直接运行/解压运行的便携目录与 ZIP；
`packaging/SuperCalc.iss` 已提供，安装 Inno Setup 后可生成安装器。

