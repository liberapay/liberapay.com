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

    function update_members_button(is_plural) {
        if (is_plural) {
            $("#members-button").removeClass("hidden")
        } else {
            $("#members-button").addClass("hidden")
        }
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

        var is_plural = jQuery("#statement-select").val() === "plural";
        $('.statement button.save').text('Saving ...');

        function success(d) {
            $('.statement .view span').html(d.statement);
            var number = $('.statement select').val();
            Gittip.profile.toNumber(number);
            finish_editing_statement();
            update_members_button(is_plural);
        }
        function error(e) {
            $('.statement button.save').text('Save');
            Gittip.notification(JSON.parse(e.responseText).error_message_long, 'error');
        }
        jQuery.ajax(
            { url: "statement.json"
            , type: "POST"
            , success: success
            , error: error
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
                    Gittip.notification("Failed to change your funding goal. Please try again.", 'error');
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


    // Wire up bitcoin input.
    // ======================

    $('.bitcoin').on("click", ".toggle-bitcoin", function()
    {
        // "Add bitcoin address" text or existing
        // bitcoin address was clicked, show the text box
        $('.bitcoin').toggle();
        $('input.bitcoin').focus();
    });
    $('.bitcoin-submit')
        .on('click', '[type=submit]', function () {
            var $this = $(this);

            $this.text('Saving...');

            function success(d) {
                $('a.bitcoin').text(d.bitcoin_address);
                $('.bitcoin').toggle();
                if (d.bitcoin_address === '') {
                    html = "<span class=\"none\">None</span>"
                    html += "<button class=\"toggle-bitcoin\">+ Add</button>";
                } else {
                    html = "<a class=\"address\" rel=\"me\" href=\"https://blockchain.info/address/";
                    html += d.bitcoin_address + "\">" + d.bitcoin_address + "</a>";
                    html += "<button class=\"toggle-bitcoin\">Edit</button>";
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
                        Gittip.notification("Invalid Bitcoin address. Please try again.", 'error');
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
                    Gittip.notification(JSON.parse(e.responseText).error_message_long, 'error');
                } catch(exception) {
                    Gittip.notification("Some error occured: "+exception, 'error')
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
