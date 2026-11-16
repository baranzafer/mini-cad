# SPDX-License-Identifier: GPL-3.0-or-later
"""Birim biçimleme ve ifade çözümleme (bpy gerektirmez, test edilebilir).

İç değerler her zaman Blender birimi (BU). Görüntü birimi metre cinsinden bir
çarpanla tanımlanır: metre = BU * scale_length.
"""
import ast
import math
import operator
import re

# ad -> (metre çarpanı, sonek)
UNIT_TABLE = {
    'UM': (1e-6, "µm"),
    'MM': (0.001, "mm"),
    'CM': (0.01, "cm"),
    'DM': (0.1, "dm"),
    'M': (1.0, "m"),
    'KM': (1000.0, "km"),
    'IN': (0.0254, "in"),
    'FT': (0.3048, "ft"),
    'YD': (0.9144, "yd"),
    'MI': (1609.344, "mi"),
}

# yazılan sonek -> metre çarpanı (uzun olanlar önce eşleşsin)
SUFFIXES = [
    ("inch", 0.0254), ("feet", 0.3048), ("foot", 0.3048),
    ("mm", 0.001), ("cm", 0.01), ("dm", 0.1), ("km", 1000.0), ("um", 1e-6), ("µm", 1e-6),
    ("in", 0.0254), ("ft", 0.3048), ("yd", 0.9144), ("mi", 1609.344),
    ("m", 1.0), ('"', 0.0254), ("'", 0.3048), ("″", 0.0254), ("′", 0.3048),
]

_METRIC_SCENE = {
    'KILOMETERS': 'KM', 'METERS': 'M', 'CENTIMETERS': 'CM',
    'MILLIMETERS': 'MM', 'MICROMETERS': 'UM',
}
_IMPERIAL_SCENE = {'MILES': 'MI', 'FEET': 'FT', 'INCHES': 'IN', 'THOU': 'IN'}


class UnitCtx:
    """Görüntü birimi bağlamı. unit=None ise uyarlamalı (değere göre seçer)."""

    def __init__(self, unit='M', scale_length=1.0, system='METRIC', precision=3):
        self.unit = unit
        self.scale_length = scale_length if scale_length > 0 else 1.0
        self.system = system          # 'METRIC' / 'IMPERIAL' / 'NONE'
        self.precision = precision

    @classmethod
    def from_settings(cls, settings, scene):
        us = scene.unit_settings
        prec = int(settings.precision)
        if settings.display_unit != 'SCENE':
            unit = settings.display_unit
            system = 'IMPERIAL' if unit in ('IN', 'FT', 'YD', 'MI') else 'METRIC'
            sl = us.scale_length if us.system != 'NONE' else 1.0
            return cls(unit, sl, system, prec)
        if us.system == 'NONE':
            return cls('BU', 1.0, 'NONE', prec)
        if us.system == 'METRIC':
            unit = _METRIC_SCENE.get(us.length_unit)      # ADAPTIVE -> None
        else:
            unit = _IMPERIAL_SCENE.get(us.length_unit)
        return cls(unit, us.scale_length, us.system, prec)

    # -- görüntü birimi seçimi
    def unit_for(self, value_bu):
        if self.unit is not None:
            return self.unit
        m = abs(value_bu) * self.scale_length
        if self.system == 'IMPERIAL':
            return 'IN' if m < 0.3048 else 'FT'
        if m < 0.01:
            return 'MM'
        if m < 1.0:
            return 'CM'
        if m < 1000.0:
            return 'M'
        return 'KM'

    def factor(self, unit):
        """1 görüntü biriminin BU karşılığı."""
        if unit == 'BU':
            return 1.0
        return UNIT_TABLE[unit][0] / self.scale_length

    def suffix(self, unit):
        return "" if unit == 'BU' else UNIT_TABLE[unit][1]

    def default_input_unit(self):
        """Sonek yazılmayan sayıların birimi."""
        if self.unit is not None:
            return self.unit
        return 'CM' if self.system != 'IMPERIAL' else 'IN'

    def fmt(self, value_bu, unit=None, sign=False):
        unit = unit or self.unit_for(value_bu)
        v = value_bu / self.factor(unit)
        p = self.precision
        txt = f"{v:+.{p}f}" if sign else f"{v:.{p}f}"
        # yuvarlama varsa '~' işareti
        if p < 8 and abs(round(v, p) - v) > 10 ** (-(p + 2)):
            txt = "~" + txt
        suf = self.suffix(unit)
        return f"{txt} {suf}" if suf else txt


