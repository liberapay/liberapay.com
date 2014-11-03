Gratipay.communities = {};

Gratipay.communities.update = function(name, is_member, success_callback, error_callback) {
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

Gratipay.communities.jumpTo = function(slug) {
    window.location.href = "/for/" + slug + "/";
};

Gratipay.communities.join = function(name, success_callback, error_callback) {
    Gratipay.communities.update(name, true, success_callback, error_callback);
};

Gratipay.communities.leave = function(name, callback) {
    if (confirm("Are you sure you want to leave the " + name + " community?"))
        Gratipay.communities.update(name, false, callback);

};
