// Degrade the console obj where not present.
// ==========================================
// http://fbug.googlecode.com/svn/branches/firebug1.2/lite/firebugx.js
// Relaxed to allow for Chrome's console.

function mock_console()
{
    var names = ["log", "debug", "info", "warn", "error", "assert", "dir",
                 "dirxml", "group", "groupEnd", "time", "timeEnd", "count",
                 "trace", "profile", "profileEnd"];
    window.console = {};
    for (var i=0, name; name = names[i]; i++)
        window.console[name] = function() {};
}

if (!window.console)
{
    mock_console();
}


function getCookie(key) {
    var o = new RegExp("(?:^|; ?)" + escape(key) + "=([^;]+)").exec(document.cookie);
    return o && unescape(o[1]);
}
