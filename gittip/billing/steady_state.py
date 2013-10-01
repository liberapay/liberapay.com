# -*- coding: utf-8 -*-
#
# Written in 2013 by Roy Liu <carsomyr@gmail.com>
#
# To the extent possible under law, the author(s) have dedicated all copyright
# and related and neighboring rights to this software to the public domain
# worldwide. This software is distributed without any warranty.
#
# You should have received a copy of the CC0 Public Domain Dedication along with
# this software. If not, see
# <http://creativecommons.org/publicdomain/zero/1.0/>.

"""A library for computing the payday steady state. It owes its existence to the knotty problem of determining payouts
under situations where funds contain funds themselves, and when the payout graph contains cycles.
"""

__author__ = "Roy Liu <carsomyr@gmail.com>"

import sys
from scipy.sparse import csr_matrix
from scipy.sparse import eye
from scipy.sparse import issparse
from scipy.sparse import lil_matrix

class SteadyState:
    """Contains core functionality for computing the steady state payouts.
    """

    def __init__(self):
        """Default constructor.
        """

    @staticmethod
    def converge(payouts, epsilon = 1e-10, max_rounds = 100):
        """Computes the the payday steady state by iteratively building a geometric sum of the payout matrix. TODO: Use
        a sparse solver to compute the exact answer.

        Args:
            n_rounds: The number of payout rounds to run.

        Returns:
            Converges to the steady state.
        """
        if not issparse(payouts):
            raise ArgumentError("Please provide a sparse matrix")

        (n_rows, n_cols) = payouts.shape

        if n_rows != n_cols:
            raise ArgumentError("The payout matrix must be square")

        payouts_d = lil_matrix((n_rows, n_cols))
        payouts_d.setdiag(payouts.diagonal())
        payouts_d = payouts_d.tocsr()

        payouts_without_d = payouts.copy()
        payouts_without_d.setdiag([0] * n_rows)
        payouts_without_d = payouts_without_d.tocsr()

        payouts = payouts.tocsr()

        acc1 = csr_matrix((n_rows, n_cols))
        acc2 = eye(n_rows, n_cols)

        for _ in range(max_rounds):
            acc1 = acc1 + acc2
            acc2 = acc2 * payouts_without_d

            if acc2.sum() < epsilon:
                break

        if acc2.sum() >= epsilon:
            raise RuntimeError("The payout matrix failed to converge")

        return acc1 * payouts_d + acc2

def main():
    """The main method body.
    """
    payouts = lil_matrix((5, 5))
    payouts[0, 0:5] = [0, .8, .2,  0, 0]
    payouts[1, 0:5] = [0,  1,  0,  0, 0]
    payouts[2, 0:5] = [0, .9,  0, .1, 0]
    payouts[3, 0:5] = [0,  0,  0,  1, 0]
    payouts[4, 0:5] = [.1, .5, .2, .2, 0]

    initial = lil_matrix((1, 5))
    initial[0, 0:5] = [100, 0, 100, 0, 100]

    print(payouts.todense())
    print(initial.todense())
    print(initial * SteadyState.converge(payouts).todense())

#

if __name__ == "__main__":
    sys.exit(main())
