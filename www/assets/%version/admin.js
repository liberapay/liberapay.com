$(document).ready(function()
{
    // Wire up is_suspicious toggle.
    // =============================

    $('label.is-suspicious-knob').click(function()
    {
        var username = $(this).attr('data-username');
        jQuery.ajax(
            { url: '/' + username + '/toggle-is-suspicious.json'
            , type: 'POST'
            , dataType: 'json'
            , success: function(data)
            {
                if (data.is_suspicious)
                    $(".on-profile").addClass('is-suspicious');
                else
                    $(".on-profile").removeClass('is-suspicious');
                $('INPUT.is-suspicious-knob').attr( 'checked'
                                                  , data.is_suspicious
                                                   );
            }
            , error: function() {
                    alert( "Failed to change is_suspicious. Please "
                         + "try again."
                          );
                }
             }
        );
    });
});
