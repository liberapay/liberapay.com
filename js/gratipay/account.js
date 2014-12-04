Gratipay.account = {};

Gratipay.account.init = function() {

    // Wire up username knob.
    // ======================

    $('form.username button.edit').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        $('.username button.edit').hide();
        $('.username button.save').show();
        $('.username button.cancel').show();
        $('.username span.view').hide();
        $('.username input').show().focus();
        $('.username .warning').show();
        return false;
    });
    $('form.username').submit(function(e) {
        e.preventDefault();

        $('#save-username').css('opacity', 0.5);

        function success(d) {
            window.location.href = "/" + encodeURIComponent(d.username) + "/";
        }
        function error(e) {
            $('#save-username').css('opacity', 1);
            Gratipay.notification(JSON.parse(e.responseText).error_message_long, 'error');
        }
        jQuery.ajax(
            { url: "../username.json"
            , type: "POST"
            , dataType: 'json'
            , data: { username: $('input[name=username]').val() }
            , success: success
            , error: error
             }
        );
        return false;
    });
    $('.username button.cancel').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_username();
        return false;
    });
    function finish_editing_username() {
        $('.username button.edit').show();
        $('.username button.save').hide();
        $('.username button.cancel').hide();
        $('.username span.view').show();
        $('.username input').hide();
        $('.username .warning').hide();
    }


    // Wire up aggregate giving knob.
    // ==============================

    $('.anonymous-giving input').click(function() {
        jQuery.ajax(
            { url: '../anonymous.json'
            , type: 'POST'
            , data: {toggle: 'giving'}
            , dataType: 'json'
            , success: function(data) {
                $('.anonymous-giving input').attr('checked', data.giving);
            }
            , error: function() {
                Gratipay.notification("Failed to change your anonymity preference. Please try again.", 'error');
            }
        });
    });


    // Wire up aggregate receiving knob.
    // ==============================

    $('.anonymous-receiving input').click(function() {
        jQuery.ajax(
            { url: '../anonymous.json'
            , type: 'POST'
            , data: {toggle: 'receiving'}
            , dataType: 'json'
            , success: function(data) {
                $('.anonymous-receiving input').attr('checked', data.receiving);
            }
            , error: function() {
                Gratipay.notification("Failed to change your anonymity preference. Please try again.", 'error');
            }
        });
    });

    // Wire up API Key
    // ===============
    //
    var callback = function(data) {
        $('.api-key span').text(data.api_key || 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx');

        if (data.api_key) {
            $('.api-key').data('api-key', data.api_key);
            $('.api-key .show').hide();
            $('.api-key .hide').show();
        } else {
            $('.api-key .show').show();
            $('.api-key .hide').hide();
        }
    }

    $('.api-key').on('click', '.show', function() {
        if ($('.api-key').data('api-key'))
            callback({api_key: $('.api-key').data('api-key')});
        else
            $.get('../api-key.json', {action: 'show'}, callback);
    })
    .on('click', '.hide', callback)
    .on('click', '.recreate', function() {
        $.post('../api-key.json', {action: 'show'}, callback);
    });

    // Wire up email addresses list.
    // =============================
    function post_email(e) {
        e.preventDefault();
        var $this = $(this);
        var action = this.className;
        var $inputs = $('.emails button, .emails input');
        var address = $this.parent().data('email') || $('input.add-email').val();

        $inputs.prop('disabled', true);

        $.ajax({
            url: '../email.json',
            type: 'POST',
            data: {action: action, address: address},
            dataType: 'json',
            success: function (data) {
                $inputs.prop('disabled', false);
                if (action == 'add-email') {
                    $('input.add-email').val('');
                    window.location.reload();
                } else if (action == 'set-primary') {
                    $('.emails li').removeClass('primary');
                    $this.parent().addClass('primary');
                } else if (action == 'remove') {
                    $this.parent().fadeOut();
                } else {
                    Gratipay.notification("Success" , 'success');
                }
            },
            error: function (e) {
                $inputs.prop('disabled', false);
                error_message = JSON.parse(e.responseText).error_message_long;
                Gratipay.notification(error_message || "Failure", 'error');
            },
        });
    }
    $('.emails button, .emails input').prop('disabled', false);
    $('.emails button[class]').on('click', post_email);
    $('form.add-email').on('submit', post_email);


    // Wire up close knob.
    // ===================

    $('button.close-account').click(function() {
        window.location.href = './close';
    });
};
