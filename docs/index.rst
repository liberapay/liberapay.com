www.gittip.com
==============

Welcome! This is the documentation for programmers working on `www.gittip.com`_
(not to be confused with programmers working with Gittip's `web API`_).

.. _www.gittip.com: https://github.com/gittip/www.gittip.com
.. _web API: https://github.com/gittip/www.gittip.com#api


DB Schema
---------

is_suspipicous on participant can be None, True or False. It represents unknown,
blacklisted or whitelisted user.

    * whitelisted can transfer money out of gittip
    * unknown can move money within gittip
    * blacklisted cannot do anything



Contents
--------

.. toctree::
    :maxdepth: 2

    gittip Python library <gittip>
