Gratipay.profile = {};

Gratipay.profile.init = function() {

    // Wire up textarea for statement.
    // ===============================

    $('textarea').focus();

    Gratipay.forms.jsEdit({root: $('.statement.js-edit')});

    $('.statement textarea').on('change keyup paste', function(){
        var changed = $(this).val() !== $(this).data('original');
        $('.statement button.save').prop('disabled', !changed);
    });

    $('.statement select.langs').on('change', function(e){
        var $form = $('.statement form');
        var $inputs = $form.find('button, input, select, textarea').filter(':not(:disabled)');
        var $textarea = $form.find('textarea');
        var $this = $(this);
        var lang = $this.val();
        if ($textarea.val() !== $textarea.data('original')) {
            if(!confirm($textarea.data('confirm-discard'))) {
                $this.val($this.data('value'));
                return;
            }
        }
        $inputs.prop('disabled', true);
        $textarea.val("Loading...");
        $.ajax({
            url: 'statement.json',
            data: {lang: lang},
            dataType: 'json',
            success: function (d) {
                $inputs.prop('disabled', false);
                $textarea.attr('lang', lang);
                $textarea.val(d.content || "");
                $textarea.data('original', $textarea.val());
                $form.find('button.save').prop('disabled', true);
                $this.data('value', lang);
            },
            error: function (e) {
                $inputs.prop('disabled', false);
                error_message = JSON.parse(e.responseText).error_message_long;
                Gratipay.notification(error_message || "Failure", 'error');
            },
        });
    });

    $('.statement button.edit').on('click', function(){
        $('.statement textarea').val('').data('original', '');
        $('.statement select.langs').change();
    });

    if ($('.statement div.view').html().trim() === '') {
        $('.statement button.edit').click();
    }

    // Wire up goal knob.
    // ==================

    Gratipay.forms.jsEdit({
        root: $('.goal.js-edit'),
        success: function(d) {
            var goal = $('input[name=goal]:checked');
            var label = $('label[for=' + goal.attr('id') + ']');
            var newtext = label.text().replace('$', d.goal_l);
            $('.goal div.view').html(newtext);
        },
    });


    // Wire up bitcoin input.
    // ======================

    $('.toggle-bitcoin').on("click", function() {
        $('.bitcoin').toggle();
        $('.toggle-bitcoin').hide();
        $('input.bitcoin').focus();
    });
    $('.bitcoin-submit')
        .on('click', '[type=submit]', function () {
            var $this = $(this);

            $this.css('opacity', 0.5);

            function success(d) {
                $('.bitcoin a.address').text(d.bitcoin_address);
                $('.toggle-bitcoin').show();
                $('.bitcoin').toggle();
                if (d.bitcoin_address === '') {
                    $('.toggle-bitcoin').text('+ Add');
                    $('.bitcoin .address').attr('href', '');
                } else {
                    $('.toggle-bitcoin').text('Edit');
                    $('.bitcoin .address').attr('href', 'https://blockchain.info/address/'+d.bitcoin_address);
                }
                $this.css('opacity', 1);
            }

            jQuery.ajax({
                    url: "bitcoin.json",
                    type: "POST",
                    dataType: 'json',
                    success: success,
                    error: function () {
                        $this.css('opacity', 1);
                        Gratipay.notification("Invalid Bitcoin address. Please try again.", 'error');
                    },
                    data: {
                        bitcoin_address: $('input.bitcoin').val()
                    }
                }
            )

            return false;
        })
        .on('click', '[type=cancel]', function () {
            $('.bitcoin').toggle();
            $('.toggle-bitcoin').show();

            return false;
        });


    // Wire up account deletion.
    // =========================

    $('.account-delete').on('click', function () {
        var $this = $(this);

        jQuery.ajax({
            url: "delete-elsewhere.json",
            type: "POST",
            dataType: "json",
            success: function ( ) {
                location.reload();
            },
            error: function (e) {
                try {
                    Gratipay.notification(JSON.parse(e.responseText).error_message_long, 'error');
                } catch(exception) {
                    Gratipay.notification("Some error occured: "+exception, 'error')
                }
            },
            data: { platform: this.dataset.platform, user_id: this.dataset.user_id }
        });

        return false;
    });

    // Wire up user_name_prompt
    // ========================

    $('.user_name_prompt').on('click', function () {
        var user_name = prompt('Please enter the name of the GitHub account you would like to connect:');
        if(!user_name) return false;
        $(this).children('[name="user_name"]').val(user_name);
    });

};
