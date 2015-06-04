Liberapay.settings = {};

Liberapay.settings.post_email = function(e) {
    e.preventDefault();
    var $this = $(this);
    var action = this.className;
    var $inputs = $('.emails button, .emails input');
    console.log($this);
    var address = $this.parent().data('email') || $('input.add-email').val();

    $inputs.prop('disabled', true);

    $.ajax({
        url: '../emails/modify.json',
        type: 'POST',
        data: {action: action, address: address},
        dataType: 'json',
        success: function (msg) {
            if (msg) {
                Liberapay.notification(msg, 'success');
            }
            if (action == 'add-email') {
                $('input.add-email').val('');
                setTimeout(function(){ window.location.reload(); }, 3000);
                return;
            } else if (action == 'set-primary') {
                $('.emails li').removeClass('primary');
                $this.parent().addClass('primary');
            } else if (action == 'remove') {
                $this.parent().fadeOut();
            }
            $inputs.prop('disabled', false);
        },
        error: [
            function () { $inputs.prop('disabled', false); },
            Liberapay.error
        ],
    });
};

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


    // Wire up email addresses list.
    // =============================

    $('.emails button, .emails input').prop('disabled', false);
    $('.emails button[class]').on('click', Liberapay.settings.post_email);
    $('form.add-email').on('submit', Liberapay.settings.post_email);


    // Wire up close knob.
    // ===================

    $('button.close-account').click(function() {
        window.location.href = './close';
    });
};
