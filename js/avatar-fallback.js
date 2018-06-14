/* This is a temporary hack. There is no reliable cross-browser way to replace
 * broken images. However we can remove the need for this by proxying images:
 * https://gitlab.com/liberapay/liberapay.com/issues/202
 */
$('img.avatar').on('error', function () {
    this.src = Liberapay.avatar_default_url;
});
$('img.avatar').each(function () {
    if (this.complete && this.naturalWidth === 0) {
        this.src = Liberapay.avatar_default_url;
    }
});
