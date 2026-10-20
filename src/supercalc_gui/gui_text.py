from __future__ import annotations

TYPE_NAMES = {
    "Int": "整数",
    "Rational": "分数",
    "ComplexExact": "精确复数",
    "Symbolic": "符号表达式",
    "ApproxReal": "近似实数",
    "ApproxComplex": "近似复数",
    "FixedInt": "定宽整数",
    "Float64": "双精度浮点数",
    "Matrix": "矩阵",
    "Vector": "向量",
    "Set": "集合",
    "Bool": "布尔值",
    "String": "文本",
    "Function": "函数",
    "Table": "表格",
    "Quantity": "带单位数值",
    "Unit": "单位",
    "Equation": "方程",
    "Range": "范围",
    "Null": "空值",
}

ROUNDING_NAMES = {
    "half_even": "银行家舍入",
    "half_up": "半值向上舍入",
    "floor": "向下取整",
    "ceiling": "向上取整",
    "down": "向零舍入",
    "up": "远离零舍入",
}

ANGLE_NAMES = {
    "radians": "弧度",
    "degrees": "角度",
}

EXACTNESS_NAMES = {
    "exact": "精确",
    "approximate": "近似",
    "symbolic": "符号",
    "script": "脚本",
    "unknown": "未知",
}

ASSUMPTION_NAMES = {
    "real": "实数",
    "complex": "复数",
    "positive": "正数",
    "negative": "负数",
    "integer": "整数",
    "rational": "有理数",
    "irrational": "无理数",
    "nonzero": "非零",
    "zero": "零",
    "even": "偶数",
    "odd": "奇数",
    "finite": "有限",
    "infinite": "无限",
}

_ALGORITHM_REPLACEMENTS = (
    ("SymPy solve + 定义域过滤", "符号方程求解并过滤定义域"),
    ("SymPy 符号微分", "符号微分"),
    ("SymPy 符号积分", "符号积分"),
    ("SymPy 特征多项式与根", "特征多项式与特征根"),
    ("mpmath 自适应数值积分", "高精度自适应数值积分"),
    ("mpmath findroot", "高精度数值求根"),
    ("SymPy", "符号代数引擎"),
    ("mpmath", "高精度数值引擎"),
    ("findroot", "数值求根"),
    ("LU", "下上三角分解"),
    ("QR", "正交三角分解"),
)


def type_name(value: str) -> str:
    return TYPE_NAMES.get(value, value or "未知类型")


def rounding_name(value: str) -> str:
    return ROUNDING_NAMES.get(value, value or "未指定")


def angle_name(value: str) -> str:
    return ANGLE_NAMES.get(value, value or "未指定")


def exactness_name(value: str) -> str:
    return EXACTNESS_NAMES.get(value, value or "未知")


def assumption_name(value: str) -> str:
    return ASSUMPTION_NAMES.get(value, value)


def algorithm_name(value: str) -> str:
    if not value:
        return "未记录"
    text = value
    for source, target in _ALGORITHM_REPLACEMENTS:
        text = text.replace(source, target)
    return text


def assumptions_text(assumptions: dict[str, list[str]]) -> str:
    if not assumptions:
        return "无"
    return "；".join(
        f"{name}：{'、'.join(assumption_name(flag) for flag in flags)}"
        for name, flags in sorted(assumptions.items())
    )
