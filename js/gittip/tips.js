Gittip.tips = {};

Gittip.tips.init = function() {

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
            amount    = parseFloat($this.val(), 10) || 0,
            oldAmount = parseFloat(this.defaultValue, 10),
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

        $myTip.val($this.text().match(/\d+/)[0] / ($this.hasClass('cents') ? 100 : 1)).change();
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
            amount    = parseFloat($myTip.val(), 10),
            oldAmount = parseFloat($myTip[0].defaultValue, 10),
            tippee    = $myTip.data('tippee'),
            isAnon    = $this.hasClass('anon');

        if (amount == oldAmount)
            return;

        if(isAnon)
            alert("Please sign in first");
        else {
            // send request to change tip
            $.post('/' + tippee + '/tip.json', { amount: amount }, function(data) {
                // lock-in changes
                $myTip[0].defaultValue = amount;
                $myTip.change();

                // update display
                $('.my-total-giving').text('$'+data.total_giving);
                $('.total-receiving').text(
                    // check and see if we are on our giving page or not
                    new RegExp('/' + tippee + '/').test(window.location.href) ?
                        '$'+data.total_receiving_tippee : '$'+data.total_receiving);

                // Increment an elsewhere receiver's "people ready to give"
                if(!oldAmount)
                    $('.on-elsewhere .ready .number').text(
                        parseInt($('.on-elsewhere .ready .number').text(),10) + 1);

                // update quick stats
                $('.quick-stats a').text('$' + data.total_giving + '/wk');

                alert("Tip changed to $" + amount + "!");
            })
            .fail(function() {
                alert('Sorry, something went wrong while changing your tip. :(');
                console.log.apply(console, arguments);
            })
        }
    });

};

