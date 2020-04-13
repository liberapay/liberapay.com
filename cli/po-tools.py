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

elif sys.argv[1] == 'copy':
    po_path = sys.argv[2]
    old_msg = sys.argv[3]
    new_msg = sys.argv[4]
    print('copying a message in PO file', po_path)
    # read PO file
    lang = po_path.rsplit('/', 1)[-1].split('.', 1)[0]
    with open(po_path, 'rb') as po:
        catalog = read_po(po, locale=lang)
    # copy old msg
    m = catalog.get(old_msg)
    if m.string:
        assert not isinstance(m.id, tuple)
        catalog.add(new_msg, m.string, flags=['fuzzy'])
        # write back
        with open(po_path, 'wb') as po:
            write_po(po, catalog, width=0)

elif sys.argv[1] == 'fuzz':
    po_path = sys.argv[2]
    old_msg = sys.argv[3]
    new_msg = sys.argv[4]
    new_msg_plural = sys.argv[5] if len(sys.argv) > 5 else None
    print('switching a message in PO file', po_path)
    # read PO file
    lang = po_path.rsplit('/', 1)[-1].split('.', 1)[0]
    with open(po_path, 'rb') as po:
        catalog = read_po(po, locale=lang)
    # replace old msg
    m = catalog.get(old_msg)
    if any(m.string):
        m.flags.add('fuzzy')
    if new_msg_plural:
        assert isinstance(m.id, tuple)
        m.id = (new_msg, new_msg_plural)
    else:
        assert not isinstance(m.id, tuple)
        m.id = new_msg
    # write back
    with open(po_path, 'wb') as po:
        write_po(po, catalog, width=0)

elif sys.argv[1] == 'pluralize':
    po_path = sys.argv[2]
    old_msg = sys.argv[3]
    new_msg = (sys.argv[4], sys.argv[5])
    print('pluralizing a message in PO file', po_path)
    # read PO file
    lang = po_path.rsplit('/', 1)[-1].split('.', 1)[0]
    with open(po_path, 'rb') as po:
        catalog = read_po(po, locale=lang)
    # replace old msg
    m = catalog.get(old_msg)
    if m.string:
        m.id = new_msg
        assert not isinstance(m.string, tuple)
        if m.string and catalog.num_plurals != 1:
            m.flags.add('fuzzy')
        m.string = (m.string,) * catalog.num_plurals
        # write back
        with open(po_path, 'wb') as po:
            write_po(po, catalog, width=0)

elif sys.argv[1] == 'unflag-empty-fuzzy':
    po_path = sys.argv[2]
    print('removing fuzzy flags on empty messages in PO file', po_path)
    # read PO file
    lang = po_path.rsplit('/', 1)[-1].split('.', 1)[0]
    with open(po_path, 'rb') as po:
        catalog = read_po(po, locale=lang)
    # replace old msg
    for m in catalog:
        if m.fuzzy and not m.string:
            m.flags.discard('fuzzy')
        msg = m.id
        contains_brace = any(
            '{' in s for s in (msg if isinstance(msg, tuple) else (msg,))
        )
        if contains_brace:
            m.flags.add('python-brace-format')
        m.flags.discard('python-format')
    # write back
    with open(po_path, 'wb') as po:
        write_po(po, catalog, width=0)

else:
    print("unknown command")
    raise SystemExit(1)
