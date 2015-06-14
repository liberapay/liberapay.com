Liberapay.profile = {};

Liberapay.profile.init = function() {

    // Wire up goal knob.
    // ==================

    $('#goal-custom').on('click change', function() {
        $('#goal-yes').prop('checked', true)
    });

    // Wire up user_name_prompt
    // ========================

    $('form.user_name_prompt').submit(function () {
        var user_name = prompt($(this).data('msg'));
        if(!user_name) return false;
        $(this).children('[name="user_name"]').val(user_name);
    });

};
