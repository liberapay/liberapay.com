// Main Namespace
// ==============

Offer = {};

Offer.main = function()
{
    Logstown.wire('authenticate-populated', function()
    {
        $('#field-confirm').hide();
    });

    $('FORM').inform();
};
