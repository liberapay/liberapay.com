Gittip.profile = {};

Gittip.profile.toNumber = function(number) {
    if (number == 'plural')
        Gittip.profile.toPlural();
    else if (number == 'singular')
        Gittip.profile.toSingular();
};

Gittip.profile.toPlural = function() {
    $('.i-am').text('We are');
    $('.i-m').text("We're");
    $('.my').text("Our");
};

Gittip.profile.toSingular = function() {
    $('.i-am').text('I am');
    $('.i-m').text("I'm");
    $('.my').text("My");
};

Gittip.profile.init = function() {
    ////////////////////////////////////////////////////////////
    //                                                         /
    // XXX This is ripe for refactoring. I ran out of steam. :-/
    //                                                         /
    ////////////////////////////////////////////////////////////


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

        $('#save-username').text('Saving ...');

        function success(d) {
            window.location.href = "/" + encodeURIComponent(d.username) + "/";
        }
        function error(e) {
            $('#save-username').text('Save');
            alert(JSON.parse(e.responseText).error_message_long);
        }
        jQuery.ajax(
            { url: "username.json"
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

        $('.statement button.save').text('Saving ...');

        function success(d) {
            $('.statement .view span').html(d.statement);
            var number = $('.statement select').val();
            Gittip.profile.toNumber(number);
            finish_editing_statement();
        }
        jQuery.ajax(
            { url: "statement.json"
            , type: "POST"
            , success: success
            , data: { statement: $('.statement textarea').val()
                    , number: $('.statement select').val()
                     }
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
        $('.statement button.save').hide().text('Save');
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

        $('.goal button.save').text('Saving ...');

        var goal = $('input[name=goal]:checked');

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
                    $('.goal button.save').text('Save');
                    alert("Failed to change your funding goal. Please try again.");
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
        $('.goal button.save').hide().text('Save');
        $('.goal button.cancel').hide();
    }


    // Wire up aggregate giving knob.
    // ==============================

    $('.anonymous-giving input').click(function() {
        jQuery.ajax(
            { url: 'anonymous.json'
            , type: 'POST'
            , data: {toggle: 'giving'}
            , dataType: 'json'
            , success: function(data) {
                $('.anonymous-giving input').attr('checked', data.giving);
            }
            , error: function() {
                    alert("Failed to change your anonymity preference. Please try again.");
                }
             }
        );
    });


    // Wire up aggregate receiving knob.
    // ==============================

    $('.anonymous-receiving input').click(function() {
        jQuery.ajax(
            { url: 'anonymous.json'
            , type: 'POST'
            , data: {toggle: 'receiving'}
            , dataType: 'json'
            , success: function(data) {
                $('.anonymous-receiving input').attr('checked', data.receiving);
            }
            , error: function() {
                    alert("Failed to change your anonymity preference. Please try again.");
                }
             }
        );
    });


    // Wire up API Key
    // ===============
    //
    $('.api-key')
        .data('callback', function (data) {
            $('.api-key span').text(data.api_key || 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx');

            if (data.api_key) {
                $('.api-key').data('api-key', data.api_key);
                $('.api-key .show')
                    .text('Hide Key')
                    .toggleClass('show hide');
            }
            else
                $('.api-key .hide')
                    .text('Show Key')
                    .toggleClass('show hide');
        })
        .on('click', '.show', function () {
            if ($('.api-key').data('api-key'))
                return $('.api-key').data('callback')({ api_key: $('.api-key').data('api-key') });

            $.get('api-key.json', { action: 'show' }, $('.api-key').data('callback'));
        })
        .on('click', '.hide', $('.api-key').data('callback'))
        .on('click', '.recreate', function () {
            $.post('api-key.json', { action: 'show' }, $('.api-key').data('callback'));
        });


    $('.bitcoin').on("click", "a.toggle-bitcoin", function()
    {
        // "Add bitcoin address" text or existing
        // bitcoin address was clicked, show the text box
        $('.bitcoin').toggle();
        $('input.bitcoin').focus();
    });

    // Wire up bitcoin input.
    $('.bitcoin-submit')
        .on('click', '[type=submit]', function () {
            var $this = $(this);

            $this.text('Saving...');

            function success(d) {
                $('a.bitcoin').text(d.bitcoin_address);
                $('.bitcoin').toggle();
                if (d.bitcoin_address === '') {
                    html = "Add a <a href=\"javascript:;\" class=\"toggle-bitcoin\">Bitcoin address</a>.";
                } else {
                    html = "<a rel=\"me\" href=\"http://blockchain.info/address/";
                    html += d.bitcoin_address + "\">" + d.bitcoin_address + "</a>";
                    html += "<div class=\"edit-bitcoin\"><a href=\"javascript:;\" class=\"toggle-bitcoin\">Edit</a> bitcoin address ";
                    html += "</div>";
                }
                $('div.bitcoin').html(html);
                $this.text('Save');
            }

            jQuery.ajax({
                    url: "bitcoin.json",
                    type: "POST",
                    dataType: 'json',
                    success: success,
                    error: function () {
                        $this.text('Save');
                        alert("Invalid Bitcoin address. Please try again." );
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
                    alert(JSON.parse(e.responseText).error_message_long);
                } catch(exception) {
                    alert("Some error occured: "+exception)
                }
            },
            data: { platform: this.dataset.platform, user_id: this.dataset.user_id }
        });

        return false;
    });
};
