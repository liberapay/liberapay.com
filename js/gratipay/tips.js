Gratipay.tips = {};

Gratipay.tips.init = function() {


    function start_editing_tip() {
        $('.my-tip .static-amount').hide();
        $('.my-tip input').show().focus();
        $('.my-tip .edit').hide();
        $('.my-tip .save').show();
        $('.my-tip .cancel').show();

    }
    function finish_editing_tip(newAmount) {
        if (newAmount !== undefined)
            $('form.my-tip .static-amount').text(newAmount.toFixed(2));
        $('form.my-tip .static-amount').show();
        $('form.my-tip input').hide();
        $('.my-tip .edit').show();
        $('.my-tip .save').hide();
        $('.my-tip .cancel').hide();
        $(window).off('beforeunload.tips');
    }

    $('.my-tip button.edit').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        start_editing_tip();
        return false;
    });
    $('.my-tip').submit(function(event) {
        event.preventDefault();
        var $this     = $(this),
            $input = $this.find('input'),
            amount    = parseFloat(unlocalizeDecimal($input.val()), 10),
            oldAmount = parseFloat(unlocalizeDecimal($input[0].defaultValue), 10),
            tippee    = $input.data('tippee'),
            isAnon    = $this.hasClass('anon');

        if (amount == oldAmount)
            return finish_editing_tip();

        if(isAnon)
            Gratipay.notification("Please sign in first", 'error');
        else
            Gratipay.tips.set(tippee, amount, function() {
                // lock-in changes
                $input[0].defaultValue = amount;
                $input.change();
                $input.attr('value', amount.toFixed(2));

                // Increment an elsewhere receiver's "people ready to give"
                if(!oldAmount)
                    $('.on-elsewhere .ready .number').text(
                        parseInt($('.on-elsewhere .ready .number').text(),10) + 1);

                // Use global notification system.
                Gratipay.notification( "Tip changed to $" + amount.toFixed(2) + " per week!"
                                     , 'success'
                                      );
                finish_editing_tip(amount);
            });
    });
    $('.my-tip button.cancel').click(function(e) {
        e.preventDefault();
        e.stopPropagation();
        finish_editing_tip();
        return false;
    });


    // Check the tip value on change, or 0.7 seconds after the user stops typing.
    // If the user presses enter, the browser should natively submit the form.
    // If the user presses cancel, we reset the form to its previous state.
    var timer;
    $('.my-tip input').change(checkTip).keyup(function(e) {
        if (e.keyCode === 27)                          // escape
            $(this).parents('form').trigger('reset');
        else if (e.keyCode === 38 || e.keyCode === 40) // up & down
            return; // causes inc/decrement in HTML5, triggering the change event
        else {
            clearTimeout(timer);
            timer = setTimeout(checkTip.bind(this), 700);
        }
    });
    $('input.my-tip').trigger("change");


    function checkTip() {
        var $this     = $(this),
            $parent   = $this.parents('form'),
            $confirm  = $parent.find('.save'),
            $cancel   = $parent.find('.cancel-tip'),
            amount    = parseFloat(unlocalizeDecimal($this.val()), 10) || 0,
            oldAmount = parseFloat(unlocalizeDecimal(this.defaultValue), 10),
            same      = amount === oldAmount;

        // show/hide the payment prompt
        if (amount) {
            $cancel.prop('disabled', false);
            $('#payment-prompt').addClass('needed');
        }
        else {
            $cancel.prop('disabled', true);
            $('#payment-prompt').removeClass('needed');
        }

        // prompt the user if they try leaving the page before confirming their tip
        if (same)
            $(window).off('beforeunload.tips');
        else
            $(window).on('beforeunload.tips', function() {
                var action = oldAmount ? 'changed your' : 'entered a';
                return "You "+action+" tip but it hasn't been confirmed. Are you sure you want to leave?";
            });
    }

    // Restore the tip value if stored
    if (localStorage.tipAfterSignIn) {
        var data = JSON.parse(localStorage.tipAfterSignIn);
        localStorage.removeItem('tipAfterSignIn');

        if (window.location.pathname === '/'+data.tippee+'/')
            $('.my-tip input').val(data.val).change();
    }

    // Store the tip value if the user hasn't signed in
    if ($('.sign-in').length)
        $(window).on('unload.tips', function() {
            var tip = $('.my-tip input');
            if (tip.parents('form').hasClass('changed'))
                localStorage.tipAfterSignIn = JSON.stringify({
                    tippee: tip.data('tippee'), val: tip.val()
                });
        });
};


Gratipay.tips.initSupportGratipay = function() {
    $('.support-gratipay button').click(function() {
        var amount = parseFloat($(this).attr('data-amount'), 10);
        Gratipay.tips.set('Gratipay', amount, function() {
            Gratipay.notification("Thank you so much for supporting Gratipay! :D", 'success');
            $('.support-gratipay').slideUp();

            // If you're on your own giving page ...
            var tip_on_giving = $('.my-tip[data-tippee="Gratipay"]');
            if (tip_on_giving.length > 0) {
                tip_on_giving[0].defaultValue = amount;
                tip_on_giving.attr('value', amount.toFixed(2));
            }

            // If you're on Gratipay's profile page or your own profile page,
            // updating the proper giving/receiving amounts is apparently taken
            // care of in Gratipay.tips.set.

        });
    });

    $('.support-gratipay .no-thanks').click(function(event) {
        event.preventDefault();
        jQuery.post('/ride-free.json')
            .success(function() { $('.support-gratipay').slideUp(); })
            .fail(function() { Gratipay.notification("Sorry, there was an error.", "failure"); })
    });
};


Gratipay.tips.set = function(tippee, amount, callback) {

    // send request to change tip
    $.post('/' + tippee + '/tip.json', { amount: amount }, function(data) {
        if (callback) callback(data);

        // update display
        $('.my-total-giving').text(data.total_giving_l);
        $('.total-receiving').text(
            // check and see if we are on our giving page or not
            new RegExp('/' + tippee + '/').test(window.location.href) ?
                data.total_receiving_tippee_l :
                data.total_receiving_l
        );
    })
    .fail(function(e) {
        Gratipay.notification('Sorry, something went wrong while changing your tip: ' + e.responseJSON.error_message_long + '. :(', 'error');
        console.log.apply(console, arguments);
    });
};
