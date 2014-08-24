Gratipay.tips = {};

Gratipay.tips.init = function() {

    // Check the tip value on change, or 0.7 seconds after the user stops typing.
    // If the user presses enter, the browser should natively submit the form.
    // If the user presses cancel, we reset the form to its previous state.
    var timer;
    $('input.my-tip').change(checkTip).keyup(function(e) {
        if (e.keyCode === 27)                          // escape
            $(this).parents('form').trigger('reset');
        else if (e.keyCode === 38 || e.keyCode === 40) // up & down
            return; // causes inc/decrement in HTML5, triggering the change event
        else {
            clearTimeout(timer);
            timer = setTimeout(checkTip.bind(this), 700);
        }
    });

    function checkTip() {
        var $this     = $(this),
            $parent   = $this.parents('form'),
            $confirm  = $parent.find('.confirm-tip'),
            amount    = parseFloat(unlocalizeDecimal($this.val()), 10) || 0,
            oldAmount = parseFloat(unlocalizeDecimal(this.defaultValue), 10),
            max       = parseFloat($this.prop('max')),
            min       = parseFloat($this.prop('min')),
            inBounds  = amount <= max && amount >= min,
            same      = amount === oldAmount;

        // dis/enables confirm button as needed
        $confirm.prop('disabled', inBounds ? same : true);

        if (same)
            $parent.removeClass('changed');
        else
            $parent.addClass('changed');

        // show/hide the payment prompt
        if (amount)
            $('#payment-prompt').addClass('needed');
        else
            $('#payment-prompt').removeClass('needed');

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
            $('input.my-tip').val(data.val).change();
    }

    // Store the tip value if the user hasn't signed in
    if ($('.sign-in').length)
        $(window).on('unload.tips', function() {
            var tip = $('input.my-tip');
            if (tip.parents('form').hasClass('changed'))
                localStorage.tipAfterSignIn = JSON.stringify({
                    tippee: tip.data('tippee'), val: tip.val()
                });
        });

    $('.my-tip .cancel-tip').click(function(event) {
        event.preventDefault();

        $(this).parents('form').trigger('reset');
    });

    $('.my-tip .tip-suggestions a').click(function(event) {
        event.preventDefault();

        var $this  = $(this),
            $myTip = $this.parents('form').find('.my-tip');

        var newTip = $this.text().match(/\d+/)[0] / ($this.hasClass('cents') ? 100 : 1);
        $myTip.val(localizeDecimal(newTip.toString())).change();
    });

    $('form.my-tip').on('reset', function() {
        $(this).removeClass('changed');
        $(this).find('.confirm-tip').prop('disabled', true);
        $(window).off('beforeunload.tips');
    });

    $('form.my-tip').submit(function(event) {
        event.preventDefault();
        var $this     = $(this),
            $myTip    = $this.find('.my-tip'),
            amount    = parseFloat(unlocalizeDecimal($myTip.val()), 10),
            oldAmount = parseFloat(unlocalizeDecimal($myTip[0].defaultValue), 10),
            tippee    = $myTip.data('tippee'),
            isAnon    = $this.hasClass('anon');

        if (amount == oldAmount)
            return;

        if(isAnon)
            Gratipay.notification("Please sign in first", 'error');
        else
            Gratipay.tips.set(tippee, amount, function() {
                // lock-in changes
                $myTip[0].defaultValue = amount;
                $myTip.change();
                $myTip.attr('value', amount.toFixed(2));

                // Increment an elsewhere receiver's "people ready to give"
                if(!oldAmount)
                    $('.on-elsewhere .ready .number').text(
                        parseInt($('.on-elsewhere .ready .number').text(),10) + 1);

                // Use global notification system.
                Gratipay.notification("Tip changed to $" + amount.toFixed(2) + "!", 'success');
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
        $('.my-total-giving').text('$' + localizeDecimal(data.total_giving));
        $('.total-receiving').text(
            // check and see if we are on our giving page or not
            new RegExp('/' + tippee + '/').test(window.location.href) ?
                '$' + localizeDecimal(data.total_receiving_tippee) :
                '$' + localizeDecimal(data.total_receiving));

        // update quick stats
        $('.quick-stats a').text('$' + localizeDecimal(data.total_giving) + '/wk');
    })
    .fail(function() {
        Gratipay.notification('Sorry, something went wrong while changing your tip. :(', 'error');
        console.log.apply(console, arguments);
    });
};
