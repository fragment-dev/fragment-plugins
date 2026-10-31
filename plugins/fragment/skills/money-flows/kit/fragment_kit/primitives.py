"""Ledger primitives for Fragment schemas: guards and proved arithmetic, each as (lines, conditions) parts.

    from kit.primitives import *
    T = entry("milestone_released", "Release {{milestone_id}}",
              step(STATE, 1, 2),                      # state 1 -> 2: settles once, and only after funding
              move(ESCROW, AVAIL, "{{amount}}"),       # money moves; the source...
              nonneg(ESCROW),                          # ...can't go negative
              check_ge0("fee", "{{fee}}"))             # an inequality, on a fresh account per entry

Fragment amounts and conditions only add and subtract parameters and integers: no "*", no parentheses
(verified with verify-schema). So a rule like "fee = amount x rate, rounded half up" can't be written; it
can be *checked*: the service supplies every intermediate value and the ledger confirms each step with
linear conditions (see proved_bps). The failure modes each primitive guards against are in its docstring.

Every entry built with entry() that uses check_ge0 must be posted with parameters operation_id and
check_n (a number unique to the entry within its operation, e.g. its index in the operation's plan).
"""

import copy
import re
from collections import defaultdict

STRONG = {"totalBalanceUpdates": "strong"}
OFFSET = "assets/kit-offset"                 # every memo/proof line is mirrored here so entries balance
CHECKS = "liabilities/kit-checks/op:{{operation_id}}/e:{{check_n}}/"
ZERO = "liabilities/kit-zero/"
POW, POW10K = "liabilities/kit-consts/pow:", "liabilities/kit-consts/pow10k:"
TOP = 39                                     # tables hold x * 2^0 .. x * 2^39 (amounts below ~$5.5 billion)
_families: dict = {}                         # zero-check family -> keyed?
_n = iter(range(10 ** 6))


# ------------------------------------------------------------------ building blocks

def acct(key, children=None, template=False, strong=False, name=None, type_=None):
    a = {"key": key}
    if type_:
        a["type"] = type_
    if name:
        a["name"] = name
    if template:
        a["template"] = True
    if strong:
        a["consistencyConfig"] = dict(STRONG)
    if children:
        a["children"] = children
    return a


def line(key, path, amount, repeated=None):
    l = {"key": key, "account": {"path": path}, "amount": amount}
    if repeated:
        l["repeated"] = {"key": repeated}
    return l


def cond(path, pre=None, post=None, repeated=None):
    c = {"account": {"path": path}}
    if pre:
        c["precondition"] = {"totalBalance": pre}
    if post:
        c["postcondition"] = {"totalBalance": post}
    if repeated:
        c["repeated"] = {"key": repeated}
    return c


def combine(*parts):
    lines, conds = [], []
    for l, c in parts:
        lines += l
        conds += c
    return lines, conds


def entry(type_, description, *parts, version=1, tags=("operation_id",)):
    """An entry type from parts. Adds the per-entry `used` marker if any check_ge0 is present."""
    lines, conds = combine(*parts)
    if any(c["account"]["path"].startswith(CHECKS) for c in conds):
        lines += [line("kit_check_used", CHECKS + "used", "1"), line("kit_check_used_off", OFFSET, "1")]
        conds.append(cond(CHECKS + "used", post={"eq": "1"}))
    e = {"type": type_, "typeVersion": version, "description": description, "postLinesAs": "net_amounts",
         "lines": lines}
    if conds:
        e["conditions"] = conds
    if tags:
        e["tags"] = [{"key": k, "value": "{{%s}}" % k} for k in tags]
    return e


# ------------------------------------------------------------------ guards

def move(src, dst, amount):
    """Moves `amount` from src to dst (same side of the balance sheet)."""
    k = next(_n)
    return [line(f"from{k}", src, negate(amount)), line(f"to{k}", dst, amount)], []


