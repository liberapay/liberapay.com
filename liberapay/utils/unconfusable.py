from confusable_homoglyphs import confusables

def unconfusable_string(name):
    unconfusable_name = ''
    for c in name:
        confusable = confusables.is_confusable(c, preferred_aliases=['COMMON', 'LATIN'])
        if confusable:
            # if the character is confusable we replace it with the first prefered alias
            c = confusable[0]['homoglyphs'][0]['c']
        unconfusable_name += c
    return unconfusable_name
