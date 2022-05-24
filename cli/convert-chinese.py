from babel.messages.pofile import read_po, write_po
import opencc


# Paths to the Traditional and Simplified Chinese translation files
t_path = 'i18n/core/zh_Hant.po'
s_path = 'i18n/core/zh_Hans.po'

# Initialize the converter from traditional to simplified
t2s_converter = opencc.OpenCC('t2s.json')
# Initialize the converter from simplified to traditional
s2t_converter = opencc.OpenCC('s2t.json')

# Open and parse the translation (PO) files
with open(t_path, 'rb') as po:
    t_catalog = read_po(po, locale='zh_Hant')
with open(s_path, 'rb') as po:
    s_catalog = read_po(po, locale='zh_Hans')

# Complete each catalog with the translations from the other one
s2t_count = t2s_count = 0
for s_msg in s_catalog:
    if not s_msg.id:
        continue
    t_msg = t_catalog._messages[t_catalog._key_for(s_msg.id)]
    if any(t_msg.string) and (not any(s_msg.string) or s_msg.fuzzy and not t_msg.fuzzy):
        if isinstance(s_msg.string, tuple):
            s_msg.string = tuple(map(t2s_converter.convert, t_msg.string))
        else:
            s_msg.string = t2s_converter.convert(t_msg.string)
        t2s_count += 1
        if t_msg.fuzzy:
            s_msg.flags.add('fuzzy')
    elif any(s_msg.string) and (not any(t_msg.string) or t_msg.fuzzy and not s_msg.fuzzy):
        if isinstance(s_msg.string, tuple):
            t_msg.string = tuple(map(s2t_converter.convert, s_msg.string))
        else:
            t_msg.string = s2t_converter.convert(s_msg.string)
        s2t_count += 1
        if s_msg.fuzzy:
            t_msg.flags.add('fuzzy')

# Save the changes
if s2t_count:
    with open(t_path, 'wb') as po:
        write_po(po, t_catalog, width=0)
    print(f"added {s2t_count} machine-converted translations to {t_path}")
if t2s_count:
    with open(s_path, 'wb') as po:
        write_po(po, s_catalog, width=0)
    print(f"added {t2s_count} machine-converted translations to {s_path}")
