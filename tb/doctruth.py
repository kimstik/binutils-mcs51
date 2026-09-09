#!/usr/bin/env python3
"""Check gas/doc/c-i51.texi against the code it documents.

The manual was made normative and nothing checked it.  Three of its
sentences were found false in one afternoon - the HIGH()/LOW() prefix rule
for jb/jnb/jbc, the B2B edge, the .ds direct-address case - and a human
reading caught every one of them.  This stage is the part of that reading a
machine can do.

WHAT IT CHECKS.  Six facts that the manual and the source each state
independently, so that the two can be compared without either being taken
on trust:

  directives    every name in md_pseudo_table (gas/config/tc-i51.c) is
                named in the manual's Directives section, and every `@item'
                / `@itemx' of that section's table is a name in
                md_pseudo_table.  Aliases are entries like any other:
                .bcommon has to be documented because it exists.
  operands      the set of built-in operand names the manual lists in
                i51-Regs is exactly the set of names in i51_directop, after
                the `@code{R0} @dots{} @code{R7}' ranges are expanded; and
                every i51_directop entry is listed under the manual group
                that matches its kind - 'D' under the byte-addressable
                special function registers, 'B' under the bit-addressable
                names, 'U' under the register-bank byte addresses, the rest
                under the registers and addressing modes.
  values        the two operand values the manual states outright, in
                `@samp{.byte ACC} therefore assembles to @code{0xE0}', are
                the values i51_directop gives those names.
  relocations   the set of R_I51_* names the manual uses anywhere is
                exactly the set RELOC_NUMBERS declares in
                include/elf/i51.h.
  mnemonics     the instruction list in the Opcodes section is exactly the
                set of names in the I51_INS rows of include/opcode/i51.h.
  diagnostics   every diagnostic the manual quotes is an instance of a
                printf format string that occurs in gas/config/tc-i51.c or
                bfd/elf32-i51.c.  The manual quotes finished output -
                `ACALL/AJMP target 0x900 is not in the same 2K page as
                0x7fe' - so the comparison is against the format with each
                conversion matched by what it can print (%s by any text,
                %ld by a decimal number, %lx by hex digits, %pB by a file
                name), the `Error: ' gas prefixes being stripped first.  A
                quoted diagnostic that no format string can produce is a
                sentence the tools will never print.

The port has no source tree: its files live in mcs51/additions.patch as +
lines.  They are reconstructed here through fixhunks.added_files (), which
is the reader that patch file's own hash check already uses.  Nothing is
built and no toolchain is needed, so this stage says nothing about the
binaries - only about what the repository claims.

WHAT IT CANNOT CHECK.  English.  Most of c-i51.texi is prose about
behaviour, and a check that appeared to verify prose would be worse than no
check at all, because it would be believed.  Nothing here reads a sentence.
In particular it does not know, and does not pretend to know:

  * whether a documented rule is the rule the code implements.  "They are
    rejected on the operand of @code{acall} and @code{ajmp}" names two
    mnemonics that exist and a behaviour nothing here tests; the three
    false sentences that prompted this stage were all of that shape, and
    all three would still pass it.  Only a stage that assembles something
    can judge them - that is what bits, reloc and branch are for.
  * whether a stated number is right.  The manual says 0x20.3 is bit
    address 0x03; the fold that decides is C in i51_fold_bit_suffix (), and
    re-deriving it in Python here would only compare this file against the
    manual.
  * whether the substituted values in a quoted diagnostic are consistent.
    0x900 and 0x7fe really are in different 2K pages, but this stage checks
    the sentence, not the arithmetic behind the example.
  * anything about a diagnostic that is described rather than quoted.

HOW THE MANUAL DECLARES A QUOTATION.  A `@smallexample' that reproduces
tool output carries a `@c doctruth: diagnostic' comment on the line above
it; the instruction list carries `@c doctruth: mnemonics'.  The marker is
invisible in the formatted manual and is what tells this stage which
examples are claims about the tools rather than sample source.  A block
that is not marked but contains `Error:' is a failure: the marker can be
forgotten, so forgetting it has to be loud rather than silent.

  doctruth.py [--patch mcs51/additions.patch]

exit: 0 the manual agrees with the source, 1 it does not, 2 something the
      stage needs is not there to read.
"""

