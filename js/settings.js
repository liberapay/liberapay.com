Liberapay.settings = {};

Liberapay.settings.init = function() {

    // Wire up username knob.
    // ======================

    Liberapay.forms.jsEdit({
        hideEditButton: true,
        root: $('.username.js-edit'),
        success: function(d) {
            window.location.href = "/" + encodeURIComponent(d.username) + "/settings/";
            return false;
        },
    });

    // Wire up privacy settings.
    // =========================

    $('.privacy-settings input[type=checkbox]').click(function(e) {
        var neg = false;
        var field = $(e.target).data('field');
        if (field[0] == '!') {
            neg = true;
            field = field.substr(1);
        }
        jQuery.ajax(
            { url: '../privacy.json'
            , type: 'POST'
            , data: {toggle: field}
            , dataType: 'json'
            , success: function(data) {
                if (data.msg) {
                    Liberapay.notification(data.msg, 'success');
                }
                $(e.target).attr('checked', data[field] ^ neg);
            }
            , error: Liberapay.error
        });
    });

    // Wire up notification preferences
    // ================================

    $('.email-notifications input').click(function(e) {
        var event = $(e.target).attr('name');
        jQuery.ajax(
            { url: '../emails/notifications.json'
            , type: 'POST'
            , data: {event: event, enable: $(e.target).prop('checked')}
            , success: function(data) {
                Liberapay.notification(data.msg, 'success');
            }
            , error: [
                Liberapay.error,
                function(){ $(e.target).prop('checked', !$(e.target).prop('checked')) },
            ]
        });
    });


    // Wire up close knob.
    // ===================

    $('button.close-account').click(function() {
        window.location.href = './close';
    });
};
