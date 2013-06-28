Gittip.team = new function()
{
  var _ = Gittip;

  function init()
  {
    $('#lookup-container form').submit(add);
    $('#query').focus().keyup(lookup);

    jQuery.get("index.json").success(drawRows);
  };


  // Draw Rows
  // =========

  function num(n) { return n.toFixed(2); }
  function perc(n) { return (n * 100).toFixed(1); }

  function drawRows(members)
  {

    var rows = [];
    for (var i=0, member; member = members[i]; i++)
      rows.push(_.jsonml(
        [ 'tr'
        , ['td', ['a', {'href': '/'+member.username+'/'}, member.username]]
        , ['td', {'class': 'figure take'}, num(member.take)]
        , ['td', {'class': 'figure balance'}, num(member.balance)]
        , ['td', {'class': 'figure percentage'}, perc(member.percentage)]
         ]
      ));
    $('#members').html(rows);
  };


  // Add
  // ===

  function lookup()
  {
    var query = $('#query').val();
    if (query === '')
      $('#lookup-results').empty();
    else
      jQuery.get("/lookup.json", {query: query}).success(drawLookupResults);
  };

  function drawLookupResults(results)
  {
    var items = [];
    for (var i=0, result; result = results[i]; i++)
    {
      items.push(_.jsonml(
        ['li', {"data-id": result.id}, result.username]
      ));
    }
    $('#lookup-results').html(items);
  };

  function add(e)
  {
    e.preventDefault();
    e.stopPropagation();
    var query = $('#query').val();
    setTake(query, '0.01', function() { alert('Member added!'); });
    $('#lookup-results').empty();
    $('#query').val('').focus();
    return false;
  }


  // Take
  // ====

  function setTake(username, take, callback)
  {
    callback = callback || function() {};

    // The members.json endpoint takes a list of member objects so that it
    // can be updated programmatically in bulk (as with tips.json. From
    // this UI we only ever change one at a time, however.

    jQuery.ajax(
        { type: 'POST'
        , url: username + ".json"
        , data: {take: take}
        , success: function(d) { callback(); drawRows(d); }
        , error: function(xhr) {
            if (xhr.status === 404) alert("Unknown user!");
          }
         });
  };


  // Export
  // ======

  return {init: init};
}


/*
Gittip.team.TeamCtrl = function($scope, $http)
{
  function updateMembers(data)
  {
    console.log("Got data!", data);
    for (var i=0, member; member=data[i]; i++)
      // The current user, but not the team itself.
      member.editing_allowed = (member.is_current_user === true) &&
                   (member.ctime !== null);
    $scope.members = data;
  }

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
};
*/
