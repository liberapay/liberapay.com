import opencc
from babel.messages.pofile import read_po, write_po


# Converts traditional to simplified
t2s_converter = opencc.OpenCC('t2s.json')
# Converts simplified to traditional
s2t_converter = opencc.OpenCC('s2t.json')

# Create path variables
t_path = '../i18n/core/zh_Hant.po'
s_path = '../i18n/core/zh_Hans.po'

# Open Traditional Chinese po file and create babel catalog
with open(t_path, 'rb') as pot:
    t_catalog = read_po(pot, locale='zh_Hant')

# Open Simplified Chinese po file and create babel catalog
with open(s_path, 'rb') as pot:
    s_catalog = read_po(pot, locale='zh_Hans')

# If message string is in t_catalog and not s_catalog, convert and insert into s_catalog
for s_message in s_catalog:
    if not s_message.string:
        for t_message in t_catalog:
            if t_message.id == s_message.id:
                s_message.string = t2s_converter.convert(t_message.string)

# Write result to zh_Hans.po
with open(s_path, 'wb') as pot:
    write_po(pot, s_catalog, width=0)    

# If message string is in s_catalog and not t_catalog, convert and insert into t_catalog
for t_message in t_catalog:
    if not t_message.string:
        for s_message in s_catalog:
            if s_message.id == t_message.id:
                t_message.string = s2t_converter.convert(s_message.string) 

# Write result to zh_Hant.po
with open(t_path, 'wb') as pot:
    write_po(pot, t_catalog, width=0)  