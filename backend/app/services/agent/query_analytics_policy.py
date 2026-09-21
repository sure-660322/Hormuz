"""SQL-03 query_analytics offline policy validator.

The validator never connects to a database and never executes SQL. It parses a
single PostgreSQL statement with the pinned SQLGlot version, validates the full
tree against catalog v1 and returns SQL serialized from that same accepted AST.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.dialects import Dialect
from sqlglot.errors import ParseError, TokenError

SQLGLOT_VERSION = "30.18.0"
SQL_DIALECT = "postgres"
CATALOG_PATH = Path(__file__).resolve().parents[2] / "query_analytics_catalog_v1.json"

MAX_SQL_BYTES = 16 * 1024
MAX_PARAMS = 50
MAX_PARAM_BYTES = 8 * 1024
MAX_TOTAL_PARAM_BYTES = 64 * 1024
MAX_PURPOSE_CHARS = 500
MAX_IDENTIFIER_BYTES = 63
MAX_AST_NODES = 200
MAX_AST_DEPTH = 20
MAX_PROJECTIONS = 30
MAX_ORDER_ITEMS = 10
MAX_GROUP_ITEMS = 10
MAX_JOINS = 1

PARAM_TYPES = {"timestamptz", "date", "text", "int", "numeric", "bool"}
ALIAS_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
TRUSTED_OUTPUT_NAMES = {
    "call_id", "query_id", "status", "columns", "rows",
    "returned_row_count", "truncated", "source", "limitations",
    "catalog_version", "views", "data_scope",
}


class QueryPolicyError(ValueError):
    """Stable validation error. retryable is true only for ordinary syntax."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class QuerySyntaxError(QueryPolicyError):
    def __init__(self, message: str):
        super().__init__("syntax_error", message, retryable=True)


class QueryInputError(QueryPolicyError):
    def __init__(self, message: str):
        super().__init__("invalid_input", message)


class QueryRefusedError(QueryPolicyError):
    def __init__(self, message: str):
        super().__init__("refused", message)


@dataclass(frozen=True)
class BoundParameter:
    name: str
    type: str
    value: Any


@dataclass(frozen=True)
class ValidatedQuery:
    normalized_sql: str
    params: tuple[BoundParameter, ...]
    referenced_views: tuple[str, ...]
    catalog_version: str
    ast_node_count: int
    ast_depth: int


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QueryInputError("catalog v1 无法加载") from exc
    if catalog.get("catalog_version") != "1.0" or not isinstance(catalog.get("views"), list):
        raise QueryInputError("catalog v1 结构无效")
    return catalog


def _serialized_size(value: Any) -> int:
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise QueryInputError("参数值无法序列化") from exc
    return len(raw.encode("utf-8"))


def _validate_value(param_type: str, value: Any) -> None:
    valid = False
    if value is None:
        valid = True
    elif param_type == "text":
        valid = isinstance(value, str)
    elif param_type == "int":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif param_type == "numeric":
        valid = isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
    elif param_type == "bool":
        valid = isinstance(value, bool)
    elif param_type == "date":
        if isinstance(value, date) and not isinstance(value, datetime):
            valid = True
        elif isinstance(value, str):
            try:
                date.fromisoformat(value)
                valid = True
            except ValueError:
                valid = False
    elif param_type == "timestamptz":
        parsed = value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
        valid = (
            isinstance(parsed, datetime)
            and parsed.tzinfo is not None
            and parsed.utcoffset() is not None
        )
    if not valid:
        raise QueryInputError(f"参数类型和值不匹配：{param_type}")


