Gittip.tips = {};

Gittip.tips.init = function()
{
    // For authenticated users we change the tip!

    $('INPUT.my-tip:not(.anon)').change(function()
    {
        // Define a closure that will be used to show/hide the payment prompt.

        function changePaymentPrompt(amount)
        {
            if (amount === '0.00')
                $('#payment-prompt.needed').removeClass('needed');
            else
                $('#payment-prompt').addClass('needed');
        }


        // Go to work!

        var amount = $(this).val();
        var oldAmount = $(this).attr('data-old-amount');
        var tippee = $(this).attr('data-tippee');

        if (oldAmount === amount)
            return;

        changePaymentPrompt(amount);

        jQuery.ajax(
            { url: '/' + tippee + '/tip.json'
            , data: {amount: amount}
            , type: "POST"
            , error: function(x,y,z) {
                changePaymentPrompt(oldAmount);
                alert("Sorry, something went wrong changing your tip. :(");
                console.log(x,y,z);
              }
             }
        )
        .done(function(data) {
            $('.total-giving').text(data['total_giving']);
            alert('Tip changed to $' + amount + '!');

            // Log to mixpanel.
            if (data.first_time === true)
                mixpanel.track("Explicitly Tip");
        });
    });


    // Range

    $('.my-tip-range INPUT.my-tip').each(function() {
        var drag     = false,
            delta    = 0,
            $gift    = $(this),
            $parent  = $gift.parent(),
            $zero    = $('<button>$0</button>'),
            $quarter = $('<button>25¢</button>'),
            $handle  = $('<button class="my-tip-range-handle">$10</button>'),
            $range   = $('<div class="my-tip-range-range"/>');

        function xMax() {
            return $range.innerWidth() -
                     parseInt($range.css('padding-left'), 10) -
                     parseInt($range.css('padding-right'), 10) -
                   $handle.outerWidth() -
                     parseInt($handle.css('margin-left'), 10) -
                     parseInt($handle.css('margin-right'), 10);
        }

        $handle.css({
            position: 'relative',
            left: 0
        });

        $range.css({
            position: 'relative',
            display: 'inline-block'
        });

        $handle.on({
            'mousedown touchstart': function(e) {
                var clientX = e.originalEvent.touches ? e.originalEvent.touches[0].clientX : e.clientX;
                drag = true;
                delta = clientX - parseInt($handle.css('left'), 10);
                $parent.find('button').removeClass('selected');
                $handle.addClass('selected drag');
                $gift.val($handle.text().substr(1));
            }
        });

        $(window).on({
            'mousemove touchmove': function(e) {
                if (!drag) return;
                if (e.originalEvent.touches) e.preventDefault();

                var value,
                    clientX = e.originalEvent.touches ? e.originalEvent.touches[0].clientX : e.clientX,
                    x   = clientX - delta,
                    max = xMax();

                if (x < 0)   x = 0;
                if (x > max) x = max;

                value = Math.round(x / max * 99) + 1;

                $handle
                    .text('$' + value)
                    .css('left', x);

                $gift.val(value);
            },

           'mouseup touchend': function() {
                if (!drag) return;
                drag = false;
                $gift.trigger('change');
                $handle.removeClass('drag');
            }
        });

        $zero.click(function() {
            $gift.val(0).trigger('change');
            $parent.find('button').removeClass('selected');
            $zero.addClass('selected');
        });

        $quarter.click(function() {
            $gift.val(0.25).trigger('change');
            $parent.find('button').removeClass('selected');
            $quarter.addClass('selected');
        });

        $range.append($handle);
        $parent.append($zero, $quarter, $range);

        // init
        $handle.css('left', (+$handle.text().substr(1) / 100) * xMax());

        switch (+$gift.val()) {
            case 0: $zero.addClass('selected'); break;
            case 0.25: $quarter.addClass('selected'); break;
            default:
                $handle.text("$" + (+$gift.val()));
                $handle.css('left', (+$gift.val() / 100) * xMax());
                $handle.addClass('selected');
                break;
        }
    });


    // For anonymous users we flash a login link.

    $('.my-tip-range.anon BUTTON').mouseover(
        function() {
            $('.sign-in-to-give .dropdown-toggle').addClass('highlight');
        }
    );
    $('.my-tip-range.anon BUTTON').click(function()
    {
        var i = 0
        function flash()
        {
            if (i++ == 6) return;
            $('.sign-in-to-give .dropdown-toggle').toggleClass('highlight');
            setTimeout(flash, 100);
        }
        flash();
    });
};

