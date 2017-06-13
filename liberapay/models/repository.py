from __future__ import absolute_import, division, print_function, unicode_literals

from postgres.orm import Model

from liberapay.website import website


class Repository(Model):

    typname = "repositories"

    @property
    def url(self):
        platform = getattr(website.platforms, self.platform)
        return platform.repo_url.format(**self.__dict__)
