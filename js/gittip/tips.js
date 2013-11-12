Gittip.tips = {};

Gittip.tips.init = function() {
    // For authenticated users we change the tip!
    $('input.my-tip:not(.anon)').change(function() {
        var $this     = $(this),
            $parent   = $this.parents('[class^="my-tip"]'),
            $confirm  = $parent.find('.confirm-tip'),
            amount    = parseFloat($this.val(), 10) || 0,
            oldAmount = parseFloat($this.data('old-amount'), 10);

        // force two decimal points on value
        $this.val(amount.toFixed(2));

        // dis/enables confirm button as needed
        $confirm.prop('disabled', amount == oldAmount);

        if (amount == oldAmount)
            $parent.removeClass('changed');
        else
            $parent.addClass('changed');

        // show/hide the payment prompt
        if (amount === 0)
            $('#payment-prompt.needed').removeClass('needed');
        else
            $('#payment-prompt').addClass('needed');
    });

    $('.my-tip .cancel-tip').click(function(event) {
        event.preventDefault();

        var $this     = $(this),
            $myTip    = $this.parents('[class^="my-tip"]').find('.my-tip'),
            oldAmount = parseFloat($myTip.data('old-amount'), 10);

        $myTip.val(oldAmount).change();
    });

    $('.my-tip .tip-suggestions a').click(function(event) {
        event.preventDefault();

        var $this  = $(this),
            $myTip = $this.parents('[class^="my-tip"]').find('.my-tip');

        $myTip.val($this.text().match(/\d+/).shift() / ($this.hasClass('cents') ? 100 : 1)).change();
    });

    $('.my-tip .confirm-tip').click(function() {
        var $this     = $(this),
            $myTip    = $this.parents('[class^="my-tip"]').find('.my-tip'),
            amount    = parseFloat($myTip.val(), 10),
            oldAmount = parseFloat($myTip.data('old-amount'), 10),
            tippee    = $myTip.data('tippee');

        if (amount == oldAmount)
            return;

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
            $('.quick-stats')
                .find('a').text('$' + data.total_giving + '/wk');

            // Log to mixpanel.
            if (data.first_time === true)
                mixpanel.track("Explicitly Tip");
        })
        .fail(function() {
            // change to old amount?
            alert('Sorry, something went wrong while changing your tip. :(');
            console.log.apply(console, arguments);
        })
        .success(function() {
            // Confirm that tip changed.
            alert("Tip changed to $" + amount + "!");
        });
    });


    // For anonymous users we flash a login link.

    $('.my-tip-range.anon BUTTON').mouseover(function() {
        $('.sign-in-to-give .dropdown-toggle').addClass('highlight');
    });
    $('.my-tip-range.anon BUTTON').click(function() {
        var i = 0;
        (function flash() {
            if (i++ == 6) return;
            $('.sign-in-to-give .dropdown-toggle').toggleClass('highlight');
            setTimeout(flash, 100);
        })();
    });
};

