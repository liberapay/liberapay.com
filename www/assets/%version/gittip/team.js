Gittip.team = new function()
{
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

  function drawMemberTake(member)
  {
    var take = num(member.take);
    if (member.editing_allowed)
      return [ 'form', {'id': 'take'}
             , ['input', { 'value': take
                         , 'data-username': member.username
                         , 'data-take': take // useful to reset form
                         , 'tabindex': '1'
                          }]
              ];
    else
      return take;
  };

  function drawRows(members)
  {

    var rows = [];
    for (var i=0, member; member = members[i]; i++)
      rows.push(Gittip.jsonml(
        [ 'tr'
        , ['td', ['a', {'href': '/'+member.username+'/'}, member.username]]
        , ['td', {'class': 'figure take'}, drawMemberTake(member)]
        , ['td', {'class': 'figure balance'}, num(member.balance)]
        , ['td', {'class': 'figure percentage'}, perc(member.percentage)]
         ]
      ));
    $('#members').html(rows);
    $('#take').submit(doTake);
    $('#take input').focus().keyup(maybeCancelTake);
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
      items.push(Gittip.jsonml(
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

  function maybeCancelTake(e)
  {
    if (e.which === 27)
    {
      var _ = $('#take input');
      _.val(_.attr('data-take')).blur();
    }
  };

  function doTake(e)
  {
    e.preventDefault();
    e.stopPropagation();
    var frm = $('#take'), _ = $('input', frm);
    var username = _.attr('data-username'),
        take = _.val();
    if (take.search(/^\d+\.?\d*$/) !== 0)
      alert("Bad input! Must be a number.");
    else
      setTake(username, take, function() { alert('Updated your take!'); });
    return false;
  };

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
            switch (xhr.status) {
              case 404: alert("Unknown user!"); break;
              case 450: alert("Too greedy!"); break;
              default: alert("Problem! " + xhr.status);
            }
          }
         });
  }


  // Export
  // ======

  return {init: init};
}