def negate(expr: str) -> str:
    """-(expr) without parentheses (Fragment allows none): flips the sign of every term, e.g. "{{a}} - {{b}} + 3"
    -> "-{{a}} + {{b}} - 3"."""
    terms = re.findall(r"\s*([+-]?)\s*([^+\-\s][^+\-]*?)\s*(?=[+-]|$)", expr.strip())
    out = []
    for sign, term in terms:
        flipped = "+" if sign == "-" else "-"
        out.append(("-" if flipped == "-" else "") + term if not out else f" {flipped} {term}")
    return "".join(out)


def nonneg(path, repeated=None):
    """The account ends >= 0. Sound on a shared account: it's the account's own balance."""
    return [], [cond(path, post={"gte": "0"}, repeated=repeated)]


def exact(path, value, repeated=None):
    """The account ends exactly at value (e.g. 0: an escrow fully paid out, no more, no less)."""
    return [], [cond(path, post={"eq": str(value)}, repeated=repeated)]


def once(path):
    """A marker that goes 0 -> 1: a second entry with the same marker (any ik, any amounts) is refused.
    Use for "request ID used once", "settles at most once"."""
    k = next(_n)
    return [line(f"once{k}", path, "1"), line(f"once{k}_off", OFFSET, "1")], [cond(path, post={"eq": "1"})]


def step(path, frm, to):
    """A state machine transition frm -> to: adds to - frm and requires exactly `to` afterwards, so the
    entry is refused from any other state. States are small integers; never reuse a number."""
    k, d = next(_n), int(to) - int(frm)
    return [line(f"step{k}", path, str(d)), line(f"step{k}_off", OFFSET, str(d))], [cond(path, post={"eq": str(to)})]


def write(key, path, expr):
    """A set-once value: adds expr and requires the account to end at expr (it must have been 0)."""
    return [line(key, path, expr), line(key + "_off", OFFSET, expr)], [cond(path, post={"eq": expr})]


def read(path, expr, repeated=None):
    """Requires the account to hold expr before the entry (binds a parameter to stored state)."""
    return [], [cond(path, pre={"eq": expr}, repeated=repeated)]


def check_ge0(name, expr):
    """expr >= 0, on a fresh account for this entry (checks/op:<op>/e:<n>/c:<name>).
    A shared check account would let one entry's slack hide another's negative."""
    path = CHECKS + "c:" + name
    return [line(f"c_{name}", path, expr), line(f"co_{name}", OFFSET, expr)], [cond(path, post={"gte": "0"})]


_TERM = re.compile(r"([+-]?)\s*(\{\{\w+\}\}|\d+)")


def _neg(expr):
    out = [("+" if s == "-" else "-") + " " + t for s, t in _TERM.findall(expr)]
    s = " ".join(out).strip()
    return s[2:] if s.startswith("+ ") else "-" + s[2:]


def _zero(family, expr, repeated=None, key=None):
    _families[family] = key is not None
    path = ZERO + family + (f"/k:{key}" if key else "")
    k = next(_n)
    return [line(f"z{k}_{family}", path, expr, repeated), line(f"zo{k}_{family}", OFFSET, expr, repeated)], path


def eq_zero(family, plus=(), minus=(), key=None, key_repeated=None):
    """sum(plus) - sum(minus) == 0, each term (expr, repeated-key or None). Honest entries net the zero
    account's lines to nothing, so they cost no lines after net_amounts."""
    lines, path = [], None
    for expr, rep in plus:
        l, path = _zero(family, expr, rep, key)
        lines += l
    for expr, rep in minus:
        l, path = _zero(family, _neg(expr), rep, key)
        lines += l
    return lines, [cond(path, post={"eq": "0"}, repeated=key_repeated)]


# ------------------------------------------------------------------ proved arithmetic

