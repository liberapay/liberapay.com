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
for s_msg in s_catalog:
    if not s_msg.id:
        continue
    t_msg = t_catalog._messages[t_catalog._key_for(s_msg.id)]
    if t_msg.string and (not s_msg.string or s_msg.fuzzy and not t_msg.fuzzy):
        s_msg.string = t2s_converter.convert(t_msg.string)
        if t_msg.fuzzy:
            s_msg.flags.add('fuzzy')
    elif s_msg.string and (not t_msg.string or t_msg.fuzzy and not s_msg.fuzzy):
        t_msg.string = s2t_converter.convert(s_msg.string)
        if s_msg.fuzzy:
            t_msg.flags.add('fuzzy')

# Save the changes
with open(t_path, 'wb') as po:
    write_po(po, t_catalog, width=0)
with open(s_path, 'wb') as po:
    write_po(po, s_catalog, width=0)