import argparse
import itertools
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixhunks                                          # noqa: E402

TEXI = "gas/doc/c-i51.texi"
GAS = "gas/config/tc-i51.c"
BFD = "bfd/elf32-i51.c"
ELFH = "include/elf/i51.h"
OPCH = "include/opcode/i51.h"


class Check:
    """Every judgement the run makes, and the ones that went against it."""

    def __init__(self):
        self.n = 0
        self.fail = []

    def true(self, what, cond):
        self.n += 1
        if not cond:
            self.fail.append(what)
        return cond

    def same(self, what, manual, source,
             mword="the manual", sword="the source"):
        """MANUAL and SOURCE name the same set, in both directions."""
        only_m = sorted(manual - source)
        only_s = sorted(source - manual)
        self.true("%s: %s names %s, %s has no such entry"
                  % (what, mword, ", ".join(only_m), sword), not only_m)
        self.true("%s: %s has %s, %s does not name %s"
                  % (what, sword, ", ".join(only_s), mword,
                     "it" if len(only_s) == 1 else "them"), not only_s)


# ------------------------------------------------------------------ texinfo

BRACED = re.compile(r"@[a-z]+\{([^{}]*)\}")
RANGE = re.compile(r"@code\{([^{}]*)\}\s*@dots\{\}\s*@code\{([^{}]*)\}")
CODE = re.compile(r"@code\{([^{}]*)\}")
R_SPAN = re.compile(r"@r\{([^{}]*)\}")
ITEM = re.compile(r"^@itemx?\s+(.*)$")


def undo_texinfo(s):
    """S as it reads in the formatted manual: markup off, @@ back to @."""
    s = s.replace("@dots{}", "...").replace("@minus{}", "-")
    prev = None
    while prev != s:
        prev = s
        s = BRACED.sub(r"\1", s)
    return s.replace("@@", "@").replace("@{", "{").replace("@}", "}")


def squeeze(s):
    """S with every run of white space collapsed to one space."""
    return " ".join(s.split())


def nodes(lines):
    """{node name: [lines]} - the manual cut at its @node lines."""
    out, name, buf = {}, None, []
    for s in lines:
        if s.startswith("@node "):
            if name is not None:
                out[name] = buf
            name, buf = s[len("@node "):].strip(), []
        else:
            buf.append(s)
    if name is not None:
        out[name] = buf
    return out


def table_body(lines):
    """The body of the first top-level @table in LINES, nesting kept."""
    depth, body = 0, None
    for s in lines:
        if s.startswith("@table"):
            depth += 1
            if depth == 1:
                body = []
                continue
        elif s.startswith("@end table"):
            depth -= 1
            if depth == 0:
                return body
        if body is not None:
            body.append(s)
    return body


def table_items(body):
    """[(item head, [lines])] for the @item entries of a table body."""
    out, head, buf, depth = [], None, [], 0
    for s in body:
        if s.startswith("@table"):
            depth += 1
        elif s.startswith("@end table"):
            depth -= 1
        if depth == 0 and s.startswith("@item "):
            if head is not None:
                out.append((head, buf))
            head, buf = s[len("@item "):].strip(), []
            continue
        if head is not None:
            buf.append(s)
    if head is not None:
        out.append((head, buf))
    return out


