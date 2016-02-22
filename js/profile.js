Liberapay.profile = {};

Liberapay.profile.init = function() {

    // Wire up goal knob.
    // ==================

    $('#goal-custom').on('click change', function() {
        $('#goal-yes').prop('checked', true)
    });

};
