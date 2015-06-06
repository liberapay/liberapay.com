Liberapay.settings = {};

Liberapay.settings.init = function() {

    // Wire up username knob
    Liberapay.forms.jsEdit({
        hideEditButton: true,
        root: $('.username.js-edit'),
        success: function(d) {
            window.location.href = "/" + encodeURIComponent(d.username) + "/settings/";
            return false;
        },
    });

};
