$(document).ready(function() {
    // Wire up is_suspicious toggle.
    // =============================

    $('.is-suspicious-label input').change(function() {
        var username = $(this).attr('data-username');
        jQuery.ajax({
            url: '/' + username + '/toggle-is-suspicious.json',
            type: 'POST',
            dataType: 'json',
            success: function (data) {
                $('.avatar').toggleClass('is-suspicious', data.is_suspicious);
                $('.is-suspicious-label input').prop('checked', data.is_suspicious);
            },
            error: Liberapay.error,
        });
    });
});
