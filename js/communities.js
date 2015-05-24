Liberapay.communities = {};

Liberapay.communities.update = function(name, is_member, success_callback, error_callback) {
    jQuery.ajax(
        { type: 'POST'
        , url: '/for/communities.json'
        , data: {name: name, is_member: is_member}
        , dataType: 'json'
        , success: success_callback
        , error: error_callback
         }
    );
};

Liberapay.communities.jumpTo = function(slug) {
    window.location.href = "/for/" + slug + "/";
};

Liberapay.communities.join = function(name, success_callback, error_callback) {
    Liberapay.communities.update(name, true, success_callback, error_callback);
};

Liberapay.communities.leave = function(name, callback) {
    if (confirm("Are you sure you want to leave the " + name + " community?"))
        Liberapay.communities.update(name, false, callback);

};
