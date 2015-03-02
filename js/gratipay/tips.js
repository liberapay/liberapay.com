Gratipay.tips = {};

Gratipay.tips.init = function() {

    Gratipay.forms.jsEdit({
        confirmBeforeUnload: true,
        hideEditButton: true,
        root: $('.your-tip.js-edit'),
        success: function(data) {
            Gratipay.notification(data.msg, 'success');
            Gratipay.tips.afterTipChange(data);
        }
    });

    $('.your-tip button.edit').click(function() {
        $('.your-tip input').focus();
    });

    $('.your-tip button.stop').click(function() {
        $('.your-tip input').val('0');
        $('.your-tip button.save').click();
    });

    $('.your-tip button.cancel').click(function() {
        $('.your-tip form').trigger('reset');
    });

    // Cancel if the user presses the Escape key
    $('.your-tip input').keyup(function(e) {
        if (e.keyCode === 27)
            $('.your-tip button.cancel').click();
    });
};


Gratipay.tips.initSupportGratipay = function() {
    $('.support-gratipay button').click(function() {
        var amount = parseFloat($(this).attr('data-amount'), 10);
        Gratipay.tips.set('Gratipay', amount, function() {
            Gratipay.notification("Thank you so much for supporting Gratipay! :D", 'success');
            $('.support-gratipay').slideUp();

            // If you're on your own giving page ...
            var tip_on_giving = $('.your-tip[data-tippee="Gratipay"]');
            if (tip_on_giving.length > 0) {
                tip_on_giving[0].defaultValue = amount;
                tip_on_giving.attr('value', amount.toFixed(2));
            }
        });
    });

    $('.support-gratipay .no-thanks').click(function(event) {
        event.preventDefault();
        jQuery.post('/ride-free.json')
            .success(function() { $('.support-gratipay').slideUp(); })
            .fail(Gratipay.error)
    });
};


Gratipay.tips.afterTipChange = function(data) {
    $('.my-total-giving').text(data.total_giving_l);
    $('.total-receiving[data-tippee="'+data.tippee_id+'"]').text(data.total_receiving_tippee_l);
    $('#payment-prompt').toggleClass('needed', data.amount > 0);
    $('.npatrons[data-tippee="'+data.tippee_id+'"]').text(data.npatrons);

    var $your_tip = $('.your-tip[data-tippee="'+data.tippee_id+'"]');
    if ($your_tip) {
        var $input = $your_tip.find('input');
        $input[0].defaultValue = $input.val();
        $your_tip.find('span.amount').text(data.amount_l);
        $your_tip.find('.edit').toggleClass('not-zero', data.amount > 0);
        $your_tip.find('.stop').toggleClass('zero', data.amount === 0);
    }
};


Gratipay.tips.set = function(tippee, amount, callback) {

    // send request to change tip
    $.post('/' + tippee + '/tip.json', { amount: amount }, function(data) {
        if (callback) callback(data);
        Gratipay.tips.afterTipChange(data);
    })
    .fail(Gratipay.error);
};