def examples(lines):
    """[(kind, text lines, lineno)] for every @smallexample block.

    KIND is the word of a `@c doctruth: KIND' comment on the line directly
    above the block, None when there is none.
    """
    out = []
    for i, s in enumerate(lines):
        if s.strip() != "@smallexample":
            continue
        kind = None
        if i > 0:
            m = re.match(r"^@c\s+doctruth:\s*(\S+)\s*$", lines[i - 1])
            if m:
                kind = m.group(1)
        body = []
        j = i + 1
        while j < len(lines) and lines[j].strip() != "@end smallexample":
            body.append(lines[j])
            j += 1
        out.append((kind, body, i + 1))
    return out


def expand(a, b):
    """The names of the range A @dots{} B, or None when it is not one.

    The two ends differ in one or more digit positions and nowhere else;
    each such position runs from A's digit to B's.  `R0' @dots{} `R7' is one
    position, `P0.0' @dots{} `P3.7' is two and names all thirty-two bits.
    """
    if len(a) != len(b):
        return None
    pos = [k for k in range(len(a)) if a[k] != b[k]]
    if not pos:
        return [a]
    spans = []
    for k in pos:
        if not (a[k].isdigit() and b[k].isdigit() and a[k] <= b[k]):
            return None
        spans.append([chr(c) for c in range(ord(a[k]), ord(b[k]) + 1)])
    out = []
    for combo in itertools.product(*spans):
        s = list(a)
        for k, ch in zip(pos, combo):
            s[k] = ch
        out.append("".join(s))
    return out


def code_names(text):
    """The @code{...} names in TEXT, ranges expanded.

    A name beginning with a dot is a directive, not an operand name, and is
    left out: the operand groups mention `.using' in passing.
    """
    names, broken = set(), []
    for m in RANGE.finditer(text):
        a, b = undo_texinfo(m.group(1)), undo_texinfo(m.group(2))
        got = expand(a, b)
        if got is None:
            broken.append("%s ... %s" % (a, b))
        else:
            names.update(got)
    for m in CODE.finditer(RANGE.sub(" ", text)):
        names.add(undo_texinfo(m.group(1)))
    return {n for n in names if not n.startswith(".")}, broken


# -------------------------------------------------------------------- C

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
           "f": "\f", "v": "\v", "\\": "\\", '"': '"', "'": "'", "?": "?"}


