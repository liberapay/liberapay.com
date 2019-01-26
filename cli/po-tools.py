import sys

from babel.messages.pofile import read_po, write_po


if sys.argv[1] == 'reflag':
    # This adds the `python-brace-format` flag to messages that contain braces
    # https://github.com/python-babel/babel/issues/333
    pot_path = sys.argv[2]
    print('rewriting PO template file', pot_path)
    # read PO file
    with open(pot_path, 'rb') as pot:
        catalog = read_po(pot)
    # tweak message flags
    for m in catalog:
        msg = m.id
        contains_brace = any(
            '{' in s for s in (msg if isinstance(msg, tuple) else (msg,))
        )
        if contains_brace:
            m.flags.add('python-brace-format')
        m.flags.discard('python-format')
    # write back
    with open(pot_path, 'wb') as pot:
        write_po(pot, catalog, width=0)

else:
    print("unknown command")
    raise SystemExit(1)