# ---------------------------------------------------------------- çözümleme

_NUM = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


class ParseError(ValueError):
    pass


def _tokenize_units(text):
    """Sayı+birim çiftlerini U(sayı, çarpan) çağrısına çevirir."""
    suf_alt = "|".join(re.escape(s) for s, _ in SUFFIXES)
    pat = re.compile(rf"({_NUM})\s*({suf_alt})?(?![A-Za-z])", re.UNICODE)
    fac = dict(SUFFIXES)
    out = []
    pos = 0
    last_unit_end = None
    for m in pat.finditer(text):
        between = text[pos:m.start()]
        if between.strip() == "" and last_unit_end is not None and out:
            # "1m 20cm" -> 1m + 20cm
            out.append(" + ")
        else:
            out.append(between)
        num, suf = m.group(1), m.group(2)
        if suf:
            out.append(f"U({num},{fac[suf]!r})")
            last_unit_end = m.end()
        else:
            out.append(f"N({num})")
            last_unit_end = None
        pos = m.end()
    rest = text[pos:]
    out.append(rest)
    return "".join(out)


_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
}


def _eval(node, default_m):
    """(değer, boyutlu_mu) döndürür. Boyutlu değerler metre cinsindendir."""
    if isinstance(node, ast.Expression):
        return _eval(node.body, default_m)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [a.value for a in node.args if isinstance(a, ast.Constant)]
        if node.func.id == 'U' and len(args) == 2:
            return float(args[0]) * float(args[1]), True
        if node.func.id == 'N' and len(args) == 1:
            return float(args[0]), False
        raise ParseError("geçersiz ifade")
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value), False
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v, d = _eval(node.operand, default_m)
        return (-v if isinstance(node.op, ast.USub) else v), d
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        a, da = _eval(node.left, default_m)
        b, db = _eval(node.right, default_m)
        op = type(node.op)
        if op in (ast.Add, ast.Sub):
            if da and not db:
                b *= default_m
            elif db and not da:
                a *= default_m
            return _BINOPS[op](a, b), (da or db)
        if op is ast.Pow:
            if da or db:
                raise ParseError("birimli üs alınamaz")
            return a ** b, False
        if op is ast.Div and b == 0:
            raise ParseError("sıfıra bölme")
        return _BINOPS[op](a, b), (da or db)
    raise ParseError("geçersiz ifade")


def parse_length(text, uctx):
    """Uzunluk ifadesini BU olarak çözer. Örn: '4.5m', '450', '1m 20cm', '2*30cm', '1,5'"""
    t = text.strip().replace(",", ".").replace("×", "*")
    if not t:
        raise ParseError("boş")
    expr = _tokenize_units(t)
    if re.search(r"[A-Za-z_]", re.sub(r"\b[UN]\(", "(", expr)):
        raise ParseError("bilinmeyen birim")
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise ParseError("sözdizimi") from e
    unit = uctx.default_input_unit()
    default_m = UNIT_TABLE[unit][0] if unit != 'BU' else 1.0
    val, dim = _eval(tree, default_m)
    if not dim:
        val *= default_m
    if not math.isfinite(val):
        raise ParseError("sonsuz")
    return val / uctx.scale_length      # metre -> BU


def parse_target(text, uctx):
    """Hedef girişini çözer.

    '150%'  -> ('FACTOR', 1.5)
    '*2', 'x2', '/2' -> ('FACTOR', 2) / ('FACTOR', 0.5)
    diğerleri -> ('LENGTH', bu)
    """
    t = text.strip().replace(",", ".")
    if not t:
        raise ParseError("boş")
    if t.endswith("%"):
        body = t[:-1].strip()
        v, dim = _eval(ast.parse(_tokenize_units(body), mode='eval'), 1.0)
        if dim:
            raise ParseError("yüzdede birim olmaz")
        return 'FACTOR', v / 100.0
    if t[0] in "*xX×":
        body = t[1:].strip()
        v, dim = _eval(ast.parse(_tokenize_units(body), mode='eval'), 1.0)
        if dim:
            raise ParseError("çarpanda birim olmaz")
        return 'FACTOR', v
    if t[0] == "/":
        body = t[1:].strip()
        v, dim = _eval(ast.parse(_tokenize_units(body), mode='eval'), 1.0)
        if dim or v == 0:
            raise ParseError("geçersiz bölen")
        return 'FACTOR', 1.0 / v
    return 'LENGTH', parse_length(t, uctx)


def safe_parse_target(text, uctx):
    try:
        return parse_target(text, uctx)
    except (ParseError, SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
