import re


ternary_re = re.compile(r'^(.+?) *\? *(.+?) *: *(.+?)$')
and_re = re.compile(r' *&& *')
or_re = re.compile(r' *\|\| *')


def strip_parentheses(s):
    s = s.strip()
    if s[:1] == '(' and s[-1:] == ')':
        s = s[1:-1].strip()
    return s


def ternary_sub(m):
    g1, g2, g3 = m.groups()
    return '%s if %s else %s' % (g2, g1, ternary_re.sub(ternary_sub, strip_parentheses(g3)))


def get_function_from_rule(rule):
    rule = ternary_re.sub(ternary_sub, strip_parentheses(rule))
    rule = and_re.sub(' and ', rule)
    rule = or_re.sub(' or ', rule)
    return eval('lambda n: ' + rule, {'__builtins__': {}})
