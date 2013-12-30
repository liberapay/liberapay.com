Gittip.tips = {};

Gittip.tips.init = function() {

    // Check the tip value on change, or 0.7 seconds after the user stops typing.
    // If the user types enter or escape, confirm or cancel the tip as appropriate.
    var timer;
    $('input.my-tip:not(.anon)').change(checkTip).keyup(function(e) {
        if (e.keyCode === 27)                     // escape
            checkTip.call(this, e, 'cancel')
        else if (e.keyCode === 38 || e.keyCode === 40) // up & down
            return; // causes inc/decrement in HTML5, triggering the change event
        else {
            clearTimeout(timer);
            timer = setTimeout(checkTip.bind(this, e), 700);
        }
    });

    function checkTip(e, endAction) {
        var $this     = $(this),
            $parent   = $this.parents('.my-tip'),
            $confirm  = $parent.find('.confirm-tip'),
            amount    = parseFloat($this.val(), 10) || 0,
            oldAmount = parseFloat($this.data('old-amount'), 10),
            max       = parseFloat($this.prop('max')),
            min       = parseFloat($this.prop('min')),
            inBounds  = amount <= max && amount >= min,
            same      = amount === oldAmount;

        // force two decimal points on value
        $this.val(amount.toFixed(2));

        // dis/enables confirm button as needed
        $confirm.prop('disabled', inBounds ? same : true);

        if (same)
            $parent.removeClass('changed');
        else
            $parent.addClass('changed');

        // show/hide the payment prompt
        if (amount === 0)
            $('#payment-prompt').removeClass('needed');
        else
            $('#payment-prompt').addClass('needed');

        if (inBounds ? endAction : endAction === 'cancel'){
            if(endAction==='cancel')
                $parent.find('.'+endAction+'-tip').click();
            else
                $parent.submit();
        }
    }

    $('.my-tip .cancel-tip').click(function(event) {
        event.preventDefault();

        var $myTip = $(this).parents('.my-tip').find('.my-tip');

        $myTip.val($myTip.data('old-amount')).change();
    });

    $('.my-tip .tip-suggestions a').click(function(event) {
        event.preventDefault();

        var $this  = $(this),
            $myTip = $this.parents('.my-tip').find('.my-tip');

        $myTip.val($this.text().match(/\d+/)[0] / ($this.hasClass('cents') ? 100 : 1)).change();
    });

    $('form.my-tip').submit(function(ev) {
        ev.preventDefault();
        var $this     = $(this),
            $myTip    = $this.find('.my-tip'),
            amount    = parseFloat($myTip.val(), 10),
            oldAmount = parseFloat($myTip.data('old-amount'), 10),
            tippee    = $myTip.data('tippee'),
            isAnon    = $($this).hasClass("anon");

        if (amount == oldAmount)
            return;

        if(isAnon)
            alert("Please sign in first");
        else {
            // send request to change tip
            $.post('/' + tippee + '/tip.json', { amount: amount }, function(data) {
                // lock-in changes
                $myTip.data('old-amount', amount).change();

                // update display
                $('.total-giving').text(data.total_giving);
                $('.total-receiving').text(
                    // check and see if we are on our giving page or not
                    new RegExp('/' + tippee + '/').test(window.location.href) ?
                        data.total_receiving_tippee : data.total_receiving);

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

