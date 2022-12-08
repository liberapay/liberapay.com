// Helper to append an optional TOTP-code to the login link when signing in via email
window.addEventListener("load", function () {
    var totp_field = document.getElementById("log-in-link-is-valid_totp_field");
    if (totp_field) {
        var login_button = document.getElementById("log-in-link-is-valid_button");
            totp_field.addEventListener("input", function () {
            var url = new URLSearchParams(login_button.href);
            url.set("log-in.totp", totp_field.value);
            login_button.href = decodeURIComponent(url.toString());
        });
    }
});
