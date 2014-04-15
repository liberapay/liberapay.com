# Dockerfile to build and run Gittip
# Version 0.1 (April 15, 2014)

################################################## General Information ##################################################

FROM ubuntu:12.04
MAINTAINER Mihir Singh (@citruspi)

ENV DEBIAN_FRONTEND noninteractive

################################################## Install Dependencies #################################################

RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ precise-pgdg main" > /etc/apt/sources.list.d/pgdg.list

RUN apt-get -y install wget

RUN wget --quiet --no-check-certificate https://www.postgresql.org/media/keys/ACCC4CF8.asc
RUN apt-key add ACCC4CF8.asc

RUN apt-get -y update

RUN apt-get -y install \
    git \
    gcc \
    make \
    g++ \
    libpq-dev \
    python-dev \
    python-pip \
    postgresql-9.3 \
    postgresql-contrib-9.3 \
    unzip \
    language-pack-en

################################################## Configure Postgres #################################################

RUN /etc/init.d/postgresql start && su postgres -c "createuser --superuser root" && su postgres -c "createdb gittip"

################################################# Clone + Setup Gittip ################################################

RUN cd /srv && wget --quiet https://github.com/gittip/www.gittip.com/archive/master.zip && unzip master.zip
RUN cd /srv/www.gittip.com-master && make env && /etc/init.d/postgresql start && make schema && make schema data

################################################ Create a Launch Script ###############################################

RUN echo "#!/bin/bash" >> /usr/bin/gittip
RUN echo "/etc/init.d/postgresql start" >> /usr/bin/gittip
RUN echo "cd /srv/www.gittip.com-master && make run" >> /usr/bin/gittip
RUN chmod +x /usr/bin/gittip

################################################### Set an Entrypoint #################################################

ENTRYPOINT ["/usr/bin/gittip"]

