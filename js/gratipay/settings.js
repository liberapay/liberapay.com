Gratipay.settings = {};

Gratipay.settings.post_email = function(e) {
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
                Gratipay.notification(msg, 'success');
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
            Gratipay.error
        ],
    });
};

Gratipay.settings.init = function() {

    // Wire up username knob.
    // ======================

    Gratipay.forms.jsEdit({
        hideEditButton: true,
        root: $('.username.js-edit'),
        success: function(d) {
            window.location.href = "/" + encodeURIComponent(d.username) + "/settings/";
            return false;
        },
    });


    // Wire up account type knob.
    // ==========================

    $('.number input').click(function(e) {
        var $input = $(this);

        e.preventDefault();

        function post(confirmed) {
            jQuery.ajax({
                url: '../number.json',
                type: 'POST',
                data: {
                    number: $input.val(),
                    confirmed: confirmed
                },
                success: function(data) {
                    if (data.confirm) {
                        if (confirm(data.confirm)) return post(true);
                        return;
                    }
                    if (data.number) {
                        $input.prop('checked', true);
                        Gratipay.notification(data.msg || "Success", 'success');
                        $('li.members').toggleClass('hidden', data.number !== 'plural');
                    }
                },
                error: Gratipay.error,
            });
        }
        post();
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
                    Gratipay.notification(data.msg, 'success');
                }
                $(e.target).attr('checked', data[field] ^ neg);
            }
            , error: Gratipay.error
        });
    });

    // Wire up notification preferences
    // ================================

    $('.email-notifications input').click(function(e) {
        var field = $(e.target).data('field');
        var bits = $(e.target).data('bits') || 1;
        jQuery.ajax(
            { url: '../emails/notifications.json'
            , type: 'POST'
            , data: {toggle: field, bits: bits}
            , dataType: 'json'
            , success: function(data) {
                Gratipay.notification(data.msg, 'success');
                $(e.target).attr('checked', data.new_value & bits)
            }
            , error: [
                Gratipay.error,
                function(){ $(e.target).attr('checked', !$(e.target).attr('checked')) },
            ]
        });
    });

    // Wire up API Key
    // ===============

    var callback = function(data) {
        var val = data.api_key || 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx';
        $('.api-credentials .key span').text(val);

        if (data.api_key) {
            $('.api-credentials').data('key', data.api_key);
            $('.api-credentials .show').hide();
            $('.api-credentials .hide').show();
        } else {
            $('.api-credentials .show').show();
            $('.api-credentials .hide').hide();
        }
    }

    $('.api-credentials').on('click', '.show', function() {
        if ($('.api-credentials').data('key'))
            callback({api_key: $('.api-credentials').data('key')});
        else
            $.get('../api-key.json', {action: 'show'}, callback);
    })
    .on('click', '.hide', callback)
    .on('click', '.recreate', function() {
        $.post('../api-key.json', {action: 'show'}, callback);
    });


    // Wire up email addresses list.
    // =============================

    $('.emails button, .emails input').prop('disabled', false);
    $('.emails button[class]').on('click', Gratipay.settings.post_email);
    $('form.add-email').on('submit', Gratipay.settings.post_email);


    // Wire up close knob.
    // ===================

    $('button.close-account').click(function() {
        window.location.href = './close';
    });
};
