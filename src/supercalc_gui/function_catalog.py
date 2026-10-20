from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class FunctionTemplate:
    name: str
    description: str
    insert_text: str
    caret_from_end: int


def _entry(
    name: str,
    description: str,
    args: str = "",
    display: str | None = None,
) -> FunctionTemplate:
    return FunctionTemplate(
        name=display or name,
        description=description,
        insert_text=f"{name}({args})",
        caret_from_end=len(args) + 1,
    )


FUNCTION_GROUPS: list[tuple[str, list[FunctionTemplate]]] = [
    (
        "数值与精度",
        [
            _entry("approx", "转换为当前精度近似值"),
            _entry("n", "指定有效位数进行数值化", " , 50"),
            _entry("f64", "转换为双精度浮点数"),
            _entry("ieee64", "查看双精度位域"),
            _entry("bits", "显示符号、指数和尾数"),
            _entry("to", "带单位数值转换", " , m"),
            _entry("convert", "单位转换别名", " , m", "convert（to）"),
            _entry("round", "按小数位舍入", " , 2"),
            _entry("floor", "向下取整"),
            _entry("ceil", "向上取整"),
            _entry("abs", "绝对值"),
            _entry("sign", "正负号"),
            _entry("gamma", "伽马函数"),
        ],
    ),
    (
        "基础数学",
        [
            _entry("sqrt", "平方根"),
            _entry("cbrt", "实数立方根"),
            _entry("sin", "正弦"),
            _entry("cos", "余弦"),
            _entry("tan", "正切"),
            _entry("asin", "反正弦"),
            _entry("acos", "反余弦"),
            _entry("atan", "反正切"),
            _entry("ln", "自然对数"),
            _entry("log", "对数，可指定底数", " , 10"),
            _entry("exp", "指数函数"),
            _entry("factorial", "阶乘"),
        ],
    ),
    (
        "代数、方程与微积分",
        [
            _entry("simplify", "符号化简"),
            _entry("expand", "展开表达式"),
            _entry("factor", "因式分解"),
            _entry("together", "通分合并"),
            _entry("apart", "部分分式分解", " , x"),
            _entry("assume", "添加变量假设", " , real"),
            _entry("solve", "求解方程", " = , x"),
            _entry("diff", "求导", " , x"),
            _entry("integrate", "不定积分", " , x"),
            _entry("nintegrate", "数值定积分", " , x, a, b"),
            _entry("findroot", "数值求根", " , x, 1"),
            _entry("limit", "求极限", " , x, 0"),
            _entry("series", "级数展开", " , x, 0, 6"),
            _entry("summation", "求和", " , k, 1, n"),
            _entry("product", "连乘", " , k, 1, n"),
        ],
    ),
    (
        "矩阵与向量",
        [
            _entry("matrix", "构造矩阵", "[1, 2], [3, 4]"),
            _entry("identity", "单位矩阵", "3"),
            _entry("eye", "单位矩阵别名", "3", "eye（identity）"),
            _entry("det", "行列式"),
            _entry("inv", "逆矩阵"),
            _entry("rank", "矩阵秩"),
            _entry("transpose", "矩阵转置"),
            _entry("eigenvalues", "特征值"),
            _entry("eigenvectors", "特征向量"),
            _entry("lu", "下上三角分解"),
            _entry("qr", "正交三角分解"),
        ],
    ),
    (
        "定宽整数与位运算",
        [
            _entry("fixed", "通用定宽整数", " , 64, true"),
            _entry("i8", "8 位有符号整数"),
            _entry("i16", "16 位有符号整数"),
            _entry("i32", "32 位有符号整数"),
            _entry("i64", "64 位有符号整数"),
            _entry("u8", "8 位无符号整数"),
            _entry("u16", "16 位无符号整数"),
            _entry("u32", "32 位无符号整数"),
            _entry("u64", "64 位无符号整数"),
            _entry("bitand", "按位与", " , "),
            _entry("bitor", "按位或", " , "),
            _entry("bitxor", "按位异或", " , "),
            _entry("bitnot", "按位取反"),
            _entry("shl", "左移", " , 1"),
            _entry("shr", "右移", " , 1"),
            _entry("rotl", "循环左移", " , 1"),
            _entry("rotr", "循环右移", " , 1"),
            _entry("popcount", "统计 1 的位数"),
        ],
    ),
    (
        "进制与数论",
        [
            _entry("base", "任意进制转换", " , 16"),
            _entry("hex", "十六进制"),
            _entry("bin", "二进制"),
            _entry("oct", "八进制"),
            _entry("gcd", "最大公约数", " , "),
            _entry("lcm", "最小公倍数", " , "),
            _entry("isprime", "判断质数"),
            _entry("nextprime", "下一个质数"),
            _entry("modpow", "模幂", " , 10, 1000"),
            _entry("comb", "组合数", " , "),
            _entry("binom", "组合数别名", " , ", "binom（comb）"),
        ],
    ),
    (
        "编码与哈希",
        [
            _entry("b64encode", "Base64 编码"),
            _entry("b64decode", "Base64 解码"),
            _entry("urlencode", "URL 编码"),
            _entry("urldecode", "URL 解码"),
            _entry("hexencode", "十六进制编码"),
            _entry("hexdecode", "十六进制解码"),
            _entry("md5", "MD5 摘要"),
            _entry("sha1", "SHA-1 摘要"),
            _entry("sha256", "SHA-256 摘要"),
            _entry("sha512", "SHA-512 摘要"),
        ],
    ),
    (
        "数据、时间与正则",
        [
            _entry("json_parse", "解析结构化文本"),
            _entry("json_stringify", "序列化结构化值"),
            _entry("csv_parse", "解析表格文本"),
            _entry("regex_test", "正则匹配", ' , "text"'),
            _entry("timestamp", "当前或指定时间戳"),
            _entry("datetime", "时间戳转 UTC 时间"),
            _entry("truth_table", "生成真值表", '"x and y"'),
        ],
    ),
    (
        "集合、调试与工具",
        [
            _entry("set", "构造集合"),
            _entry("range", "构造范围", "1, 10"),
            _entry("len", "长度"),
            _entry("random", "使用工作区种子的随机数"),
            _entry("ast", "表达式源码"),
            _entry("ast_dump", "内部结构表示"),
            _entry("version", "版本信息"),
        ],
    ),
]


class FunctionCatalogDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("函数大全")
        self.resize(820, 720)
        self.selected: FunctionTemplate | None = None
        intro = QLabel("搜索或展开分类，单击函数即可插入到最近使用的公式或脚本光标处。")
        intro.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索函数名称或说明…")
        self.search.textChanged.connect(self._filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["函数", "说明"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemClicked.connect(self._choose)
        for category, entries in FUNCTION_GROUPS:
            category_item = QTreeWidgetItem([category, ""])
            category_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(category_item)
            for template in entries:
                item = QTreeWidgetItem([template.name, template.description])
                item.setData(0, Qt.ItemDataRole.UserRole, template)
                category_item.addChild(item)
            category_item.setExpanded(True)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(index)
            if category is None:
                continue
            visible = False
            for child_index in range(category.childCount()):
                child = category.child(child_index)
                if child is None:
                    continue
                template: FunctionTemplate = child.data(0, Qt.ItemDataRole.UserRole)
                match = not needle or needle in (f"{template.name} {template.description}".lower())
                child.setHidden(not match)
                visible = visible or match
            category.setHidden(not visible)
            if needle and visible:
                category.setExpanded(True)

    def _choose(self, item: QTreeWidgetItem, _column: int) -> None:
        template = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(template, FunctionTemplate):
            self.selected = template
            self.accept()