def _validate_params(raw_params: list[dict[str, Any]] | None) -> dict[str, BoundParameter]:
    if raw_params is None:
        raw_params = []
    if not isinstance(raw_params, list):
        raise QueryInputError("params 必须是数组")
    if len(raw_params) > MAX_PARAMS:
        raise QueryInputError(f"参数数量不能超过 {MAX_PARAMS}")

    result: dict[str, BoundParameter] = {}
    total_size = 0
    for raw in raw_params:
        if not isinstance(raw, dict) or set(raw) != {"name", "type", "value"}:
            raise QueryInputError("每个参数必须且只能包含 name/type/value")
        name = raw["name"]
        param_type = raw["type"]
        if not isinstance(name, str) or not ALIAS_RE.fullmatch(name):
            raise QueryInputError("参数名必须是小写安全标识符")
        if len(name.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
            raise QueryInputError("参数名超过 PostgreSQL 63 字节限制")
        if name in result:
            raise QueryInputError(f"参数重复：{name}")
        if param_type not in PARAM_TYPES:
            raise QueryInputError(f"参数类型不在白名单：{param_type}")
        _validate_value(param_type, raw["value"])
        size = _serialized_size(raw["value"])
        if size > MAX_PARAM_BYTES:
            raise QueryInputError(f"单个参数超过 {MAX_PARAM_BYTES} 字节")
        total_size += size
        if total_size > MAX_TOTAL_PARAM_BYTES:
            raise QueryInputError(f"参数值合计超过 {MAX_TOTAL_PARAM_BYTES} 字节")
        result[name] = BoundParameter(name, param_type, raw["value"])
    return result


def _catalog_views(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {view["name"]: view for view in catalog["views"]}


def _type_family(postgres_type: str) -> str:
    lowered = postgres_type.lower()
    if "timestamp with time zone" in lowered:
        return "timestamptz"
    if lowered == "date":
        return "date"
    if lowered == "boolean":
        return "bool"
    if lowered in {"bigint", "integer", "smallint"}:
        return "int"
    if lowered in {"double precision", "real", "numeric"} or lowered.startswith("numeric("):
        return "numeric"
    if lowered == "text" or lowered.startswith("character varying"):
        return "text"
    return "unknown"


def _tree_depth(node: exp.Expression) -> int:
    maximum = 0
    stack = [(node, 1)]
    while stack:
        current, depth = stack.pop()
        maximum = max(maximum, depth)
        stack.extend((child, depth + 1) for child in current.iter_expressions())
    return maximum


def _is_descendant_of(node: exp.Expression, parents: tuple[type[exp.Expression], ...]) -> bool:
    current = node.parent
    while current is not None:
        if isinstance(current, parents):
            return True
        current = current.parent
    return False


def _validate_alias(name: str, used: set[str]) -> None:
    tokenizer = Dialect.get_or_raise(SQL_DIALECT).tokenizer_class
    if (
        not ALIAS_RE.fullmatch(name)
        or name.upper() in tokenizer.KEYWORDS
        or name in TRUSTED_OUTPUT_NAMES
        or name in used
    ):
        raise QueryRefusedError(f"输出别名不允许：{name}")
    used.add(name)


def _infer_type(
    node: exp.Expression,
    column_types: dict[int, str],
    params: dict[str, BoundParameter],
) -> str:
    if isinstance(node, exp.Paren):
        return _infer_type(node.this, column_types, params)
    if isinstance(node, exp.Alias):
        return _infer_type(node.this, column_types, params)
    if isinstance(node, exp.Column):
        return column_types.get(id(node), "unknown")
    if isinstance(node, exp.Placeholder):
        param = params.get(node.name)
        return param.type if param else "unknown"
    if isinstance(node, exp.Null):
        return "null"
    if isinstance(node, exp.Boolean):
        return "bool"
    if isinstance(node, exp.Cast):
        return _cast_target(node)
    if isinstance(node, exp.Count):
        return "int"
    if isinstance(node, (exp.Sum, exp.Avg, exp.Extract)):
        return "numeric"
    if isinstance(node, (exp.Min, exp.Max)):
        return _infer_type(node.this, column_types, params)
    if isinstance(node, (exp.Upper, exp.Lower)):
        return "text"
    if isinstance(node, exp.Length):
        return "int"
    if isinstance(node, exp.TimestampTrunc):
        return _infer_type(node.this, column_types, params)
    if isinstance(node, exp.Coalesce):
        values = [node.this, *node.expressions]
        types = {_infer_type(item, column_types, params) for item in values} - {"null"}
        return next(iter(types)) if len(types) == 1 else "unknown"
    if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
        return "numeric"
    if isinstance(node, (exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE,
                         exp.And, exp.Or, exp.Not, exp.Like, exp.In, exp.Between, exp.Is)):
        return "bool"
    return "unknown"


def _cast_target(node: exp.Cast) -> str:
    target = node.args.get("to")
    if not isinstance(target, exp.DataType):
        return "unknown"
    mapping = {
        exp.DataType.Type.DATE: "date",
        exp.DataType.Type.TEXT: "text",
        exp.DataType.Type.VARCHAR: "text",
        exp.DataType.Type.INT: "int",
        exp.DataType.Type.BIGINT: "int",
        exp.DataType.Type.DECIMAL: "numeric",
    }
    return mapping.get(target.this, "unknown")


def _validate_functions_and_operators(
    tree: exp.Select,
    column_types: dict[int, str],
    params: dict[str, BoundParameter],
) -> None:
    allowed_functions = (
        exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Upper, exp.Lower,
        exp.Length, exp.Coalesce, exp.TimestampTrunc, exp.Extract,
    )
    allowed_binary = (
        exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE,
        exp.And, exp.Or, exp.Add, exp.Sub, exp.Mul, exp.Div,
        exp.Like, exp.In, exp.Between, exp.Is,
    )
    allowed_function_types = set(allowed_functions) | {exp.Cast}
    allowed_operator_types = set(allowed_binary) | {exp.Not}

    def compatible(left: str, right: str) -> bool:
        if "unknown" in {left, right}:
            return False
        if "null" in {left, right}:
            return True
        return left == right or {left, right} <= {"int", "numeric"}

    for node in tree.walk():
        if (
            isinstance(node, exp.Func)
            and type(node) not in allowed_function_types
            and type(node) not in allowed_operator_types
        ):
            raise QueryRefusedError(f"函数不在白名单：{node.sql_name()}")
        if isinstance(node, exp.Binary) and not isinstance(node, allowed_binary):
            raise QueryRefusedError(f"操作符不在白名单：{type(node).__name__}")
        if isinstance(node, (exp.TryCast, exp.ILike, exp.RegexpLike)):
            raise QueryRefusedError(f"表达式不在白名单：{type(node).__name__}")

        if isinstance(node, exp.Cast) and _cast_target(node) not in {"date", "text", "int", "numeric"}:
            raise QueryRefusedError("CAST 目标类型不在白名单")
        if isinstance(node, exp.Count) and (node.this is None or node.expressions):
            raise QueryRefusedError("COUNT 必须且只能有一个参数")
        if isinstance(node, (exp.Sum, exp.Avg)):
            if _infer_type(node.this, column_types, params) not in {"int", "numeric"}:
                raise QueryRefusedError(f"{node.sql_name()} 只允许数值参数")
        if isinstance(node, exp.Coalesce):
            values = [node.this, *node.expressions]
            if len(values) < 2 or _infer_type(node, column_types, params) == "unknown":
                raise QueryRefusedError("COALESCE 至少需要两个同类型参数")
        if isinstance(node, (exp.Upper, exp.Lower, exp.Length)):
            if _infer_type(node.this, column_types, params) != "text":
                raise QueryRefusedError(f"{node.sql_name()} 只允许文本参数")
        if isinstance(node, exp.TimestampTrunc):
            if _infer_type(node.this, column_types, params) != "timestamptz":
                raise QueryRefusedError("date_trunc 第二参数必须是 timestamptz")
            unit = node.args.get("unit")
            if not isinstance(unit, exp.Placeholder) or _infer_type(unit, column_types, params) != "text":
                raise QueryRefusedError("date_trunc 单位必须使用 text 绑定参数")
        if isinstance(node, exp.Extract):
            if _infer_type(node.expression, column_types, params) not in {"date", "timestamptz"}:
                raise QueryRefusedError("extract 只允许日期或时间字段")
            if not isinstance(node.this, exp.Var) or node.this.name.upper() not in {
                "YEAR", "MONTH", "DAY", "HOUR", "MINUTE", "SECOND",
            }:
                raise QueryRefusedError("extract 时间字段不在白名单")
        if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
            sides = (_infer_type(node.this, column_types, params),
                     _infer_type(node.expression, column_types, params))
            if any(item not in {"int", "numeric"} for item in sides):
                raise QueryRefusedError("算术操作只允许数值表达式")
        if isinstance(node, (exp.And, exp.Or)):
            sides = (_infer_type(node.this, column_types, params),
                     _infer_type(node.expression, column_types, params))
            if any(item != "bool" for item in sides):
                raise QueryRefusedError("逻辑操作只允许布尔表达式")
        if isinstance(node, exp.Not):
            if _infer_type(node.this, column_types, params) != "bool":
                raise QueryRefusedError("NOT 只允许布尔表达式")
        if isinstance(node, exp.Like):
            sides = (_infer_type(node.this, column_types, params),
                     _infer_type(node.expression, column_types, params))
            if any(item != "text" for item in sides):
                raise QueryRefusedError("LIKE 只允许文本表达式")
        if isinstance(node, (exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE)):
            left = _infer_type(node.this, column_types, params)
            right = _infer_type(node.expression, column_types, params)
            if not compatible(left, right):
                raise QueryRefusedError("比较操作两侧类型不兼容")
        if isinstance(node, exp.In):
            left = _infer_type(node.this, column_types, params)
            if not node.expressions or any(
                not compatible(left, _infer_type(item, column_types, params))
                for item in node.expressions
            ):
                raise QueryRefusedError("IN 参数类型不兼容")
        if isinstance(node, exp.Between):
            value_type = _infer_type(node.this, column_types, params)
            if not compatible(value_type, _infer_type(node.args["low"], column_types, params)) or not compatible(
                value_type, _infer_type(node.args["high"], column_types, params)
            ):
                raise QueryRefusedError("BETWEEN 参数类型不兼容")
        if isinstance(node, exp.Is):
            right = _infer_type(node.expression, column_types, params)
            if right not in {"null", "bool"}:
                raise QueryRefusedError("IS 仅允许 NULL/TRUE/FALSE")
            if right == "bool" and _infer_type(node.this, column_types, params) != "bool":
                raise QueryRefusedError("IS TRUE/FALSE 左侧必须是布尔表达式")


def validate_query(
    sql: str,
    params: list[dict[str, Any]] | None = None,
    purpose: str = "",
    *,
    catalog: dict[str, Any] | None = None,
) -> ValidatedQuery:
    """Validate one model-produced query and return same-AST normalized SQL."""

    if sqlglot.__version__ != SQLGLOT_VERSION:
        raise QueryInputError("SQLGlot 运行版本与 SQL-03 锁定版本不一致")
    if not isinstance(sql, str) or not sql.strip():
        raise QueryInputError("sql 必须是非空字符串")
    if len(sql.encode("utf-8")) > MAX_SQL_BYTES:
        raise QueryInputError(f"SQL 文本不能超过 {MAX_SQL_BYTES} 字节")
    if not isinstance(purpose, str) or len(purpose) > MAX_PURPOSE_CHARS:
        raise QueryInputError(f"purpose 不能超过 {MAX_PURPOSE_CHARS} 字符")

    bound_params = _validate_params(params)
    catalog = catalog or load_catalog()
    views = _catalog_views(catalog)

    try:
        tokenizer = Dialect.get_or_raise(SQL_DIALECT).tokenizer_class()
        tokens = tokenizer.tokenize(sql)
    except TokenError as exc:
        raise QuerySyntaxError("SQL 词法解析失败") from exc
    if any(token.comments for token in tokens):
        raise QueryRefusedError("SQL comment token 不允许")
    if any("STRING" in token.token_type.name for token in tokens):
        raise QueryRefusedError("字符串和日期时间字面量不允许，必须使用绑定参数")

    try:
        statements = sqlglot.parse(sql, read=SQL_DIALECT)
    except ParseError as exc:
        raise QuerySyntaxError("SQL 语法解析失败") from exc
    except RecursionError as exc:
        raise QueryRefusedError("SQL 嵌套深度超过解析上限") from exc
    if len(statements) != 1 or statements[0] is None:
        raise QueryRefusedError("只允许一条 SQL 语句")
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise QueryRefusedError("只允许 SELECT")

    forbidden = (
        exp.With, exp.CTE, exp.Subquery, exp.Lateral, exp.SetOperation,
        exp.Window, exp.Into, exp.Lock, exp.Command,
    )
    if any(isinstance(node, forbidden) for node in tree.walk()):
        raise QueryRefusedError("查询包含首批禁止的结构")
    if sum(1 for node in tree.walk() if isinstance(node, exp.Select)) != 1:
        raise QueryRefusedError("子查询不允许")
    if tree.args.get("distinct") is not None:
        raise QueryRefusedError("DISTINCT 首批不允许")

    nodes = list(tree.walk())
    allowed_node_types = {
        exp.Select, exp.From, exp.Table, exp.TableAlias, exp.Identifier,
        exp.Column, exp.Alias, exp.Placeholder, exp.Where, exp.Group,
        exp.Having, exp.Order, exp.Ordered, exp.Limit, exp.Offset, exp.Join,
        exp.Paren, exp.Null, exp.Boolean, exp.Literal, exp.Star, exp.Var, exp.DataType,
        exp.Cast, exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Upper,
        exp.Lower, exp.Length, exp.Coalesce, exp.TimestampTrunc, exp.Extract,
        exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE, exp.And, exp.Or,
        exp.Not, exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Like, exp.In,
        exp.Between, exp.Is,
    }
    unsupported = next((node for node in nodes if type(node) not in allowed_node_types), None)
    if unsupported is not None:
        raise QueryRefusedError(f"AST 节点不在白名单：{type(unsupported).__name__}")
    depth = _tree_depth(tree)
    if len(nodes) > MAX_AST_NODES or depth > MAX_AST_DEPTH:
        raise QueryRefusedError("AST 复杂度超过限制")
    if len(tree.expressions) > MAX_PROJECTIONS:
        raise QueryRefusedError("投影列数超过限制")
    order = tree.args.get("order")
    group = tree.args.get("group")
    if order is not None and len(order.expressions) > MAX_ORDER_ITEMS:
        raise QueryRefusedError("ORDER BY 项数超过限制")
    if group is not None and len(group.expressions) > MAX_GROUP_ITEMS:
        raise QueryRefusedError("GROUP BY 项数超过限制")
    joins = list(tree.args.get("joins") or [])
    if len(joins) > MAX_JOINS:
        raise QueryRefusedError("JOIN 数量超过限制")

    from_clause = tree.args.get("from_")
    if from_clause is None or not isinstance(from_clause.this, exp.Table):
        raise QueryRefusedError("必须从 catalog 视图查询")
    tables = [from_clause.this, *[join.this for join in joins]]
    if not all(isinstance(table, exp.Table) for table in tables):
        raise QueryRefusedError("FROM/JOIN 只能引用 catalog 视图")

    aliases: dict[str, str] = {}
    referenced: list[str] = []
    for table in tables:
        if table.catalog or table.db != "agent_data":
            raise QueryRefusedError("关系必须使用 agent_data 全限定名")
        full_name = f"agent_data.{table.name}"
        if full_name not in views:
            raise QueryRefusedError(f"关系不在 catalog：{full_name}")
        alias = table.alias_or_name
        if not ALIAS_RE.fullmatch(alias) or alias in aliases:
            raise QueryRefusedError("表别名无效或重复")
        aliases[alias] = full_name
        if not table.alias:
            aliases[table.name] = full_name
        referenced.append(full_name)

    if joins:
        join = joins[0]
        side = (join.args.get("side") or "").upper()
        kind = (join.args.get("kind") or "").upper()
        if side not in {"", "LEFT"} or kind not in {"", "INNER"}:
            raise QueryRefusedError("仅允许 INNER JOIN 或 LEFT JOIN")
        if join.args.get("using") or join.args.get("method"):
            raise QueryRefusedError("USING/NATURAL/CROSS JOIN 不允许")
        on = join.args.get("on")
        if not isinstance(on, exp.EQ):
            raise QueryRefusedError("JOIN ON 必须是唯一批准的等值条件")

    output_aliases: set[str] = set()
    for projection in tree.expressions:
        if isinstance(projection, exp.Alias):
            _validate_alias(projection.alias, output_aliases)

    column_types: dict[int, str] = {}
    for column in tree.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        if column.db and column.db != "agent_data":
            raise QueryRefusedError("字段 schema 不允许")
        qualifier = column.table
        if not qualifier and column.name in output_aliases and _is_descendant_of(column, (exp.Ordered,)):
            continue
        if joins and not qualifier:
            raise QueryRefusedError("JOIN 查询中的字段必须带表限定")
        if qualifier:
            view_name = aliases.get(qualifier)
            if view_name is None:
                raise QueryRefusedError(f"未知字段限定符：{qualifier}")
        else:
            view_name = referenced[0]
        columns = {item["name"]: item for item in views[view_name]["columns"]}
        if column.name not in columns:
            raise QueryRefusedError(f"字段不在 catalog：{column.name}")
        column_types[id(column)] = _type_family(columns[column.name]["postgres_type"])

    if joins:
        left, right = joins[0].args["on"].this, joins[0].args["on"].expression
        if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
            raise QueryRefusedError("JOIN 条件必须直接比较批准字段")
        pair = {(aliases.get(left.table), left.name), (aliases.get(right.table), right.name)}
        approved = {
            ("agent_data.v_news", "event_id"),
            ("agent_data.v_events", "event_id"),
        }
        if pair != approved:
            raise QueryRefusedError("JOIN 条件不在白名单")

    for star in tree.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            raise QueryRefusedError("SELECT * 不允许，唯一例外是 COUNT(*)")
    for literal in tree.find_all(exp.Literal):
        if literal.is_string:
            raise QueryRefusedError("字符串字面量不允许")
        if not _is_descendant_of(literal, (exp.Limit, exp.Offset)):
            raise QueryRefusedError("数值字面量只允许用于 LIMIT/OFFSET")
        try:
            if int(literal.this) < 0:
                raise ValueError
        except ValueError as exc:
            raise QueryRefusedError("LIMIT/OFFSET 必须是非负整数") from exc
    for structural_limit in (tree.args.get("limit"), tree.args.get("offset")):
        if structural_limit is not None and any(
            isinstance(item, exp.Placeholder) for item in structural_limit.walk()
        ):
            raise QueryRefusedError("LIMIT/OFFSET 只允许非负整数字面量")

    placeholder_names = [item.name for item in tree.find_all(exp.Placeholder)]
    if any(not ALIAS_RE.fullmatch(name) for name in placeholder_names):
        raise QueryInputError("占位符名称无效")
    if set(placeholder_names) != set(bound_params):
        raise QueryInputError("SQL 占位符与 params 必须一一对应")
    for identifier in tree.find_all(exp.Identifier):
        if len(identifier.name.encode("utf-8")) > MAX_IDENTIFIER_BYTES:
            raise QueryInputError("SQL 标识符超过 PostgreSQL 63 字节限制")

    aggregate_nodes = list(tree.find_all(exp.AggFunc))
    if aggregate_nodes:
        grouped = {
            item.sql(dialect=SQL_DIALECT, pretty=False)
            for item in (group.expressions if group is not None else [])
        }
        for projection in tree.expressions:
            expression = projection.this if isinstance(projection, exp.Alias) else projection
            if not any(isinstance(item, exp.AggFunc) for item in expression.walk()):
                if expression.sql(dialect=SQL_DIALECT, pretty=False) not in grouped:
                    raise QueryRefusedError("聚合查询的非聚合投影必须出现在 GROUP BY")

    _validate_functions_and_operators(tree, column_types, bound_params)

    normalized = tree.sql(dialect=SQL_DIALECT, pretty=False)
    return ValidatedQuery(
        normalized_sql=normalized,
        params=tuple(bound_params.values()),
        referenced_views=tuple(dict.fromkeys(referenced)),
        catalog_version=catalog["catalog_version"],
        ast_node_count=len(nodes),
        ast_depth=depth,
    )
