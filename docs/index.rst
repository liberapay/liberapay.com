www.gratipay.com
==============

Welcome! This is the documentation for programmers working on `www.gratipay.com`_
(not to be confused with programmers working with Gratipay's `web API`_).

.. _www.gratipay.com: https://github.com/gratipay/www.gratipay.com
.. _web API: https://github.com/gratipay/www.gratipay.com#api


DB Schema
---------

is_suspipicous on participant can be None, True or False. It represents unknown,
blacklisted or whitelisted user.

    * whitelisted can transfer money out of gratipay
    * unknown can move money within gratipay
    * blacklisted cannot do anything


The exchanges table records movements of money into and out of Gratipay. The
``amount`` column shows a positive amount for payins and a negative amount for
payouts. The ``fee`` column is always positive. For both payins and payouts,
the ``amount`` does not include the ``fee`` (e.g., a $10 payin would result in
an ``amount`` of ``9.41`` and a ``fee`` of ``0.59``, and a $100 payout with a
2% fee would result in an ``amount`` of ``-98.04`` and a fee of ``1.96``).


Contents
--------

.. toctree::
    :maxdepth: 2

    gratipay Python library <gratipay>