def doubling(table, base_read_path):
    """Items {j, h, v, half} extend `table` (a path prefix ending in ':'): table[j] = v = 2 x half and
    j = h + 1. Links prove each half is the value at h: +v at j, -half at h, +base at first, -top at
    last, and every link account ends at 0. Parameters: items, base, first, last, top."""
    fam = "link-" + table.strip(":").split("/")[-1].replace(":", "-")
    return combine(
        ([line("set", table + "{{j}}", "{{v}}", "items"), line("set_off", OFFSET, "{{v}}", "items")],
         [cond(table + "{{j}}", post={"eq": "{{v}}"}, repeated="items")]),
        eq_zero("double", plus=[("{{v}} - {{half}} - {{half}}", "items")], key="{{j}}", key_repeated="items"),
        eq_zero("index-step", plus=[("{{j}} - {{h}} - 1", "items")], key="{{j}}", key_repeated="items"),
        ([l for expr, rep, key in (("{{v}}", "items", "{{j}}"), ("-{{half}}", "items", "{{h}}"),
                                   ("{{base}}", None, "{{first}}"), ("-{{top}}", None, "{{last}}"))
          for l in _zero(fam, expr, rep, key)[0]], []),
        ([], [cond(ZERO + f"{fam}/k:{{{{j}}}}", post={"eq": "0"}, repeated="items"),
              cond(ZERO + f"{fam}/k:{{{{first}}}}", post={"eq": "0"})]),
        read(base_read_path, "{{base}}"))


def const_types():
    """Entry types that build 2^j and 10000 x 2^j once per ledger (post them before any proof)."""
    return [entry("kit_consts_based", "Constant tables: base", write("pow0", POW + "0", "1"),
                  write("pow10k0", POW10K + "0", "10000"), tags=()),
            entry("kit_consts_doubled", "Constant tables: 2^j", doubling(POW, POW + "{{first}}"), tags=()),
            entry("kit_consts10k_doubled", "Constant tables: 10000 x 2^j", doubling(POW10K, POW10K + "{{first}}"), tags=())]


def rate_table_types(prefix, name):
    """Entry types that build rate x 2^j for one stored rate: `prefix` holds {{rate_id}}, e.g.
    'liabilities/rates/rate:{{rate_id}}'. The rate itself is `prefix + '/value'`, set once."""
    return [entry(f"{name}_rate_set", "Rate {{rate_id}} set to {{value}}", write("value", prefix + "/value", "{{value}}"),
                  check_ge0("rate", "{{value}}"), check_ge0("rate-cap", "10000 - {{value}}"), write("pow0", prefix + "/pow:0", "{{value}}")),
            entry(f"{name}_rate_doubled", "Rate {{rate_id}} table", doubling(prefix + "/pow:", prefix + "/pow:{{first}}"), tags=())]


def products(table_a, table_b, a_name, b_name):
    """Items {j, qa, qb}: qa = table_a[j], qb = table_b[j]; sum(qa) = {{a_name}} and sum(qb) = {{b_name}}.
    With table_a = 2^j and table_b = x * 2^j this proves b = x * a, whatever bits the writer picks."""
    return combine(read(table_a + "{{j}}", "{{qa}}", "items"), read(table_b + "{{j}}", "{{qb}}", "items"),
                   eq_zero("sum-" + a_name, plus=[("{{qa}}", "items")], minus=[("{{%s}}" % a_name, None)]),
                   eq_zero("sum-" + b_name, plus=[("{{qb}}", "items")], minus=[("{{%s}}" % b_name, None)]))


