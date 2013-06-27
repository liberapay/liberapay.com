Gittip.team = angular.module('Gittip.team', []);

Gittip.team.TeamCtrl = function($scope, $http)
{
    function updateMembers(data)
    {
        for (var i=0, member; member=data[i]; i++)
            // The current user, but not the team itself.
            member.editing_allowed = member.is_current_user &&
                                     member.ctime !== null;
        $scope.members = data;
    }

    $scope.doLookup = function()
    {
        if ($scope.query == '')
            $scope.lookup = [];
        else
            $http.get("/lookup.json", {params: {query: $scope.query}})
                 .success(function(data) { $scope.lookup = data; });
    };

    $scope.doAdd = function()
    {
        $scope.change({'username': $scope.query}, '0.01', function() {
            alert('Member added!');
        });
        $scope.lookup = [];
        $scope.query = '';
        jQuery('#query').focus();
    };

    var updateHandle = null;
    $scope.doUpdate = function(member)
    {
        console.log(member.username, member.take);
        clearTimeout(updateHandle);
        updateHandle = setTimeout(function()
        {
            console.log('handling update');
            if (member.take.search(/^\d+\.?\d*$/) !== 0)
                return;
            $scope.change(member, member.take, function()
            {
                alert('Updated your take!');
            });
        }, 500);
    };

    $scope.change = function(participant, take, callback)
    {
        callback = callback || function() {};

        // The members.json endpoint takes a list of member objects so that it
        // can be updated programmatically in bulk (as with tips.json. From
        // this UI we only ever change one at a time, however.

        var data = { take: take
                   , csrf_token: getCookie('csrf_token')
                    };
        // http://stackoverflow.com/questions/12190166/
        data = jQuery.param(data);
        var content_type = 'application/x-www-form-urlencoded; charset=UTF-8';
        var config = {headers: {'Content-Type': content_type}};
        console.log('posting', participant.username, take);
        $http.post(participant.username + ".json", data, config)
             .success(function() { callback(); updateMembers(); });
    };

    $http.get("index.json").success(updateMembers);

    // No good way in Angular yet:
    // http://stackoverflow.com/questions/14833326/
    jQuery('#query').focus();
};
