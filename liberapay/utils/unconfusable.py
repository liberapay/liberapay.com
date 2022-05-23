from confusable_homoglyphs import confusables

# Convert an Unicode string to its equivalent replacing all confusable homoglyphs
# to its common/latin equivalent
def unconfusable_string(s):
    unconfusable_string = ''
    for c in s:
        confusable = confusables.is_confusable(c, preferred_aliases=['COMMON', 'LATIN'])
        if confusable:
            # if the character is confusable we replace it with the first prefered alias
            c = confusable[0]['homoglyphs'][0]['c']
        unconfusable_string += c
    return unconfusable_string