def proved_bps_types(name, rate_prefix, out_prefix):
    """Two entry types proving out = round_half_up(amount x rate / 10000) for a stored rate:
      {name}_product  writes amount and amount x rate under out_prefix (set once)
      {name}_rounded  writes out, with out x 10000 within [product - 5000, product + 4999]
    out_prefix holds the object's ID, e.g. 'liabilities/proofs/fee/milestone:{{milestone_id}}'.
    Parameters: rate_id, amount, product, items (see bps_params), result, and operation_id/check_n."""
    p = out_prefix
    return [entry(f"{name}_product", f"{name}: amount x rate", read(rate_prefix + "/value", "{{rate}}"),
                  products(POW, rate_prefix + "/pow:", "amount", "product"),
                  write("amount", p + "/amount", "{{amount}}"), write("product", p + "/product", "{{product}}")),
            entry(f"{name}_rounded", f"{name}: rounded half up", read(p + "/product", "{{product}}"),
                  products(POW, POW10K, "result", "scaled"),
                  check_ge0("round-low", "{{product}} + 5000 - {{scaled}}"),
                  check_ge0("round-high", "{{scaled}} + 4999 - {{product}}"),
                  write("result", p + "/result", "{{result}}"))]


def kit_accounts(rate_prefix_tree=None):
    """The account subtrees the primitives use: merge into your chart (assets / liabilities children)."""
    zero = acct("kit-zero", name="Zero checks: each ends every entry at exactly 0", children=[
        acct(f, strong=True, children=[acct("k", template=True, strong=True)] if keyed else None)
        for f, keyed in sorted(_families.items())])
    liabilities = [
        acct("kit-checks", name="Inequality checks: a fresh account per operation and entry", children=[
            acct("op", template=True, children=[acct("e", template=True, children=[
                acct("c", template=True, strong=True), acct("used", strong=True)])])]),
        acct("kit-consts", name="Constant tables, built once by verified doubling", children=[
            acct("pow", template=True, strong=True), acct("pow10k", template=True, strong=True)]),
        zero]
    assets = [acct("kit-offset", strong=True, name="Memo: offset for kit proof and marker lines")]
    return {"assets": assets, "liabilities": liabilities}


def rate_accounts(key="rates"):
    """liabilities/<key>/rate:{{rate_id}}/{value, pow:{{j}}} for rate_table_types(f"liabilities/{key}/rate:{{{{rate_id}}}}", ...)."""
    return acct(key, name="Stored rates (bps) and their x 2^j tables", children=[acct("rate", template=True, children=[
        acct("value", strong=True), acct("pow", template=True, strong=True)])])


def proof_accounts(key, object_key):
    """liabilities/<key>/<object_key>:{{id}}/{amount, product, result} for proved_bps_types."""
    return acct(key, name=f"Proved results per {object_key}", children=[acct(object_key, template=True, children=[
        acct(k, strong=True) for k in ("amount", "product", "result")])])


# ------------------------------------------------------------------ the service side

def bits(n):
    return [j for j in range(TOP + 1) if n >> j & 1]


def doubling_params(base, first=0, last=TOP, chunk=10):
    """Parameters for the doubling entries that build table[first+1 .. last] from table[first] = base,
    as a list: one entry may touch only about 95 strongly consistent accounts (about 4 per item), so the
    table is built `chunk` items per entry, each continuing from where the previous one ended."""
    out, v, start = [], base, first
    while start < last:
        end = min(start + chunk, last)
        items, cur = [], v
        for j in range(start + 1, end + 1):
            items.append({"j": str(j), "h": str(j - 1), "v": str(cur * 2), "half": str(cur)})
            cur *= 2
        out.append({"items": items, "base": str(v), "first": str(start), "last": str(end), "top": str(cur)})
        v, start = cur, end
    return out


def bps_params(amount, rate):
    """Parameters for {name}_product and {name}_rounded: returns (product_params, rounded_params, result)."""
    product = amount * rate
    result = (product + 5000) // 10000
    p = {"amount": str(amount), "rate": str(rate), "product": str(product),
         "items": [{"j": str(j), "qa": str(1 << j), "qb": str(rate << j)} for j in bits(amount)]}
    r = {"product": str(product), "result": str(result), "scaled": str(result * 10000),
         "items": [{"j": str(j), "qa": str(1 << j), "qb": str(10000 << j)} for j in bits(result)]}
    return p, r, result
