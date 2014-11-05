Gratipay.profile = {};

Gratipay.profile.init = function() {
    ////////////////////////////////////////////////////////////
    //                                                         /
    // XXX This is ripe for refactoring. I ran out of steam. :-/
    //                                                         /
    ////////////////////////////////////////////////////////////

    // Wire up textarea for statement.
    // ===============================

    $('textarea').focus();
    function start_editing_statement() {
        var h = $('.statement div.view').height();
        h = Math.max(h, 128);
        $('.statement textarea').height(h);

        $('.statement button.edit').hide();
        $('.statement button.save').show();
        $('.statement button.cancel').show();
        $('.statement div.view').hide();
        $('.statement div.edit').show(0, function() {
            $('.statement textarea').focus();
        });
    }

    if ($('.statement textarea').val() === '') {
        start_editing_statement();
    }
    $('.statement button.edit').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        start_editing_statement();
        return false;
    });
    $('form.statement').submit(function(e) {
        e.preventDefault();

        $('.statement button.save').css('opacity', 0.5);

        function success(d) {
            $('.statement .view').html(d.statement);
            finish_editing_statement();
        }
        function error(e) {
            $('.statement button.save').css('opacity', 1);
            Gratipay.notification(JSON.parse(e.responseText).error_message_long, 'error');
        }
        jQuery.ajax(
            { url: "statement.json"
            , type: "POST"
            , success: success
            , error: error
            , data: { statement: $('.statement textarea').val() }
             }
        );
        return false;
    });
    $('.statement button.cancel').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_statement();
        return false;
    });
    function finish_editing_statement() {
        $('.statement button.edit').show();
        $('.statement button.save').hide().css('opacity', 1);
        $('.statement button.cancel').hide();
        $('.statement div.view').show();
        $('.statement div.edit').hide();
        $('.statement .warning').hide();
    }


    // Wire up goal knob.
    // ==================

    $('.goal button.edit').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        $('.goal div.view').hide();
        $('.goal table.edit').show();
        $('.goal button.edit').hide();
        $('.goal button.save').show();
        $('.goal button.cancel').show();
        return false;
    });
    $('form.goal').submit(function(e) {
        e.preventDefault();

        var goal = $('input[name=goal]:checked');

        if(goal.val() === '-1') {
            var r = confirm(
                'Warning: Doing this will remove all the tips you are currently receiving.\n\n'+
                'That cannot be undone!'
            );
            if(!r) return;
        }

        $('.goal button.save').css('opacity', 0.5);

        function success(d) {
            var label = $('label[for=' + goal.attr('id') + ']');
            var newtext = '';
            if (label.length === 1)
                newtext = label.html();
            else
            {   // custom goal is wonky
                newtext = label.html();
                newtext = newtext.replace('$', '$' + d.goal);
                newtext += $(label.get(1)).html();
            }

            if (parseFloat(d.goal) > 0)
                $('input[name=goal_custom]').val(d.goal);
            $('.goal div.view').html(newtext);
            finish_editing_goal();
        }
        jQuery.ajax(
            { url: "goal.json"
            , type: "POST"
            , dataType: 'json'
            , data: { goal: goal.val()
                    , goal_custom: $('[name=goal_custom]').val()
                     }
            , success: success
            , error: function() {
                    $('.goal button.save').css('opacity', 1);
                    Gratipay.notification("Failed to change your funding goal. Please try again.", 'error');
                }
             }
        );
        return false;
    });
    $('.goal button.cancel').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_goal();
        return false;
    });
    function finish_editing_goal() {
        $('.goal div.view').show();
        $('.goal table.edit').hide();
        $('.goal button.edit').show();
        $('.goal button.save').hide().css('opacity', 1);
        $('.goal button.cancel').hide();
    }


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
