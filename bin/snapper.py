#!/usr/bin/env python
"""This is a command line utility for managing Gratipay backups.

Running this script gets you a `snapper> ` prompt with commands to take backups
and load them locally. Backups are managed as *.psql files in ../backups/, and
they're loaded into a local gratipay-bak database. Type 'help' or '?' at the
prompt for help.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import cmd
import os
import subprocess


class Snapper(cmd.Cmd):

    prompt = 'snapper> '
    root = '../backups'
    dbname = 'gratipay-bak'

    def do_EOF(self, line):
        raise KeyboardInterrupt

    def do_quit(self, line):
        raise SystemExit
    do_exit = do_quit

    def do_new(self, line):
        """Take a new backup.
        """
        subprocess.call('./backup.sh')
    do_n = do_new

    def do_list(self, line):
        """List available backups.
        """
        filenames = self.get_filenames()
        for i, filename in enumerate(filenames):
            print('{:>2} {}'.format(i, filename[:-len('.psql')]))
    do_l = do_list

    def get_filenames(self):
        return sorted([f for f in os.listdir(self.root) if f.endswith('.psql')])

    def do_load(self, line):
        """Load a backup based on its number per `list`..
        """
        try:
            i = int(line)
            filename = self.get_filenames()[i]
        except (ValueError, KeyError):
            print('\x1b[31;1mBad backup number!\x1b[0m')
            print('\x1b[32;1mPick one of these:\x1b[0m')
            self.do_list('')
        else:
            if subprocess.call(['dropdb', self.dbname]) == 0:
                if subprocess.call(['createdb', self.dbname]) == 0:
                    subprocess.call( 'psql {} < {}/{}'.format(self.dbname, self.root, filename)
                                   , shell=True
                                    )


if __name__ == '__main__':
    try:
        Snapper().cmdloop()
    except KeyboardInterrupt:
        print()
