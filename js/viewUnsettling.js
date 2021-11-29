Liberapay.view_unsettling = {};

Liberapay.view_unsettling.init = function () {
    Liberapay.view_unsettling.once();
    Liberapay.view_unsettling.opt_in();
};

Liberapay.view_unsettling.once = function () {
    $(".display-unsettling-once").click(function () {
        $(this).remove();
        $("#unsettling-content-display").remove();
    });
};

Liberapay.view_unsettling.opt_in = function () {
    $(".display-unsettling-opt-in").click(function () {
        $(this).remove();
        $("#unsettling-content-display").remove();

        document.cookie = 'always_view_unsettling=True;domain=;path=/';
    });
};
