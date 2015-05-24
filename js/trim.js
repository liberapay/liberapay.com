// strips Unicode & non-printable characters, then leading/trailing whitespace
Liberapay.trim = function(s) {
    return s.replace(/[^\x20-\x7F]/g, '').replace(/^\s+|\s+$/g, '');
}
