# `.scws` 工作区格式

工作区是 UTF-8 JSON 单文件。扩展名为 `.scws`，但内部仍是可审阅的 JSON。

```json
{
  "schemaVersion": 1,
  "appVersion": "0.1.0",
  "workspaceId": "uuid",
  "title": "示例",
  "createdAt": "2026-10-20T00:00:00+00:00",
  "updatedAt": "2026-10-20T00:00:00+00:00",
  "settings": {
    "mode": "exact",
    "precision": 50,
    "rounding": "half_even",
    "angle": "radians",
    "randomSeed": 0,
    "showSteps": true
  },
  "cells": [
    {
      "id": "uuid",
      "kind": "math",
      "source": "x := 1/3",
      "tags": [],
      "plot": {},
      "collapsed": false
    }
  ],
  "history": [],
  "snapshot": {}
}
```

单元类型为 `math`、`script`、`markdown`、`plot`。公式源码是唯一真源；WYSIWYG
控件只投影和编辑该源码。绘图单元在 `plot` 中保存完整方程、范围、采样数和
直角/隐式/极坐标类型。旧版包含 `expression` 和 `variable` 的绘图单元仍可自动迁移。

打开工作区时，核心按记录顺序重放单元，恢复变量、函数、假设和历史；`snapshot`
保存上一次运行环境，供检查与诊断。

## 兼容与恢复

- 当前 `schemaVersion` 为 1。
- 旧版本通过迁移链升级；新版本文件在旧应用中以只读方式打开，拒绝覆盖保存。
- 损坏 JSON 返回带行列号的错误，原文件保持不变。
- 保存先写同目录临时文件，执行 `fsync`，再原子替换；旧文件保留为 `.bak`。
- 编辑时每 5 秒写 `%APPDATA%\SuperCalc\recovery\<workspaceId>.autosave.scws`。
- 最近文件保存在 `%APPDATA%\SuperCalc\recent.json`。
- 设置 `SUPERCALC_DATA_DIR` 可重定向应用数据目录。

插件引用保存在 `plugins` 扩展字段中，包含路径、版本、权限和 SHA-256。打开时若哈希
改变，必须重新确认权限。

