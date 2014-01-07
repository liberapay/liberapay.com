Gittip.communities = {};

Gittip.communities.update = function(name, is_member, callback) {
    jQuery.ajax(
        { type: 'POST'
        , url: '/for/communities.json'
        , data: {name: name, is_member: is_member}
        , dataType: 'json'
        , success: callback
         }
    );
};

Gittip.communities.jumpTo = function(slug) {
    window.location.href = "/for/" + slug + "/";
};

Gittip.communities.join = function(name, callback) {
    Gittip.communities.update(name, true, callback);
};

Gittip.communities.leave = function(name, callback) {
    if (confirm("Are you sure you want to leave the " + name + " community?"))
        Gittip.communities.update(name, false, callback);

};
