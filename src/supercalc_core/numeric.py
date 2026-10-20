from __future__ import annotations

import math
import struct
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any

import mpmath as mp
import sympy as sp

from .diagnostics import CalcError, Diagnostic, Span, warning
from .models import Value
from .units import UnitSpec, dimension_symbol, quantity_value

EXACT_NUMERIC_TYPES = {"Int", "Rational", "ComplexExact"}
NUMERIC_TYPES = EXACT_NUMERIC_TYPES | {"ApproxReal", "ApproxComplex", "FixedInt", "Float64"}


def precision_bits(digits: int) -> int:
    return max(53, int(math.ceil(max(2, digits) * math.log2(10))) + 8)


def format_fraction(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def format_mpf(value: mp.mpf, digits: int) -> str:
    if mp.isnan(value):
        return "nan"
    if mp.isinf(value):
        return "oo" if value > 0 else "-oo"
    with mp.workdps(max(8, digits)):
        text = mp.nstr(value, n=max(8, digits), strip_zeros=False)
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def int_value(value: int, display: str | None = None) -> Value:
    return Value("Int", int(value), True, display or str(value), str(value))


def rational_value(value: Fraction) -> Value:
    value = Fraction(value)
    if value.denominator == 1:
        return int_value(value.numerator)
    display = format_fraction(value)
    return Value(
        "Rational",
        value,
        True,
        display,
        rf"\frac{{{value.numerator}}}{{{value.denominator}}}",
    )


def approx_value(value: mp.mpf | complex, precision: int) -> Value:
    if isinstance(value, complex):
        real = mp.mpf(value.real)
        imag = mp.mpf(value.imag)
        display = f"{format_mpf(real, precision)} + {format_mpf(imag, precision)}i"
        return Value(
            "ApproxComplex",
            (str(real), str(imag)),
            False,
            display,
            "",
            {"precisionDigits": precision, "precisionBits": precision_bits(precision)},
        )
    value = mp.mpf(value)
    display = format_mpf(value, precision)
    return Value(
        "ApproxReal",
        str(value),
        False,
        display,
        "",
        {
            "precisionDigits": precision,
            "precisionBits": precision_bits(precision),
            "errorBoundUlp": 1,
        },
    )


def complex_exact_value(real: Fraction | int, imag: Fraction | int) -> Value:
    real_f = Fraction(real)
    imag_f = Fraction(imag)
    if imag_f == 0:
        return rational_value(real_f)
    if real_f == 0:
        if imag_f == 1:
            display = "i"
        elif imag_f == -1:
            display = "-i"
        else:
            display = f"{format_fraction(imag_f)}i"
    else:
        sign = "+" if imag_f >= 0 else "-"
        imag_text = format_fraction(abs(imag_f))
        display = f"{format_fraction(real_f)} {sign} {imag_text}i"
    return Value(
        "ComplexExact",
        (real_f, imag_f),
        True,
        display,
        sp.latex(
            sp.Rational(real_f.numerator, real_f.denominator)
            + sp.I * sp.Rational(imag_f.numerator, imag_f.denominator)
        ),
    )


def symbolic_value(expr: sp.Expr) -> Value:
    expr = sp.sympify(expr)
    if expr.is_Integer:
        return int_value(int(expr))
    if expr.is_Rational:
        rational = expr if isinstance(expr, sp.Rational) else sp.Rational(expr)
        return rational_value(Fraction(int(rational.p), int(rational.q)))
    display = str(expr).replace("**", "^")
    return Value("Symbolic", expr, True, display, sp.latex(expr), {"kind": "symbolic"})


def bool_value(value: bool) -> Value:
    return Value("Bool", bool(value), True, "true" if value else "false", str(value).lower())


def string_value(value: str) -> Value:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return Value("String", value, True, f'"{value}"', rf"\text{{{escaped}}}")


def null_value() -> Value:
    return Value("Null", None, True, "null", r"\mathrm{null}")


def parse_number_literal(
    raw: str,
    *,
    mode: str,
    precision: int,
    span: Span | None = None,
) -> tuple[Value, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    clean = raw.replace("_", "")
    lower = clean.lower()
    try:
        if lower.startswith(("0x", "0b", "0o")):
            return int_value(int(clean, 0)), diagnostics
        is_decimal = "." in clean or "e" in lower
        if not is_decimal:
            return int_value(int(clean, 10)), diagnostics
        if mode == "approx":
            with mp.workdps(precision):
                value = mp.mpf(clean)
            diagnostics.append(
                warning(
                    "SC3001",
                    "十进制字面量已转换为二进制近似值",
                    hint="如需精确十进制，请切换到精确模式或使用 1/10 这样的有理数写法。",
                    span=span,
                    category="precision",
                    snippet=raw,
                )
            )
            return approx_value(value, precision), diagnostics
        with localcontext() as context:
            context.prec = max(50, precision + 10)
            fraction = Fraction(Decimal(clean))
        return rational_value(fraction), diagnostics
    except (ValueError, ArithmeticError) as exc:
        raise CalcError(
            "SC1008",
            f"数字字面量“{raw}”无效：{exc}",
            hint="检查数字格式，例如 0xFF、0b1010、1.25 或 1e-3。",
            span=span,
            category="parse",
        ) from exc


def value_to_sympy(value: Value) -> sp.Expr:
    if value.type == "Int":
        return sp.Integer(int(value.data))
    if value.type == "Rational":
        value_fraction = Fraction(value.data)
        return sp.Rational(value_fraction.numerator, value_fraction.denominator)
    if value.type == "ComplexExact":
        real, imag = value.data
        return sp.Rational(
            Fraction(real).numerator, Fraction(real).denominator
        ) + sp.I * sp.Rational(Fraction(imag).numerator, Fraction(imag).denominator)
    if value.type == "Symbolic":
        return value.data
    if value.type in {"ApproxReal", "ApproxComplex"}:
        return sp.Float(value.display, max(15, value.meta.get("precisionDigits", 50)))
    if value.type == "Float64":
        return sp.Float(value.meta.get("hex", "0x0p+0"), 53)
    raise CalcError(
        "SC2101",
        f"{value.type} 不能作为符号表达式使用",
        hint="使用数值或显式转换为表达式。",
        category="type",
    )


def value_to_mpf(value: Value, precision: int) -> mp.mpf:
    if value.type == "Int":
        return mp.mpf(int(value.data))
    if value.type == "Rational":
        fraction = Fraction(value.data)
        return mp.mpf(fraction.numerator) / mp.mpf(fraction.denominator)
    if value.type == "ApproxReal":
        return mp.mpf(value.data)
    if value.type == "Float64":
        return mp.mpf(value.data)
    if value.type == "Symbolic" and value.data.is_number:
        numeric = sp.N(value.data, precision)
        try:
            real = float(numeric)
        except (TypeError, ValueError) as exc:
            raise CalcError(
                "SC2102", "符号表达式不是实数，不能转换为实数值", category="type"
            ) from exc
        return mp.mpf(real)
    if value.type in {"ComplexExact", "Symbolic", "ApproxComplex"}:
        raise CalcError(
            "SC2102",
            f"{value.type} 不能直接转换为实数近似值",
            hint="先使用 n(...) 或 approx(...) 明确转换。",
            category="type",
        )
    raise CalcError("SC2103", f"不支持从 {value.type} 转换为数值", category="type")


def _complex_parts(value: Value) -> tuple[Fraction, Fraction]:
    if value.type == "Int":
        return Fraction(int(value.data)), Fraction(0)
    if value.type == "Rational":
        return Fraction(value.data), Fraction(0)
    if value.type == "ComplexExact":
        return Fraction(value.data[0]), Fraction(value.data[1])
    raise CalcError("SC2104", "无法取得复数实部与虚部", category="type")


def _is_complex(value: Value) -> bool:
    return value.type == "ComplexExact" and Fraction(value.data[1]) != 0


def _exact_arithmetic(op: str, left: Value, right: Value) -> Value:
    if _is_complex(left) or _is_complex(right):
        ar, ai = _complex_parts(left)
        br, bi = _complex_parts(right)
        if op == "+":
            return complex_exact_value(ar + br, ai + bi)
        if op == "-":
            return complex_exact_value(ar - br, ai - bi)
        if op == "*":
            return complex_exact_value(ar * br - ai * bi, ar * bi + ai * br)
        if op == "/":
            denominator = br * br + bi * bi
            if denominator == 0:
                raise CalcError(
                    "SC2003",
                    "复数量除以零",
                    hint="除数不能为零。",
                    category="domain",
                )
            return complex_exact_value(
                (ar * br + ai * bi) / denominator,
                (ai * br - ar * bi) / denominator,
            )
        if op == "^":
            if br.denominator != 1:
                return symbolic_value(sp.Pow(value_to_sympy(left), value_to_sympy(right)))
            return complex_exact_value(*_complex_int_pow((ar, ai), int(br)))
    a = Fraction(int(left.data)) if left.type == "Int" else Fraction(left.data)
    b = Fraction(int(right.data)) if right.type == "Int" else Fraction(right.data)
    if op == "+":
        return rational_value(a + b)
    if op == "-":
        return rational_value(a - b)
    if op == "*":
        return rational_value(a * b)
    if op == "/":
        if b == 0:
            raise CalcError(
                "SC2003", "除数不能为零", hint="检查除法或分式分母。", category="domain"
            )
        return rational_value(a / b)
    if op == "%":
        if b == 0:
            raise CalcError("SC2004", "模运算的除数不能为零", category="domain")
        if a.denominator != 1 or b.denominator != 1:
            raise CalcError(
                "SC2105",
                "模运算要求整数操作数",
                hint="使用整数或先取整。",
                category="type",
            )
        return int_value(int(a) % int(b))
    if op == "^":
        if b.denominator != 1:
            return symbolic_value(sp.Pow(value_to_sympy(left), value_to_sympy(right)))
        exponent = int(b)
        if left.type in {"Int", "Rational"}:
            if exponent < 0 and a == 0:
                raise CalcError("SC2005", "零不能取负指数", category="domain")
            return rational_value(a**exponent)
        if exponent < 0 and a == 0:
            raise CalcError("SC2005", "零不能取负指数", category="domain")
        return complex_exact_value(*_complex_int_pow((a, Fraction(0)), exponent))
    raise CalcError("SC2106", f"不支持的精确运算 {op}", category="internal")


def _complex_int_pow(parts: tuple[Fraction, Fraction], exponent: int) -> tuple[Fraction, Fraction]:
    real, imag = parts
    if exponent < 0:
        denominator = real * real + imag * imag
        if denominator == 0:
            raise CalcError("SC2005", "零不能取负指数", category="domain")
        real, imag = real / denominator, -imag / denominator
        exponent = -exponent
    result_real, result_imag = Fraction(1), Fraction(0)
    base_real, base_imag = real, imag
    while exponent:
        if exponent & 1:
            result_real, result_imag = (
                result_real * base_real - result_imag * base_imag,
                result_real * base_imag + result_imag * base_real,
            )
        base_real, base_imag = (
            base_real * base_real - base_imag * base_imag,
            2 * base_real * base_imag,
        )
        exponent >>= 1
    return result_real, result_imag


def _fixed_spec(value: Value) -> tuple[int, bool, int]:
    if value.type != "FixedInt":
        raise CalcError("SC2107", "此处需要定宽整数", category="type")
    return int(value.meta["width"]), bool(value.meta["signed"]), int(value.data)


def make_fixed(
    value: int, width: int, signed: bool, *, overflow: bool = False, original: int | None = None
) -> Value:
    modulus = 1 << width
    raw = int(value) % modulus
    if signed and raw >= (1 << (width - 1)):
        wrapped = raw - modulus
        signed_min, signed_max = -(1 << (width - 1)), (1 << (width - 1)) - 1
        did_overflow = overflow or value < signed_min or value > signed_max
    else:
        wrapped = raw
        did_overflow = overflow or value < 0 or value >= modulus
    prefix = "i" if signed else "u"
    meta: dict[str, Any] = {
        "width": width,
        "signed": signed,
        "bits": format(raw, f"0{width}b"),
    }
    if did_overflow:
        meta["overflow"] = {
            "wrapped": wrapped,
            "original": original if original is not None else value,
            "width": width,
            "signed": signed,
        }
    return Value(
        "FixedInt",
        wrapped,
        True,
        f"{wrapped} ({prefix}{width})",
        str(wrapped),
        meta,
    )


def _fixed_arithmetic(op: str, left: Value, right: Value) -> Value:
    width, signed, a = _fixed_spec(left)
    rw, rs, b = _fixed_spec(right)
    if (width, signed) != (rw, rs):
        raise CalcError(
            "SC2108",
            f"定宽整数类型不一致：i{width} 与 i{rw}" if signed and rs else "定宽整数类型不一致",
            hint="先显式转换为相同宽度和符号性。",
            category="type",
        )
    if op == "+":
        return make_fixed(a + b, width, signed, original=a + b)
    if op == "-":
        return make_fixed(a - b, width, signed, original=a - b)
    if op == "*":
        return make_fixed(a * b, width, signed, original=a * b)
    if op == "/":
        if b == 0:
            raise CalcError("SC2003", "除数不能为零", category="domain")
        quotient = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            quotient = -quotient
        return make_fixed(quotient, width, signed, original=quotient)
    if op in {"&", "|", "xor", "^"}:
        raw_a, raw_b = a % (1 << width), b % (1 << width)
        if op == "&":
            raw = raw_a & raw_b
        elif op == "|":
            raw = raw_a | raw_b
        else:
            raw = raw_a ^ raw_b
        return make_fixed(raw, width, signed)
    if op in {"<<", ">>"}:
        if b < 0 or b >= width:
            raise CalcError(
                "SC2010",
                f"移位量 {b} 超出 0..{width - 1}",
                hint="定宽移位只在类型宽度内定义。",
                category="domain",
            )
        raw = (a % (1 << width)) << b if op == "<<" else (a % (1 << width)) >> b
        return make_fixed(raw, width, signed)
    raise CalcError("SC2109", f"不支持定宽整数运算 {op}", category="type")


def _approx_binary(op: str, left: Value, right: Value, precision: int) -> Value:
    with mp.workdps(precision):
        a = value_to_mpf(left, precision)
        b = value_to_mpf(right, precision)
        if op == "+":
            result = a + b
        elif op == "-":
            result = a - b
        elif op == "*":
            result = a * b
        elif op == "/":
            if b == 0:
                raise CalcError("SC2003", "除数不能为零", category="domain")
            result = a / b
        elif op == "^":
            result = mp.power(a, b)
        elif op == "%":
            if b == 0:
                raise CalcError("SC2004", "模运算的除数不能为零", category="domain")
            result = mp.fmod(a, b)
        else:
            raise CalcError("SC2110", f"不支持的近似运算 {op}", category="internal")
    return approx_value(result, precision)


def binary_arithmetic(
    op: str,
    left: Value,
    right: Value,
    *,
    precision: int,
) -> Value:
    if left.type in {"Unit", "Quantity"} or right.type in {"Unit", "Quantity"}:
        return _unit_arithmetic(op, left, right, precision=precision)
    if op in {"&&", "and"}:
        return bool_value(truthy(left) and truthy(right))
    if op in {"||", "or"}:
        return bool_value(truthy(left) or truthy(right))
    if op in {"==", "!=", "<", "<=", ">", ">="}:
        return compare_values(op, left, right, precision=precision)
    if left.type == "FixedInt" or right.type == "FixedInt":
        if left.type == "FixedInt" and right.type == "Int":
            width, signed, _ = _fixed_spec(left)
            right = make_fixed(int(right.data), width, signed)
        elif right.type == "FixedInt" and left.type == "Int":
            width, signed, _ = _fixed_spec(right)
            left = make_fixed(int(left.data), width, signed)
        return _fixed_arithmetic(op, left, right)
    if left.type == "String" and right.type == "String" and op == "+":
        return string_value(str(left.data) + str(right.data))
    if left.type in {"Vector", "Matrix"} or right.type in {"Vector", "Matrix"}:
        return _structured_arithmetic(op, left, right, precision=precision)
    if left.type in {"Set"} and right.type in {"Set"}:
        return _set_arithmetic(op, left, right, precision=precision)
    if left.type in NUMERIC_TYPES and right.type in NUMERIC_TYPES:
        if left.type in EXACT_NUMERIC_TYPES and right.type in EXACT_NUMERIC_TYPES:
            return _exact_arithmetic(op, left, right)
        if left.type == "Float64" or right.type == "Float64":
            a = float(value_to_sympy(left))
            b = float(value_to_sympy(right))
            result = _python_float_op(op, a, b)
            return float64_value(result)
        return _approx_binary(op, left, right, precision)
    if left.type == "Symbolic" or right.type == "Symbolic" or op in {"^"}:
        try:
            a = value_to_sympy(left)
            b = value_to_sympy(right)
            expr = {
                "+": lambda: a + b,
                "-": lambda: a - b,
                "*": lambda: a * b,
                "/": lambda: a / b,
                "^": lambda: sp.Pow(a, b),
                "%": lambda: sp.Mod(a, b),
            }.get(op)
            if op == "/" and b == 0:
                raise CalcError("SC2003", "除数不能为零", category="domain")
            if expr is None:
                raise CalcError("SC2111", f"不支持的符号运算 {op}", category="type")
            return symbolic_value(expr())
        except CalcError:
            raise
        except Exception as exc:
            raise CalcError(
                "SC2112",
                f"符号运算失败：{exc}",
                hint="检查表达式类型和定义域。",
                category="symbolic",
            ) from exc
    raise CalcError(
        "SC2113",
        f"类型 {left.type} 与 {right.type} 不能进行 {op} 运算",
        hint="先显式转换类型，或检查是否混用了数值与字符串。",
        category="type",
    )


def _quantity_parts(value: Value) -> tuple[Value, UnitSpec]:
    if value.type == "Unit":
        return int_value(1), value.data
    if value.type == "Quantity":
        magnitude, spec = value.data
        return magnitude, spec
    raise CalcError("SC2140", f"{value.type} 不是带单位的值", category="type")


def _unit_arithmetic(op: str, left: Value, right: Value, *, precision: int) -> Value:
    left_is_unit = left.type in {"Unit", "Quantity"}
    right_is_unit = right.type in {"Unit", "Quantity"}
    if op == "^" and left.type == "Unit" and right.type == "Int":
        exponent = int(right.data)
        _magnitude, spec = _quantity_parts(left)
        dimension = tuple(item * exponent for item in spec.dimension)
        return unit_value_from_spec(
            UnitSpec(
                f"{spec.symbol}^{exponent}",
                f"{spec.name}^{exponent}",
                _dimension(dimension),
                spec.factor**exponent,
            )
        )
    if op in {"+", "-"}:
        if not (left.type == "Quantity" and right.type == "Quantity"):
            raise CalcError(
                "SC2141",
                "带单位加减需要两个相同维度的量",
                hint="例如 3 m + 20 cm；单位符号本身不能与数相加。",
                category="type",
            )
        left_mag, left_spec = _quantity_parts(left)
        right_mag, right_spec = _quantity_parts(right)
        if left_spec.dimension != right_spec.dimension:
            raise CalcError(
                "SC2142",
                f"单位维度不匹配：{dimension_symbol(left_spec.dimension)} 与 {dimension_symbol(right_spec.dimension)}",
                hint="先把右侧转换或改写成相同维度。",
                category="type",
            )
        ratio = right_spec.factor / left_spec.factor
        converted = binary_arithmetic("*", right_mag, rational_value(ratio), precision=precision)
        magnitude = binary_arithmetic(op, left_mag, converted, precision=precision)
        return quantity_value(magnitude, left_spec)
    if op == "*":
        if left_is_unit and right_is_unit:
            left_mag, left_spec = _quantity_parts(left)
            right_mag, right_spec = _quantity_parts(right)
            magnitude = binary_arithmetic("*", left_mag, right_mag, precision=precision)
            symbol = f"{left_spec.symbol}*{right_spec.symbol}"
            spec = UnitSpec(
                symbol,
                symbol,
                _dimension(
                    tuple(
                        a + b
                        for a, b in zip(left_spec.dimension, right_spec.dimension, strict=True)
                    )
                ),
                left_spec.factor * right_spec.factor,
            )
            return quantity_value(magnitude, spec)
        quantity_side = left if left_is_unit else right
        scalar_side = right if left_is_unit else left
        if scalar_side.type not in NUMERIC_TYPES:
            raise CalcError("SC2143", "单位只能与数值相乘", category="type")
        magnitude, spec = _quantity_parts(quantity_side)
        return quantity_value(
            binary_arithmetic("*", magnitude, scalar_side, precision=precision), spec
        )
    if op == "/":
        if right.type == "Unit" and left.type in NUMERIC_TYPES:
            denominator, right_spec = _quantity_parts(right)
            inverse = UnitSpec(
                f"1/{right_spec.symbol}",
                f"每{right_spec.name}",
                _dimension(tuple(-item for item in right_spec.dimension)),
                Fraction(1) / right_spec.factor,
            )
            return quantity_value(
                binary_arithmetic("/", left, denominator, precision=precision),
                inverse,
            )
        if left.type == "Unit" and right.type == "Unit":
            left_mag, left_spec = _quantity_parts(left)
            right_mag, right_spec = _quantity_parts(right)
            dimension = tuple(
                a - b for a, b in zip(left_spec.dimension, right_spec.dimension, strict=True)
            )
            symbol = f"{left_spec.symbol}/{right_spec.symbol}"
            spec = UnitSpec(
                symbol, symbol, _dimension(dimension), left_spec.factor / right_spec.factor
            )
            return quantity_value(
                binary_arithmetic("/", left_mag, right_mag, precision=precision),
                spec,
            )
        if left.type == "Quantity" and right.type in NUMERIC_TYPES:
            magnitude, spec = _quantity_parts(left)
            return quantity_value(
                binary_arithmetic("/", magnitude, right, precision=precision),
                spec,
            )
        if left.type == "Quantity" and right.type == "Quantity":
            left_mag, left_spec = _quantity_parts(left)
            right_mag, right_spec = _quantity_parts(right)
            dimension = tuple(
                a - b for a, b in zip(left_spec.dimension, right_spec.dimension, strict=True)
            )
            symbol = f"{left_spec.symbol}/{right_spec.symbol}"
            spec = UnitSpec(
                symbol, symbol, _dimension(dimension), left_spec.factor / right_spec.factor
            )
            return quantity_value(
                binary_arithmetic("/", left_mag, right_mag, precision=precision),
                spec,
            )
        if left.type == "Quantity" and right.type == "Unit":
            left_mag, left_spec = _quantity_parts(left)
            right_mag, right_spec = _quantity_parts(right)
            dimension = tuple(
                a - b for a, b in zip(left_spec.dimension, right_spec.dimension, strict=True)
            )
            symbol = f"{left_spec.symbol}/{right_spec.symbol}"
            spec = UnitSpec(
                symbol, symbol, _dimension(dimension), left_spec.factor / right_spec.factor
            )
            return quantity_value(
                binary_arithmetic("/", left_mag, right_mag, precision=precision),
                spec,
            )
    if op in {"==", "!=", "<", "<=", ">", ">="} and left.type == right.type == "Quantity":
        left_mag, left_spec = _quantity_parts(left)
        right_mag, right_spec = _quantity_parts(right)
        if left_spec.dimension != right_spec.dimension:
            return bool_value(op == "!=")
        ratio = right_spec.factor / left_spec.factor
        converted = binary_arithmetic("*", right_mag, rational_value(ratio), precision=precision)
        return compare_values(op, left_mag, converted, precision=precision)
    raise CalcError(
        "SC2144",
        f"单位不支持运算 {op}",
        hint="支持同维度加减、乘除和显式单位转换。",
        category="type",
    )


def _dimension(values: tuple[int, ...]) -> tuple[int, int, int, int, int, int, int]:
    padded = (*values, 0, 0, 0, 0, 0, 0, 0)
    return padded[0], padded[1], padded[2], padded[3], padded[4], padded[5], padded[6]


def convert_quantity(value: Value, target: Value, *, precision: int) -> Value:
    if value.type != "Quantity" or target.type != "Unit":
        raise CalcError("SC2145", "转换需要带单位的量和目标单位", category="type")
    magnitude, source_spec = _quantity_parts(value)
    target_spec: UnitSpec = target.data
    if source_spec.dimension != target_spec.dimension:
        raise CalcError(
            "SC2146",
            f"不能把 {dimension_symbol(source_spec.dimension)} 转换为 {dimension_symbol(target_spec.dimension)}",
            category="domain",
        )
    ratio = source_spec.factor / target_spec.factor
    converted = binary_arithmetic("*", magnitude, rational_value(ratio), precision=precision)
    return quantity_value(converted, target_spec)


def unit_value_from_spec(spec: UnitSpec) -> Value:
    from .units import unit_value as make_unit

    if spec.symbol in {
        "m",
        "s",
        "kg",
        "A",
        "K",
        "mol",
        "cd",
        "N",
        "J",
        "W",
        "Pa",
        "Hz",
        "km",
        "cm",
        "mm",
        "ms",
        "min",
        "h",
        "g",
    }:
        return make_unit(spec.symbol)
    return Value(
        "Unit",
        spec,
        True,
        spec.symbol,
        rf"\mathrm{{{spec.symbol}}}",
        {"dimension": list(spec.dimension), "name": spec.name},
    )


def _python_float_op(op: str, a: float, b: float) -> float:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise CalcError("SC2003", "除数不能为零", category="domain")
        return a / b
    if op == "^":
        return a**b
    if op == "%":
        return a % b
    raise CalcError("SC2114", f"不支持的二进制浮点运算 {op}", category="type")


def _structured_arithmetic(op: str, left: Value, right: Value, *, precision: int) -> Value:
    if op not in {"+", "-", "*"}:
        raise CalcError(
            "SC2115",
            f"矩阵/向量不支持 {op} 运算",
            hint="矩阵乘法使用 *；逐元素运算将在后续版本提供。",
            category="type",
        )
    if left.type == "Matrix" and right.type == "Matrix":
        if op in {"+", "-"}:
            _require_same_shape(left, right)
            rows = [
                [
                    binary_arithmetic(op, a, b, precision=precision)
                    for a, b in zip(left_row, right_row, strict=True)
                ]
                for left_row, right_row in zip(left.data, right.data, strict=True)
            ]
            return matrix_value(rows)
        if op == "*":
            if len(left.data[0]) != len(right.data):
                raise CalcError(
                    "SC2116",
                    "矩阵维度不匹配",
                    hint=f"左矩阵列数 {len(left.data[0])} 必须等于右矩阵行数 {len(right.data)}。",
                    category="type",
                )
            result = []
            for row in left.data:
                result_row = []
                for col_index in range(len(right.data[0])):
                    total = int_value(0)
                    for k, cell in enumerate(row):
                        total = binary_arithmetic(
                            "+",
                            total,
                            binary_arithmetic(
                                "*", cell, right.data[k][col_index], precision=precision
                            ),
                            precision=precision,
                        )
                    result_row.append(total)
                result.append(result_row)
            return matrix_value(result)
    if left.type == "Vector" and right.type == "Vector":
        if len(left.data) != len(right.data):
            raise CalcError("SC2117", "向量长度不一致", category="type")
        if op == "*":
            total = int_value(0)
            for a, b in zip(left.data, right.data, strict=True):
                total = binary_arithmetic(
                    "+",
                    total,
                    binary_arithmetic("*", a, b, precision=precision),
                    precision=precision,
                )
            return total
        return Value(
            "Vector",
            [
                binary_arithmetic(op, a, b, precision=precision)
                for a, b in zip(left.data, right.data, strict=True)
            ],
            True,
        )
    structured = left if left.type in {"Vector", "Matrix"} else right
    scalar = right if structured is left else left
    if scalar.type in {"Vector", "Matrix"}:
        raise CalcError("SC2118", "两个结构类型不能进行该运算", category="type")
    if structured.type == "Vector":
        vector_data = [
            binary_arithmetic(op, item, scalar, precision=precision) for item in structured.data
        ]
        return Value(
            "Vector",
            vector_data,
            all(v.exact for v in vector_data),
            "[" + ", ".join(v.display for v in vector_data) + "]",
        )
    matrix_data = [
        [binary_arithmetic(op, item, scalar, precision=precision) for item in row]
        for row in structured.data
    ]
    return matrix_value(matrix_data)


def _require_same_shape(left: Value, right: Value) -> None:
    left_shape = (len(left.data), len(left.data[0]) if left.data else 0)
    right_shape = (len(right.data), len(right.data[0]) if right.data else 0)
    if left_shape != right_shape:
        raise CalcError(
            "SC2119",
            f"矩阵形状不一致：{left_shape} 与 {right_shape}",
            category="type",
        )


def _set_arithmetic(op: str, left: Value, right: Value, *, precision: int) -> Value:
    right_keys = {value_sort_key(item) for item in right.data}
    combined = left.data + right.data
    if op == "|":
        chosen = combined
    elif op == "&":
        chosen = [value for value in combined if value_sort_key(value) in right_keys]
        chosen = list({value_sort_key(value): value for value in chosen}.values())
    elif op == "-":
        chosen = [value for value in left.data if value_sort_key(value) not in right_keys]
    else:
        raise CalcError("SC2120", f"集合不支持 {op} 运算", category="type")
    unique = list({value_sort_key(value): value for value in chosen}.values())
    return set_value(unique)


def value_sort_key(value: Value) -> str:
    return f"{value.type}:{value.display}"


def compare_values(op: str, left: Value, right: Value, *, precision: int) -> Value:
    a: Any
    b: Any
    if left.type == "String" and right.type == "String":
        a, b = str(left.data), str(right.data)
    elif left.type in NUMERIC_TYPES and right.type in NUMERIC_TYPES:
        if left.type in EXACT_NUMERIC_TYPES and right.type in EXACT_NUMERIC_TYPES:
            a_fraction, a_imag = _complex_parts(left)
            b_fraction, b_imag = _complex_parts(right)
            if a_imag != 0 or b_imag != 0:
                raise CalcError("SC2121", "复数不能进行大小比较", category="type")
            a, b = a_fraction, b_fraction
        else:
            with mp.workdps(precision):
                a, b = value_to_mpf(left, precision), value_to_mpf(right, precision)
    else:
        if left.type == "Bool" and right.type == "Bool":
            a, b = bool(left.data), bool(right.data)
        else:
            a, b = value_to_sympy(left), value_to_sympy(right)
    if op == "==":
        return bool_value(sp.simplify(a - b) == 0 if isinstance(a, sp.Expr) else a == b)
    if op == "!=":
        return bool_value(not bool(compare_values("==", left, right, precision=precision).data))
    return bool_value({"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op])


def unary_arithmetic(op: str, value: Value, *, precision: int) -> Value:
    if op == "+":
        return value
    if op == "-":
        if value.type == "Int":
            return int_value(-int(value.data))
        if value.type == "Rational":
            return rational_value(-Fraction(value.data))
        if value.type == "ComplexExact":
            return complex_exact_value(-value.data[0], -value.data[1])
        if value.type == "ApproxReal":
            return approx_value(-mp.mpf(value.data), precision)
        if value.type == "Symbolic":
            return symbolic_value(-value.data)
        if value.type == "FixedInt":
            width, signed, raw = _fixed_spec(value)
            if not signed and raw:
                raise CalcError("SC2122", "无符号定宽整数不能取负", category="domain")
            return make_fixed(-raw, width, signed, original=-raw)
    if op == "~":
        if value.type == "FixedInt":
            width, signed, raw = _fixed_spec(value)
            return make_fixed(~(raw % (1 << width)), width, signed)
        if value.type == "Int":
            return int_value(~int(value.data))
        raise CalcError("SC2123", "位取反需要整数", category="type")
    if op == "not":
        return bool_value(not truthy(value))
    raise CalcError("SC2124", f"不支持一元运算 {op}", category="type")


def truthy(value: Value) -> bool:
    if value.type == "Bool":
        return bool(value.data)
    if value.type in NUMERIC_TYPES:
        return not (
            (value.type == "Int" and int(value.data) == 0)
            or (value.type == "Rational" and Fraction(value.data) == 0)
            or (value.type == "ApproxReal" and mp.mpf(value.data) == 0)
        )
    if value.type == "Null":
        return False
    return True


def vector_value(items: list[Value]) -> Value:
    return Value(
        "Vector",
        items,
        all(v.exact for v in items),
        "[" + ", ".join(v.display for v in items) + "]",
        r"\begin{bmatrix}" + r" \\ ".join(v.latex for v in items) + r"\end{bmatrix}",
    )


def matrix_value(rows: list[list[Value]]) -> Value:
    if not rows:
        raise CalcError("SC2125", "矩阵不能为空", category="type")
    width = len(rows[0])
    if width == 0 or any(len(row) != width for row in rows):
        raise CalcError(
            "SC2126",
            "矩阵每一行的列数必须相同",
            hint="例如 [[1, 2], [3, 4]]。",
            category="type",
        )
    exact = all(v.exact for row in rows for v in row)
    display = "[" + ", ".join("[" + ", ".join(v.display for v in row) + "]" for row in rows) + "]"
    latex_rows = " \\\\ ".join(" & ".join(v.latex for v in row) for row in rows)
    return Value(
        "Matrix",
        rows,
        exact,
        display,
        rf"\begin{{bmatrix}}{latex_rows}\end{{bmatrix}}",
        {"rows": len(rows), "columns": width},
    )


def set_value(items: list[Value]) -> Value:
    items = list({value_sort_key(v): v for v in items}.values())
    return Value(
        "Set",
        items,
        all(v.exact for v in items),
        "{" + ", ".join(v.display for v in items) + "}",
    )


def float64_value(value: float) -> Value:
    bits = struct.unpack(">Q", struct.pack(">d", value))[0]
    sign = (bits >> 63) & 1
    exponent = (bits >> 52) & 0x7FF
    mantissa = bits & ((1 << 52) - 1)
    classification = "finite"
    if exponent == 0:
        classification = "zero" if mantissa == 0 else "subnormal"
    elif exponent == 0x7FF:
        classification = "nan" if mantissa else "infinity"
    return Value(
        "Float64",
        float(value),
        False,
        repr(float(value)),
        "",
        {
            "bits": f"{bits:064b}",
            "hex": f"0x{bits:016x}",
            "sign": sign,
            "exponent": exponent,
            "mantissa": mantissa,
            "classification": classification,
        },
    )


def inspect_float64(value: Value) -> dict[str, Any]:
    if value.type != "Float64":
        value = float64_value(float(value_to_sympy(value)))
    bits = int(value.meta["hex"], 16)
    sign = (bits >> 63) & 1
    exponent_bits = (bits >> 52) & 0x7FF
    mantissa = bits & ((1 << 52) - 1)
    classification = value.meta.get("classification", "finite")
    if exponent_bits == 0:
        exponent = -1022
        significand = mantissa / (1 << 52)
    elif exponent_bits == 0x7FF:
        exponent = None
        significand = None
    else:
        exponent = exponent_bits - 1023
        significand = 1 + mantissa / (1 << 52)
    return {
        "value": value.data,
        "hex": value.meta["hex"],
        "binary": f"{bits:064b}",
        "sign": sign,
        "exponentBits": exponent_bits,
        "exponent": exponent,
        "mantissaBits": mantissa,
        "mantissaHex": f"0x{mantissa:013x}",
        "significand": significand,
        "classification": classification,
    }


def bits_from_float(value: Value) -> Value:
    data = inspect_float64(value)
    lines = [
        f"值: {data['value']!r}",
        f"分类: {data['classification']}",
        f"符号位: {data['sign']}",
        f"指数位: {data['exponentBits']:011b} ({data['exponentBits']})",
        f"尾数位: {data['mantissaBits']:052b}",
        f"十六进制: {data['hex']}",
    ]
    return Value(
        "String",
        "\n".join(lines),
        True,
        "\n".join(lines),
        "",
        {"ieee754": data},
    )


def value_to_python(value: Value) -> Any:
    if value.type == "Int":
        return int(value.data)
    if value.type == "Rational":
        return float(Fraction(value.data))
    if value.type == "ApproxReal":
        return float(mp.mpf(value.data))
    if value.type in {"ApproxComplex", "ComplexExact"}:
        real, imag = (
            (float(value.data[0]), float(value.data[1]))
            if value.type == "ApproxComplex"
            else (float(value.data[0]), float(value.data[1]))
        )
        return complex(real, imag)
    if value.type == "Float64":
        return float(value.data)
    if value.type == "Bool":
        return bool(value.data)
    if value.type == "String":
        return str(value.data)
    if value.type in {"Vector", "Set"}:
        return [value_to_python(v) for v in value.data]
    if value.type == "Matrix":
        return [[value_to_python(v) for v in row] for row in value.data]
    if value.type == "Symbolic":
        return complex(value.data.evalf()) if value.data.is_number else str(value.data)
    if value.type == "Null":
        return None
    return value.data


def value_from_python(value: Any, precision: int = 50) -> Value:
    if value is None:
        return null_value()
    if isinstance(value, bool):
        return bool_value(value)
    if isinstance(value, int):
        return int_value(value)
    if isinstance(value, Fraction):
        return rational_value(value)
    if isinstance(value, sp.Expr):
        return symbolic_value(value)
    if isinstance(value, str):
        return string_value(value)
    if isinstance(value, complex):
        if value.imag == 0:
            return approx_value(mp.mpf(value.real), precision)
        return approx_value(value, precision)
    if isinstance(value, float):
        return approx_value(mp.mpf(value), precision)
    if isinstance(value, (list, tuple, set)):
        items = [value_from_python(item, precision) for item in value]
        if items and all(item.type == "Vector" for item in items):
            return matrix_value([item.data for item in items])
        return vector_value(items)
    if isinstance(value, dict):
        return Value(
            "String",
            str(value),
            True,
            str(value),
            "",
            {"pythonValue": value},
        )
    return string_value(str(value))
