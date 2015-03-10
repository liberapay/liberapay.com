# Dockerfile to build and run Gratipay
# Version 0.2 (March 10, 2015)

################################################## General Information ##################################################

FROM ubuntu:14.04
MAINTAINER Mihir Singh (@citruspi)

ENV DEBIAN_FRONTEND noninteractive

################################################## Install Dependencies #################################################

RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ trusty-pgdg main" > /etc/apt/sources.list.d/pgdg.list

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
    language-pack-en

################################################## Configure Postgres #################################################

RUN /etc/init.d/postgresql start && su postgres -c "createuser --superuser root" && su postgres -c "createdb gratipay"

################################################# Copy files + Setup Gratipay ##########################################

COPY ./ /srv/gratipay.com/
WORKDIR /srv/gratipay.com
RUN make env && /etc/init.d/postgresql start && make schema && make schema data

################################################ Create a Launch Script ###############################################

RUN echo "#!/bin/bash" >> /usr/bin/gratipay && \
    echo "/etc/init.d/postgresql start" >> /usr/bin/gratipay && \
    echo "cd /srv/gratipay.com && make run" >> /usr/bin/gratipay && \
    chmod +x /usr/bin/gratipay

################################################### Launch command #####################################################

CMD ["/usr/bin/gratipay"]