def unescape_c(s):
    """The bytes a C string literal body stands for, as text."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        e = s[i]
        if e in ESCAPES:
            out.append(ESCAPES[e])
            i += 1
        elif e == "x":
            i += 1
            j = i
            while j < n and s[j] in "0123456789abcdefABCDEF":
                j += 1
            out.append(chr(int(s[i:j] or "0", 16)))
            i = j
        elif e in "01234567":
            j = i
            while j < n and j < i + 3 and s[j] in "01234567":
                j += 1
            out.append(chr(int(s[i:j], 8)))
            i = j
        else:
            out.append(e)
            i += 1
    return "".join(out)


def opens_gettext(text, i):
    """Is the literal at TEXT[I] the first one of a `_(' argument?"""
    k = i - 1
    while k >= 0 and text[k].isspace():
        k -= 1
    return k >= 1 and text[k] == "(" and text[k - 1] == "_"


def c_strings(text):
    """The translatable string literals of TEXT, adjacent ones joined.

    Only a run that opens directly after `_(' is collected, which is what
    makes the result the strings the tools say to a user rather than every
    literal in the file.  Every diagnostic in this port is written
    as_bad (_("...")), and the debugging fprintf ()s beside them are not:
    one of those is "%s\\n", and a format that is nothing but a conversion
    matches any sentence at all, so a stage that took it for a candidate
    would pass every quotation in the manual whatever it said.

    Comments and character constants are stepped over, so a quote inside
    either does not open a string; a comment between two literals does not
    break the run, because the compiler joins them across it.
    """
    out, cur = [], None
    i, n = 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            piece = unescape_c(text[i + 1:j])
            if cur is not None:
                cur += piece
            elif opens_gettext(text, i):
                cur = piece
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            while j < n and text[j] != "'":
                j += 2 if text[j] == "\\" else 1
            i = j + 1
        elif c.isspace():
            i += 1
            continue
        else:
            i += 1
        if cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out


CONV = re.compile(r"%(?:%|pB|[-+ #0]*[0-9]*(?:\.[0-9]+)?"
                  r"(?:hh|h|ll|l|z|t|j|L)?[diouxXeEfgGaAcsp])")


def conv_pattern(spec):
    """A regex for what one conversion can print, or None if unknown."""
    if spec == "%%":
        return re.escape("%")
    if spec == "%pB":
        return r"\S+"                    # bfd prints the file's name
    tail = spec[-1]
    if tail == "s":
        return r".+?"
    if tail in "di":
        return r"[-+]?[0-9]+"
    if tail in "ou":
        return r"[0-9]+"
    if tail in "xX":
        return r"[0-9a-fA-F]+"
    if tail == "c":
        return r"."
    return None


def format_regex(fmt):
    """FMT as a regex over the text printf can produce from it, or None.

    White space is collapsed to single spaces first, and the manual text is
    collapsed the same way before matching, because a diagnostic reaches
    the manual wrapped to the page.  Collapsing must not strip: the space
    on either side of a conversion is part of the sentence, and losing it
    made this matcher reject three diagnostics that were quoted correctly.
    """
    fmt = re.sub(r"\s+", " ", fmt).strip()
    out, i = [], 0
    for m in CONV.finditer(fmt):
        pat = conv_pattern(m.group(0))
        if pat is None:
            return None
        out.append(re.escape(fmt[i:m.start()]))
        out.append(pat)
        i = m.end()
    out.append(re.escape(fmt[i:]))
    return "".join(out)


PREFIX = re.compile(r"^(?:Error|Warning|Fatal error|Internal error):\s+")


def instance_of(text, formats):
    """The format strings TEXT is a printed instance of."""
    hits = []
    for fmt in formats:
        rx = format_regex(fmt)
        if rx is None:
            continue
        if re.fullmatch(rx, text):
            hits.append(fmt)
    return hits


def initialiser(lines, opener):
    """The lines of the array initialiser whose head line contains OPENER."""
    out, seen = [], False
    for s in lines:
        if not seen:
            if opener in s:
                seen = True
            continue
        if s.strip() == "};":
            return out
        out.append(s)
    return out if seen else None


# ---------------------------------------------------------------- checks

PSEUDO = re.compile(r'\{\s*"([^"]+)"')
DIRECTOP = re.compile(r'\{\s*"((?:[^"\\]|\\.)*)"\s*,\s*\'(\\.|[^\'])\'\s*,'
                      r"\s*(0[xX][0-9a-fA-F]+|[0-9]+)")
RELOC_NUMBER = re.compile(r"(?<![A-Z_])RELOC_NUMBER\s*\(\s*(R_I51_[A-Z0-9_]+)")
RELOC_NAME = re.compile(r"\bR_I51_[A-Z0-9_]+")
I51_INS = re.compile(r'^I51_INS\s*\(\s*"([a-z0-9]+)"', re.M)

REG_GROUPS = [
    ("Registers and addressing modes", lambda ref: ref not in "DBU"),
    ("Register-bank byte addresses", lambda ref: ref == "U"),
    ("Byte-addressable special function registers", lambda ref: ref == "D"),
    ("Bit-addressable names", lambda ref: ref == "B"),
]

BYTE_VALUE = re.compile(r"@samp\{\.byte\s+([^}]+)\}")
HEX = re.compile(r"@code\{0[xX]([0-9a-fA-F]+)\}")


def check_directives(ck, doc, gas):
    """md_pseudo_table against the manual's Directives section."""
    body = initialiser(gas, "md_pseudo_table[] =")
    if body is None:
        return ck.true("directives: no md_pseudo_table in " + GAS, False)
    source = {m.group(1) for s in body for m in [PSEUDO.match(s.strip())] if m}
    ck.true("directives: md_pseudo_table came out empty", bool(source))

    node = doc.get("i51 Directives")
    if node is None:
        return ck.true("directives: no `i51 Directives' node in "
                       + TEXI, False)
    documented = set()
    for s in table_body(node) or []:
        m = ITEM.match(s)
        if m and m.group(1).startswith("."):
            documented.add(re.match(r"\.([a-z0-9_]+)", m.group(1)).group(1))
    # .equ and .set are named in the section's prose rather than given an
    # entry of their own, because they behave as the machine-independent
    # directives of those names.  Naming a directive counts as documenting
    # that it exists; only an @item is read back the other way.
    named = documented | {m.group(1) for m in
                          re.finditer(r"@code\{\.([a-z0-9_]+)\}",
                                      "\n".join(node))}
    ck.true("directives: the manual's table has no entries", bool(documented))
    missing = sorted(source - named)
    ck.true("directives: md_pseudo_table has %s, the manual does not name %s"
            % (", ".join(missing), "it" if len(missing) == 1 else "them"),
            not missing)
    extra = sorted(documented - source)
    ck.true("directives: the manual documents %s, md_pseudo_table has no "
            "such entry" % ", ".join(extra), not extra)
    return not missing and not extra


def directop(gas):
    """[(name, ref, value)] for the i51_directop table."""
    body = initialiser(gas, "i51_directop[] =")
    if body is None:
        return None
    out = []
    for s in body:
        m = DIRECTOP.match(s.strip())
        if m:
            out.append((m.group(1), m.group(2), int(m.group(3), 0)))
    return out


def check_operands(ck, doc, ops):
    """i51_directop against the operand names listed in i51-Regs."""
    node = doc.get("i51-Regs")
    if node is None:
        return ck.true("operands: no `i51-Regs' node in " + TEXI, False)
    body = table_body(node)
    if body is None:
        return ck.true("operands: no @table in the i51-Regs section", False)

    groups = {}
    for head, lines in table_items(body):
        names, broken = code_names(" ".join(lines))
        ck.true("operands: %s: cannot expand the range %s"
                % (head, ", ".join(broken)), not broken)
        groups[head] = names

    listed = set()
    for names in groups.values():
        listed |= names
    ck.same("operands", listed, {n for n, _r, _v in ops})

    for head, wanted in REG_GROUPS:
        if not ck.true("operands: the manual has no `%s' group" % head,
                       head in groups):
            continue
        want = {n for n, ref, _v in ops if wanted(ref)}
        absent = sorted(want - groups[head])
        ck.true("operands: %s is in i51_directop but the manual does not "
                "list it under `%s'" % (", ".join(absent), head), not absent)


def check_values(ck, doc, ops):
    """The operand values the manual states outright, against i51_directop."""
    node = doc.get("i51-Regs")
    if node is None:
        return
    text = " ".join(node)
    value = {n: v for n, _r, v in ops}
    stated = 0
    for m in BYTE_VALUE.finditer(text):
        name = undo_texinfo(m.group(1)).strip()
        h = HEX.search(text, m.end())
        if not ck.true("values: the manual says what `.byte %s' assembles to "
                       "and then gives no @code{0x..}" % name, h is not None):
            continue
        stated += 1
        want = int(h.group(1), 16)
        got = value.get(name)
        ck.true("values: the manual has `.byte %s' assembling to 0x%02X, "
                "i51_directop gives %s"
                % (name, want,
                   "no such name" if got is None else "0x%02X" % got),
                got == want)
    ck.true("values: the manual states no operand value at all - the "
            "`@samp{.byte NAME}' examples that gave them are gone", stated > 0)


def check_relocations(ck, texi, elfh):
    """RELOC_NUMBERS against every R_I51_* name the manual uses."""
    source = set(RELOC_NUMBER.findall("\n".join(elfh)))
    ck.true("relocations: no RELOC_NUMBERS in " + ELFH, bool(source))
    named = set(RELOC_NAME.findall("\n".join(texi)))
    ck.same("relocations", named, source)


def check_mnemonics(ck, texi, opch):
    """The Opcodes section's instruction list against the I51_INS rows."""
    source = set(I51_INS.findall("\n".join(opch)))
    ck.true("mnemonics: no I51_INS rows in " + OPCH, bool(source))
    blocks = [b for kind, b, _ln in examples(texi) if kind == "mnemonics"]
    if not ck.true("mnemonics: no @smallexample in %s is marked "
                   "`@c doctruth: mnemonics'" % TEXI, len(blocks) == 1):
        return
    listed = set(undo_texinfo(" ".join(blocks[0])).split())
    ck.same("mnemonics", listed, source)


def check_diagnostics(ck, texi, formats):
    """Every quoted diagnostic against the format strings of the port."""
    quoted = 0
    for kind, body, lineno in examples(texi):
        text = " ".join(body)
        if kind is None:
            ck.true("diagnostics: %s:%d: an @smallexample quotes `Error:' "
                    "and carries no `@c doctruth: diagnostic' marker"
                    % (TEXI, lineno), "Error:" not in text)
            continue
        if kind != "diagnostic":
            continue
        quoted += 1
        # A diagnostic sitting inside sample source is written as an
        # @r{...} span beside the line that provokes it; a block that is
        # nothing but the diagnostic has no span and is taken whole.
        spans = R_SPAN.findall(text)
        if spans:
            text = " ".join(spans)
        text = squeeze(PREFIX.sub("", squeeze(undo_texinfo(text))))
        ck.true("diagnostics: %s:%d: nothing in %s or %s can print\n"
                "       %s" % (TEXI, lineno, GAS, BFD, text),
                bool(instance_of(text, formats)))
    ck.true("diagnostics: %s marks no diagnostic at all" % TEXI, quoted > 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--patch",
                    default=os.path.join(here, "..", "mcs51",
                                         "additions.patch"),
                    help="the all-additions patch the port's sources live in")
    args = ap.parse_args()

    if not os.path.exists(args.patch):
        print("doctruth: no %s" % args.patch, file=sys.stderr)
        return 2
    try:
        tree = fixhunks.added_files(args.patch)
    except fixhunks.NotAllAdditions as exc:
        print("doctruth: %s: %s" % (args.patch, exc), file=sys.stderr)
        return 2
    missing = [f for f in (TEXI, GAS, BFD, ELFH, OPCH) if f not in tree]
    if missing:
        print("doctruth: %s builds no %s" % (args.patch, ", ".join(missing)),
              file=sys.stderr)
        return 2

    texi = tree[TEXI]
    doc = nodes(texi)
    formats = c_strings("\n".join(tree[GAS])) + c_strings("\n".join(tree[BFD]))

    ck = Check()
    check_directives(ck, doc, tree[GAS])
    ops = directop(tree[GAS])
    if ck.true("operands: no i51_directop table in " + GAS, ops is not None):
        check_operands(ck, doc, ops)
        check_values(ck, doc, ops)
    check_relocations(ck, texi, tree[ELFH])
    check_mnemonics(ck, texi, tree[OPCH])
    check_diagnostics(ck, texi, formats)

    print("== doctruth: %s against %s"
          % (TEXI, ", ".join((GAS, BFD, ELFH, OPCH))))
    print("   %d checks, %d nodes, %d format strings"
          % (ck.n, len(doc), len(formats)))
    if ck.fail:
        for f in ck.fail:
            print("FAIL %s" % f)
        print("\ndoctruth: FAIL (%d of %d checks)" % (len(ck.fail), ck.n))
        return 1
    print("doctruth: PASS (the manual's directive, operand, relocation and "
          "mnemonic lists and its quoted diagnostics match the source)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
